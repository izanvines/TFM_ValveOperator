#!/bin/bash
# Instancia de Isaac Sim para MIRAR, no para medir: la politica intenta abrir la valvula sin
# parar y la escena se transmite por WebRTC para poder moverse por ella con el raton.
#
#   setsid nohup bash ~/eval/arena_extras/mirador_politica.sh > /dev/null 2>&1 &
#
# Convive con la evaluacion sin estorbarla:
#   * todo va a la GPU 1 (`--device cuda:1` + `activeGpu=1`), mientras la evaluacion usa la 0.
#   * servidor de politica PROPIO en el 5563. Reutilizar el 5561 de la evaluacion seria peor que
#     lento: el servidor ZMQ atiende una peticion a la vez, asi que los dos clientes se
#     intercalarian y ninguna de las dos tiradas mediria lo que cree medir.
#   * livestream en 49120/48020, que son los que ufw permite desde <SUBRED_LAN>. El 49100 es
#     de CloudXR y `--livestream 1` lo fija sin poder cambiarlo: por ahi la imagen sale negra.
#
# NO usar CUDA_VISIBLE_DEVICES para elegir GPU: deja CUDA en un estado que vuelve negro el
# monitor WebRTC. Se elige con --device y --/renderer/activeGpu.
set -u
LOGS=$HOME/eval/logs
ARENA=$HOME/TFM/IsaacLab-Arena
GR00T=$HOME/TFM/isaac-gr00t-standalone
PUERTO=5563

echo "[$(date +%H:%M:%S)] mirador: arrancando servidor de politica en el $PUERTO" | tee -a "$LOGS/mirador.log"
( cd "$ARENA" && PYTHONPATH=$ARENA "$GR00T/.venv/bin/python" -u \
    -m isaaclab_arena.remote_policy.remote_policy_server_runner \
    --policy_type isaaclab_arena_gr00t.policy.gr00t_remote_policy.Gr00tRemoteServerSidePolicy \
    --host 127.0.0.1 --port $PUERTO --timeout_ms 600000 \
    --policy_config_yaml_path isaaclab_arena_gr00t/policy/config/g1_valve100_gr00t_closedloop_config.yaml \
    --policy_device cuda:1 ) > "$LOGS/mirador_servidor.log" 2>&1 &

for _ in $(seq 1 120); do
  grep -q "listening on tcp://" "$LOGS/mirador_servidor.log" 2>/dev/null && break
  sleep 5
done
grep -q "listening on tcp://" "$LOGS/mirador_servidor.log" 2>/dev/null \
  || { echo "[$(date +%H:%M:%S)] mirador: el servidor no arranco" | tee -a "$LOGS/mirador.log"; exit 1; }

echo "[$(date +%H:%M:%S)] mirador: servidor listo, arrancando el simulador" | tee -a "$LOGS/mirador.log"
docker exec -w /workspaces/isaaclab_arena isaaclab_arena-latest bash -c \
 "unset DISPLAY && export HOME=/home/ivines && export ARENA_FIX_BASE=1 && \
  unset OFFICE_GS_LIGHT && export ARENA_VALVE_EPISODE_S=20 && \
  /isaac-sim/python.sh -u isaaclab_arena/evaluation/policy_runner.py \
    --policy_type isaaclab_arena.policy.action_chunking_client.ActionChunkingClientSidePolicy \
    --remote_host 127.0.0.1 --remote_port $PUERTO --remote_timeout_ms 600000 \
    --enable_cameras --device cuda:1 --num_envs 1 --num_episodes 100000 \
    --language_instruction 'turn the handwheel to open the valve' \
    --viz kit --livestream 2 \
    --kit_args='--/renderer/multiGpu/enabled=false --/renderer/activeGpu=1 \
--/exts/omni.kit.livestream.app/primaryStream/signalPort=49120 \
--/exts/omni.kit.livestream.app/primaryStream/streamPort=48020 \
--/exts/omni.kit.livestream.app/primaryStream/publicIp=${STREAM_PUBLIC_IP:?Define STREAM_PUBLIC_IP con la IP de la estación que ve el cliente WebRTC (se ha quitado del repositorio)}' \
    g1_valve --embodiment g1_wbc_agile_joint --background office_gs" \
  > "$LOGS/mirador_sim.log" 2>&1
echo "[$(date +%H:%M:%S)] mirador: terminado" | tee -a "$LOGS/mirador.log"
