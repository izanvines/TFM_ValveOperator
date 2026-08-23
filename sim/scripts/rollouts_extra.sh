#!/bin/bash
# 100 rollouts MAS por politica, con una semilla distinta, para sumar a los 100 que ya hay.
#
#   setsid nohup bash ~/eval/arena_extras/rollouts_extra.sh > /dev/null 2>&1 &
#
# Por que una semilla distinta y no repetir la 42: con la misma semilla el simulador reproduce
# exactamente las mismas 100 condiciones y la tirada no aportaria informacion nueva -- seria una
# hora de maquina para volver a obtener el mismo resultado.
#
# Por que la MISMA semilla en las dos politicas: para que la comparacion siga siendo emparejada.
# Cada politica ve la misma valvula en el mismo orden, que es lo que permite usar McNemar y lo
# que elimina la duda de si una tuvo tiradas mas faciles.
#
# Agrupar los dos bloques (semilla 42 + semilla 7) es valido porque dentro de cada bloque las dos
# politicas ven condiciones identicas. Lo que NO valdria es comparar el bloque de una contra el
# bloque de la otra.
set -u
LOGS=$HOME/eval/logs
RES=$HOME/eval/resultados
ARENA=$HOME/TFM/IsaacLab-Arena
GR00T=$HOME/TFM/isaac-gr00t-standalone
REG=$LOGS/rollouts_extra.log
SEMILLA=${SEMILLA:-7}
EPISODIOS=${EPISODIOS:-100}
INSTRUCCION="turn the handwheel to open the valve"

anota() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$REG"; }
mkdir -p "$RES"

cliente() {   # $1 = puerto
  docker exec -w /workspaces/isaaclab_arena isaaclab_arena-latest bash -c \
   "unset DISPLAY && export HOME=/home/ivines && export ARENA_FIX_BASE=1 && \
    unset OFFICE_GS_LIGHT && export ARENA_VALVE_EPISODE_S=20 && export ARENA_EVAL_RECORD=1 && \
    /isaac-sim/python.sh -u isaaclab_arena/evaluation/policy_runner.py \
      --policy_type isaaclab_arena.policy.action_chunking_client.ActionChunkingClientSidePolicy \
      --remote_host 127.0.0.1 --remote_port $1 --remote_timeout_ms 300000 \
      --enable_cameras --device cuda:0 --num_envs 1 --num_episodes ${EPISODIOS} \
      --seed ${SEMILLA} --language_instruction '${INSTRUCCION}' \
      --kit_args='--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0' \
      g1_valve --embodiment g1_wbc_agile_joint --background office_gs"
}

esperar() { for _ in $(seq 1 120); do grep -q "listening on tcp://" "$1" 2>/dev/null && return 0; sleep 5; done; return 1; }

# Se apunta que ficheros habia antes para saber cual es el nuevo: el mirador tambien escribe en
# /tmp/isaaclab/logs y coger "el mas reciente" a ciegas podria devolver el suyo.
recoger() {   # $1 = fichero con el listado previo, $2 = destino
  nuevo=$(ls -t /tmp/isaaclab/logs/*.hdf5 2>/dev/null | grep -vxF -f "$1" | head -1)
  if [ -n "$nuevo" ]; then cp "$nuevo" "$2"; anota "  -> $(basename "$2") desde $(basename "$nuevo")"
  else anota "  -> NO se encontro HDF5 nuevo"; fi
}

for POL in gr00t act; do
  PUERTO=$([ "$POL" = gr00t ] && echo 5571 || echo 5572)
  anota "${POL}: arrancando servidor en el ${PUERTO}"
  if [ "$POL" = gr00t ]; then
    ( cd "$ARENA" && PYTHONPATH=$ARENA "$GR00T/.venv/bin/python" -u \
        -m isaaclab_arena.remote_policy.remote_policy_server_runner \
        --policy_type isaaclab_arena_gr00t.policy.gr00t_remote_policy.Gr00tRemoteServerSidePolicy \
        --host 127.0.0.1 --port $PUERTO --timeout_ms 300000 \
        --policy_config_yaml_path isaaclab_arena_gr00t/policy/config/g1_valve100_gr00t_closedloop_config.yaml \
        --policy_device cuda:1 ) > "$LOGS/serv_extra_${POL}.log" 2>&1 &
  else
    ( cd "$ARENA" && PYTHONPATH=$ARENA:$HOME/Desktop/VLA-HumanoidG1/train/scripts \
        CUDA_VISIBLE_DEVICES=1 "$HOME/venvs/lerobot-act/bin/python" -u \
        -m isaaclab_arena.remote_policy.remote_policy_server_runner \
        --policy_type act_remote_policy.ActRemoteServerSidePolicy \
        --host 127.0.0.1 --port $PUERTO --timeout_ms 300000 \
        --checkpoint $HOME/models/isaaclab_arena/g1_valve/act_valve100_20k/checkpoints/020000/pretrained_model \
        --device cuda \
        --stats_json $HOME/datasets/isaaclab_arena/g1_valve/valve_100/lerobot/meta/stats.json \
      ) > "$LOGS/serv_extra_${POL}.log" 2>&1 &
  fi
  PID_S=$!
  if esperar "$LOGS/serv_extra_${POL}.log"; then
    ls /tmp/isaaclab/logs/*.hdf5 2>/dev/null > "$LOGS/_antes_${POL}.txt" || : > "$LOGS/_antes_${POL}.txt"
    anota "${POL}: servidor listo, ${EPISODIOS} rollouts con semilla ${SEMILLA}"
    cliente "$PUERTO" > "$LOGS/eval_extra_${POL}.log" 2>&1
    anota "${POL}: $(grep -aoE 'Metrics: \{[^}]*\}' "$LOGS/eval_extra_${POL}.log" | tail -1)"
    recoger "$LOGS/_antes_${POL}.txt" "$RES/${POL}_extra100.hdf5"
  else
    anota "${POL}: el servidor no llego a escuchar"
  fi
  kill -9 $PID_S 2>/dev/null; sleep 5
done
anota "ROLLOUTS EXTRA COMPLETOS"
