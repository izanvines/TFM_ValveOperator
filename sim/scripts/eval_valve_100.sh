#!/bin/bash
# Evalua las dos politicas entrenadas sobre `g1_valve`, en el simulador, CON el fondo de oficina.
#
#   setsid nohup bash ~/eval/arena_extras/eval_valve_100.sh > /dev/null 2>&1 &
#
# Orden deliberado: primero los VIDEOS (5 rollouts, minutos) y luego las metricas (100 rollouts,
# ~1 h cada politica). Si algo se tuerce de madrugada, los videos ya estan.
#
# Por que `--background office_gs`: las imagenes con las que se entreno salen del re-render con la
# oficina. Evaluar en diafano seria cambiarle la entrada visual a la politica.
# Por que NO se define OFFICE_GS_LIGHT: por defecto son 3000, que es con lo que se genero el
# dataset entero. La nota de TRAIN.md que pide 1500 es del ensayo, que entreno en diafano.
# Por que `--embodiment g1_wbc_agile_joint`: la columna `action` del dataset son las 43 juntas de
# salida de Pink IK, no las 23 de entrada. Con el embodiment de grabacion sale
# `Invalid action shape, expected: 23, received: 50`.
set -u
LOGS=$HOME/eval/logs
REG=$LOGS/eval_valve_100.log
ARENA=$HOME/TFM/IsaacLab-Arena
GR00T=$HOME/TFM/isaac-gr00t-standalone
VIDEOS=$HOME/eval/videos/politicas
EPISODIOS=${EPISODIOS:-100}
INSTRUCCION="turn the handwheel to open the valve"

anota() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$REG"; }

mkdir -p "$VIDEOS"

anota "esperando a que termine el entrenamiento..."
for _ in $(seq 1 720); do            # hasta 3 h
  grep -q "ENTRENAMIENTO COMPLETO" "$LOGS/train_valve_100.log" 2>/dev/null && break
  sleep 15
done
grep -q "ENTRENAMIENTO COMPLETO" "$LOGS/train_valve_100.log" 2>/dev/null \
  || { anota "ABANDONO: el entrenamiento no termino"; exit 1; }

# --- YAML de GR00T apuntando al checkpoint nuevo ------------------------------------------
YAML=$ARENA/isaaclab_arena_gr00t/policy/config/g1_valve100_gr00t_closedloop_config.yaml
sed 's|^model_path:.*|model_path: '"$HOME"'/models/isaaclab_arena/g1_valve/gr00t_n17_valve100_10k/checkpoint-10000|' \
  "$ARENA/isaaclab_arena_gr00t/policy/config/g1_valve_gr00t_closedloop_config.yaml" > "$YAML"
anota "YAML de GR00T: $(grep ^model_path "$YAML")"

# --- Cliente: identico para las dos politicas ---------------------------------------------
cliente() {   # $1 = puerto, $2 = num_episodios, $3 = etiqueta, $4 = "video" | "metricas"
  local extra=""  reg_extra=""
  if [ "$4" = "video" ]; then
    extra="--video --video_dir /eval/videos/politicas/$3 --viz kit"
  else
    reg_extra="export ARENA_EVAL_RECORD=1 &&"
  fi
  docker exec -w /workspaces/isaaclab_arena isaaclab_arena-latest bash -c \
   "unset DISPLAY && export HOME=/home/ivines && export ARENA_FIX_BASE=1 && \
    unset OFFICE_GS_LIGHT && export ARENA_VALVE_EPISODE_S=20 && ${reg_extra} \
    /isaac-sim/python.sh -u isaaclab_arena/evaluation/policy_runner.py \
      --policy_type isaaclab_arena.policy.action_chunking_client.ActionChunkingClientSidePolicy \
      --remote_host 127.0.0.1 --remote_port $1 --remote_timeout_ms 300000 \
      --enable_cameras --device cuda:0 --num_envs 1 --num_episodes $2 --seed 42 \
      --language_instruction '${INSTRUCCION}' ${extra} \
      --kit_args='--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0' \
      g1_valve --embodiment g1_wbc_agile_joint --background office_gs"
}

esperar_servidor() {   # $1 = fichero de log
  for _ in $(seq 1 120); do
    grep -q "listening on tcp://" "$1" 2>/dev/null && return 0
    sleep 5
  done
  return 1
}

# =========================== GR00T ==========================================================
anota "GR00T: arrancando servidor"
( cd "$ARENA" && PYTHONPATH=$ARENA "$GR00T/.venv/bin/python" -u \
    -m isaaclab_arena.remote_policy.remote_policy_server_runner \
    --policy_type isaaclab_arena_gr00t.policy.gr00t_remote_policy.Gr00tRemoteServerSidePolicy \
    --host 127.0.0.1 --port 5561 --timeout_ms 300000 \
    --policy_config_yaml_path isaaclab_arena_gr00t/policy/config/g1_valve100_gr00t_closedloop_config.yaml \
    --policy_device cuda:1 ) > "$LOGS/serv_gr00t.log" 2>&1 &
PID_S=$!
if esperar_servidor "$LOGS/serv_gr00t.log"; then
  anota "GR00T: servidor listo. Video de 5 rollouts"
  cliente 5561 5 gr00t video > "$LOGS/eval_gr00t_video.log" 2>&1
  anota "GR00T: video hecho. Metricas de ${EPISODIOS} rollouts"
  cliente 5561 "$EPISODIOS" gr00t metricas > "$LOGS/eval_gr00t.log" 2>&1
  anota "GR00T: metricas hechas"
else
  anota "GR00T: el servidor no llego a escuchar, ver serv_gr00t.log"
fi
kill -9 $PID_S 2>/dev/null; sleep 5

# =========================== ACT ============================================================
# CUDA_VISIBLE_DEVICES=1 con --device cuda, NUNCA --device cuda:1: en cuda:1 los buferes de
# normalizacion se quedan a std=0 y la red satura emitiendo ceros exactos, sin ningun mensaje.
anota "ACT: arrancando servidor"
( cd "$ARENA" && PYTHONPATH=$ARENA:$HOME/Desktop/VLA-HumanoidG1/train/scripts \
    CUDA_VISIBLE_DEVICES=1 "$HOME/venvs/lerobot-act/bin/python" -u \
    -m isaaclab_arena.remote_policy.remote_policy_server_runner \
    --policy_type act_remote_policy.ActRemoteServerSidePolicy \
    --host 127.0.0.1 --port 5562 --timeout_ms 300000 \
    --checkpoint $HOME/models/isaaclab_arena/g1_valve/act_valve100_20k/checkpoints/020000/pretrained_model \
    --device cuda \
    --stats_json $HOME/datasets/isaaclab_arena/g1_valve/valve_100/lerobot/meta/stats.json \
  ) > "$LOGS/serv_act.log" 2>&1 &
PID_S=$!
if esperar_servidor "$LOGS/serv_act.log"; then
  anota "ACT: servidor listo. Video de 5 rollouts"
  cliente 5562 5 act video > "$LOGS/eval_act_video.log" 2>&1
  anota "ACT: video hecho. Metricas de ${EPISODIOS} rollouts"
  cliente 5562 "$EPISODIOS" act metricas > "$LOGS/eval_act.log" 2>&1
  anota "ACT: metricas hechas"
else
  anota "ACT: el servidor no llego a escuchar, ver serv_act.log"
fi
kill -9 $PID_S 2>/dev/null

anota "EVALUACION COMPLETA"
