#!/bin/bash
# Prepara las estadisticas y entrena las DOS politicas sobre el dataset de 100 demos.
# Corre en el HOST (los venvs estan fuera del contenedor) y hay que lanzarlo con `setsid`
# para que sobreviva a la sesion que lo arranca.
#
#   setsid nohup bash ~/eval/arena_extras/train_valve_100.sh > /dev/null 2>&1 &
#
# Espera a que la cadena del dataset (pipeline_valve_100.sh, dentro del contenedor) termine.
set -u
LOGS=$HOME/eval/logs
DS=$HOME/datasets/isaaclab_arena/g1_valve/valve_100
REG=$LOGS/train_valve_100.log
GR00T=$HOME/TFM/isaac-gr00t-standalone
MOD=$HOME/TFM/IsaacLab-Arena/isaaclab_arena_gr00t/embodiments/g1/g1_sim_wbc_data_gr00t_n_1_7_config.py

anota() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$REG"; }

anota "esperando a que termine la cadena del dataset..."
for _ in $(seq 1 480); do            # hasta 2 h
  [ -f "$LOGS/etapa_convert.ok" ] && break
  sleep 15
done
if [ ! -f "$LOGS/etapa_convert.ok" ]; then anota "ABANDONO: la conversion no termino"; exit 1; fi
anota "dataset listo en $DS/lerobot"

# --- info.json coherente ---------------------------------------------------------------
if [ ! -f "$LOGS/etapa_meta.ok" ]; then
  python3 $HOME/Desktop/VLA-HumanoidG1/train/scripts/fix_lerobot_meta.py "$DS/lerobot" \
    >> "$REG" 2>&1 && touch "$LOGS/etapa_meta.ok" && anota "meta arreglado"
fi

# --- Estadisticas para GR00T ------------------------------------------------------------
# NEW_EMBODIMENT en MAYUSCULAS: esta ruta usa el nombre del enum via tyro. `generate_stats` se
# cortocircuita si ya hay un stats.json valido, asi que se borra para no heredar el del dataset
# anterior.
if [ ! -f "$LOGS/etapa_stats.ok" ]; then
  anota "estadisticas: empieza"
  rm -f "$DS/lerobot/meta/stats.json"
  ( cd "$GR00T" && ./.venv/bin/python gr00t/data/stats.py \
      --dataset-path "$DS/lerobot" \
      --embodiment-tag NEW_EMBODIMENT \
      --modality-config-path "$MOD" ) > "$LOGS/stats.log" 2>&1 \
    || { anota "estadisticas: FALLO, ver stats.log"; exit 1; }
  anota "estadisticas: hechas"
  touch "$LOGS/etapa_stats.ok"
fi

# --- Vista del dataset para ACT ----------------------------------------------------------
if [ ! -f "$LOGS/etapa_actview.ok" ]; then
  anota "vista ACT: empieza"
  rm -rf "$DS/lerobot_act"
  $HOME/venvs/lerobot-act/bin/python \
    $HOME/Desktop/VLA-HumanoidG1/train/scripts/make_lerobot_act_view.py \
    --src "$DS/lerobot" --dest "$DS/lerobot_act" > "$LOGS/actview.log" 2>&1 \
    || { anota "vista ACT: FALLO"; exit 1; }
  anota "vista ACT: hecha"
  touch "$LOGS/etapa_actview.ok"
fi

# --- Entrenar las dos a la vez, una GPU cada una -----------------------------------------
# Directorios de salida NUEVOS: experiment.py llama a train(resume_from_checkpoint=True) sin
# condiciones, y con un checkpoint viejo cuyo global_step ya sea max_steps ejecuta CERO pasos
# y guarda los pesos de antes.
SAL_GR=$HOME/models/isaaclab_arena/g1_valve/gr00t_n17_valve100_10k
SAL_ACT=$HOME/models/isaaclab_arena/g1_valve/act_valve100_20k
rm -rf "$SAL_GR" "$SAL_ACT"

anota "GR00T (GPU 0, 10k pasos) y ACT (GPU 1, 20k pasos): arrancan en paralelo"

( cd "$GR00T" && NUM_GPUS=1 GLOBAL_BATCH_SIZE=32 MAX_STEPS=10000 SAVE_STEPS=2000 USE_WANDB=0 \
  SHARD_SIZE=512 DATALOADER_NUM_WORKERS=4 EPISODE_SAMPLING_RATE=0.1 \
  CUDA_VISIBLE_DEVICES=0 PATH=$GR00T/.venv/bin:$PATH \
  bash examples/finetune.sh \
    --base-model-path $HOME/models/isaaclab_arena/static_apple_tutorial/gn1x_tuned_static_apple \
    --dataset-path "$DS/lerobot" \
    --embodiment-tag new_embodiment \
    --modality-config-path "$MOD" \
    --output-dir "$SAL_GR" --save-only-model ) > "$LOGS/train_gr00t.log" 2>&1 &
PID_GR=$!

# CUDA_VISIBLE_DEVICES=1 con --policy.device=cuda, NUNCA cuda:1.
( CUDA_VISIBLE_DEVICES=1 $HOME/venvs/lerobot-act/bin/lerobot-train \
    --dataset.repo_id=tfm/g1_valve_100 \
    --dataset.root="$DS/lerobot_act" \
    --dataset.video_backend=torchcodec \
    --policy.type=act --policy.device=cuda --policy.push_to_hub=false \
    --policy.chunk_size=40 --policy.n_action_steps=40 \
    --batch_size=8 --steps=20000 --save_freq=5000 --log_freq=200 --num_workers=8 \
    --wandb.enable=false --seed=42 \
    --output_dir="$SAL_ACT" ) > "$LOGS/train_act.log" 2>&1 &
PID_ACT=$!

wait $PID_ACT; anota "ACT: terminado (codigo $?)"
wait $PID_GR;  anota "GR00T: terminado (codigo $?)"
anota "ENTRENAMIENTO COMPLETO"
