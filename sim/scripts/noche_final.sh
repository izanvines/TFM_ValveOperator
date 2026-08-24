#!/bin/bash
# Ultima noche de maquina antes de escribir la memoria. Anade dos ejes de comparacion baratos
# sobre lo que ya esta medido: latencia de inferencia y curva de eficiencia de datos.
#
#   setsid nohup bash ~/Desktop/VLA-HumanoidG1/sim/scripts/noche_final.sh > /dev/null 2>&1 &
#
# LA GPU 1 NO SE TOCA: la ocupa un Qwen del usuario (88 GB). Todo va a la GPU 0, en serie.
# Por eso ACT pasa de CUDA_VISIBLE_DEVICES=1 a 0 y el servidor de GR00T de cuda:1 a cuda:0.
#
# Orden deliberado: primero la latencia (15 min, usa los checkpoints que ya existen). Si la
# curva se tuerce de madrugada, por la manana al menos hay un resultado nuevo.
#
# Centinela por etapa en ~/eval/logs/noche_*.ok: relanzar el guion salta lo ya hecho.
set -u
LOGS=$HOME/eval/logs
RES=$HOME/eval/resultados
DS=$HOME/datasets/isaaclab_arena/g1_valve
MOD_DIR=$HOME/models/isaaclab_arena/g1_valve
ARENA=$HOME/TFM/IsaacLab-Arena
GR00T=$HOME/TFM/isaac-gr00t-standalone
SCRIPTS=$HOME/Desktop/VLA-HumanoidG1/train/scripts
MOD=$ARENA/isaaclab_arena_gr00t/embodiments/g1/g1_sim_wbc_data_gr00t_n_1_7_config.py
CFGDIR=$ARENA/isaaclab_arena_gr00t/policy/config
REG=$LOGS/noche_final.log
INSTRUCCION="turn the handwheel to open the valve"
mkdir -p "$RES" "$LOGS"

anota() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$REG"; }
hecho() { [ -f "$LOGS/noche_$1.ok" ]; }
marca() { touch "$LOGS/noche_$1.ok"; }

esperar() { for _ in $(seq 1 180); do grep -q "listening on tcp://" "$1" 2>/dev/null && return 0; sleep 5; done; return 1; }

# El mirador y otras evaluaciones tambien escriben en /tmp/isaaclab/logs; coger "el mas reciente"
# a ciegas podria devolver un fichero ajeno.
recoger() { # $1 listado previo, $2 destino
  nuevo=$(ls -t /tmp/isaaclab/logs/*.hdf5 2>/dev/null | grep -vxF -f "$1" | head -1)
  if [ -n "$nuevo" ]; then cp "$nuevo" "$2"; anota "  -> $(basename "$2")"
  else anota "  -> NO aparecio HDF5 nuevo"; fi
}

# --- cliente del simulador (identico al de rollouts_extra.sh salvo el numero de episodios) ---
cliente() { # $1 puerto, $2 episodios, $3 semilla
  docker exec -w /workspaces/isaaclab_arena isaaclab_arena-latest bash -c \
   "unset DISPLAY && export HOME=/home/ivines && export ARENA_FIX_BASE=1 && \
    unset OFFICE_GS_LIGHT && export ARENA_VALVE_EPISODE_S=20 && export ARENA_EVAL_RECORD=1 && \
    /isaac-sim/python.sh -u isaaclab_arena/evaluation/policy_runner.py \
      --policy_type isaaclab_arena.policy.action_chunking_client.ActionChunkingClientSidePolicy \
      --remote_host 127.0.0.1 --remote_port $1 --remote_timeout_ms 300000 \
      --enable_cameras --device cuda:0 --num_envs 1 --num_episodes $2 \
      --seed $3 --language_instruction '${INSTRUCCION}' \
      --kit_args='--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0' \
      g1_valve --embodiment g1_wbc_agile_joint --background office_gs"
}

# --- servidores, los dos en la GPU 0 -----------------------------------------------------
srv_gr00t() { # $1 puerto, $2 yaml, $3 log, [$4 policy_type]
  ( cd "$ARENA" && PYTHONPATH=$ARENA:$SCRIPTS LATENCIA_OUT="${LATENCIA_OUT:-}" \
      "$GR00T/.venv/bin/python" -u -m isaaclab_arena.remote_policy.remote_policy_server_runner \
      --policy_type "${4:-isaaclab_arena_gr00t.policy.gr00t_remote_policy.Gr00tRemoteServerSidePolicy}" \
      --host 127.0.0.1 --port "$1" --timeout_ms 300000 \
      --policy_config_yaml_path "$2" --policy_device cuda:0 ) > "$3" 2>&1 &
}
srv_act() { # $1 puerto, $2 checkpoint, $3 stats.json, $4 log, [$5 policy_type]
  ( cd "$ARENA" && PYTHONPATH=$ARENA:$SCRIPTS CUDA_VISIBLE_DEVICES=0 LATENCIA_OUT="${LATENCIA_OUT:-}" \
      "$HOME/venvs/lerobot-act/bin/python" -u -m isaaclab_arena.remote_policy.remote_policy_server_runner \
      --policy_type "${5:-act_remote_policy.ActRemoteServerSidePolicy}" \
      --host 127.0.0.1 --port "$1" --timeout_ms 300000 \
      --checkpoint "$2" --device cuda --stats_json "$3" ) > "$4" 2>&1 &
}

anota "================ NOCHE FINAL: empieza ================"

# =========================================================================================
# ETAPA 1 - Latencia de inferencia (~15 min), con los checkpoints de 100 demos
# =========================================================================================
if ! hecho latencia; then
  for POL in gr00t act; do
    PUERTO=$([ "$POL" = gr00t ] && echo 5581 || echo 5582)
    export LATENCIA_OUT=$LOGS/latencia_${POL}.jsonl
    anota "latencia ${POL}: arrancando servidor cronometrado en ${PUERTO}"
    if [ "$POL" = gr00t ]; then
      srv_gr00t "$PUERTO" "$CFGDIR/g1_valve100_gr00t_closedloop_config.yaml" \
                "$LOGS/lat_srv_${POL}.log" "latencia_wrapper.Gr00tCronometrado"
    else
      srv_act "$PUERTO" "$MOD_DIR/act_valve100_20k/checkpoints/020000/pretrained_model" \
              "$DS/valve_100/lerobot/meta/stats.json" "$LOGS/lat_srv_${POL}.log" \
              "latencia_wrapper.ActCronometrado"
    fi
    PID_S=$!
    if esperar "$LOGS/lat_srv_${POL}.log"; then
      anota "latencia ${POL}: 10 rollouts"
      cliente "$PUERTO" 10 42 > "$LOGS/lat_eval_${POL}.log" 2>&1
      anota "latencia ${POL}: $(wc -l < "$LATENCIA_OUT" 2>/dev/null || echo 0) medidas"
    else
      anota "latencia ${POL}: el servidor no llego a escuchar"
    fi
    kill -9 $PID_S 2>/dev/null; sleep 8
  done
  unset LATENCIA_OUT
  # Solo se marca hecha si hay medidas en los dos ficheros: si no, un relanzamiento se saltaria
  # una etapa que no produjo nada. Paso justo esto con el 504 de Lightwheel el 2026-08-24.
  if [ -s "$LOGS/latencia_gr00t.jsonl" ] && [ -s "$LOGS/latencia_act.jsonl" ]; then
    marca latencia; anota "LATENCIA: hecha"
  else
    anota "LATENCIA: SIN MEDIDAS, no se marca (se reintentara al relanzar)"; exit 1
  fi
fi

# =========================================================================================
# ETAPA 2 - Estadisticas y vista ACT de los subconjuntos (los subconjuntos ya estan creados)
# =========================================================================================
for N in 25 50; do
  if ! hecho prep$N; then
    anota "prep ${N}: estadisticas GR00T"
    # NEW_EMBODIMENT en MAYUSCULAS (tyro usa el nombre del enum aqui). Se borra stats.json antes
    # porque generate_stats se cortocircuita si ya hay uno valido -- heredariamos el de las 100,
    # que es filtrar informacion de datos que este modelo no ha visto.
    rm -f "$DS/valve_${N}/lerobot/meta/stats.json"
    ( cd "$GR00T" && ./.venv/bin/python gr00t/data/stats.py \
        --dataset-path "$DS/valve_${N}/lerobot" --embodiment-tag NEW_EMBODIMENT \
        --modality-config-path "$MOD" ) > "$LOGS/stats_${N}.log" 2>&1 \
      || { anota "prep ${N}: FALLO en estadisticas"; exit 1; }
    anota "prep ${N}: vista ACT"
    rm -rf "$DS/valve_${N}/lerobot_act"
    "$HOME/venvs/lerobot-act/bin/python" "$SCRIPTS/make_lerobot_act_view.py" \
      --src "$DS/valve_${N}/lerobot" --dest "$DS/valve_${N}/lerobot_act" \
      > "$LOGS/actview_${N}.log" 2>&1 || { anota "prep ${N}: FALLO en vista ACT"; exit 1; }
    marca prep$N
    anota "prep ${N}: lista"
  fi
done

# =========================================================================================
# ETAPA 3 - Cuatro entrenamientos, EN SERIE en la GPU 0 (~2 h 30)
# Mismo presupuesto de pasos que la tirada de 100: la unica variable son los datos.
# =========================================================================================
for N in 25 50; do
  if ! hecho tr_gr00t$N; then
    SAL=$MOD_DIR/gr00t_n17_valve${N}_10k
    rm -rf "$SAL"        # experiment.py reanuda sin condiciones: un dir viejo daria CERO pasos
    anota "GR00T @${N}: 10k pasos en la GPU 0"
    ( cd "$GR00T" && NUM_GPUS=1 GLOBAL_BATCH_SIZE=32 MAX_STEPS=10000 SAVE_STEPS=10000 USE_WANDB=0 \
      SHARD_SIZE=512 DATALOADER_NUM_WORKERS=4 EPISODE_SAMPLING_RATE=0.1 \
      CUDA_VISIBLE_DEVICES=0 PATH=$GR00T/.venv/bin:$PATH \
      bash examples/finetune.sh \
        --base-model-path $MOD_DIR/../static_apple_tutorial/gn1x_tuned_static_apple \
        --dataset-path "$DS/valve_${N}/lerobot" \
        --embodiment-tag new_embodiment \
        --modality-config-path "$MOD" \
        --output-dir "$SAL" --save-only-model ) > "$LOGS/train_gr00t_${N}.log" 2>&1
    anota "GR00T @${N}: terminado (codigo $?)"; marca tr_gr00t$N
  fi
done

for N in 25 50; do
  if ! hecho tr_act$N; then
    SAL=$MOD_DIR/act_valve${N}_20k
    rm -rf "$SAL"
    anota "ACT @${N}: 20k pasos en la GPU 0"
    # CUDA_VISIBLE_DEVICES=0 con --policy.device=cuda. NUNCA cuda:1 ni cuda:0 explicito: deja
    # los buffers de normalizacion a std=0 y la red emite ceros exactos sin avisar.
    ( CUDA_VISIBLE_DEVICES=0 "$HOME/venvs/lerobot-act/bin/lerobot-train" \
        --dataset.repo_id=tfm/g1_valve_${N} \
        --dataset.root="$DS/valve_${N}/lerobot_act" \
        --dataset.video_backend=torchcodec \
        --policy.type=act --policy.device=cuda --policy.push_to_hub=false \
        --policy.chunk_size=40 --policy.n_action_steps=40 \
        --batch_size=8 --steps=20000 --save_freq=20000 --log_freq=200 --num_workers=8 \
        --wandb.enable=false --seed=42 \
        --output_dir="$SAL" ) > "$LOGS/train_act_${N}.log" 2>&1
    anota "ACT @${N}: terminado (codigo $?)"; marca tr_act$N
  fi
done

# =========================================================================================
# ETAPA 4 - Cuatro evaluaciones, 100 rollouts, SEMILLA 42 (~3 h 40)
# La 42 es la de la primera tanda de los @100, asi que la curva queda emparejada punto a punto.
# =========================================================================================
for N in 25 50; do
  for POL in gr00t act; do
    if hecho ev_${POL}$N; then continue; fi
    PUERTO=$([ "$POL" = gr00t ] && echo 558 || echo 559)$([ "$N" = 25 ] && echo 3 || echo 4)
    anota "eval ${POL} @${N}: servidor en ${PUERTO}"
    if [ "$POL" = gr00t ]; then
      YAML=$CFGDIR/g1_valve${N}_gr00t_closedloop_config.yaml
      sed "s#^model_path:.*#model_path: $MOD_DIR/gr00t_n17_valve${N}_10k/checkpoint-10000#" \
        "$CFGDIR/g1_valve100_gr00t_closedloop_config.yaml" > "$YAML"
      srv_gr00t "$PUERTO" "$YAML" "$LOGS/srv_${POL}_${N}.log"
    else
      srv_act "$PUERTO" "$MOD_DIR/act_valve${N}_20k/checkpoints/020000/pretrained_model" \
              "$DS/valve_${N}/lerobot/meta/stats.json" "$LOGS/srv_${POL}_${N}.log"
    fi
    PID_S=$!
    if esperar "$LOGS/srv_${POL}_${N}.log"; then
      ls /tmp/isaaclab/logs/*.hdf5 2>/dev/null > "$LOGS/_antes_${POL}_${N}.txt" || : > "$LOGS/_antes_${POL}_${N}.txt"
      anota "eval ${POL} @${N}: 100 rollouts, semilla 42"
      cliente "$PUERTO" 100 42 > "$LOGS/eval_${POL}_${N}.log" 2>&1
      anota "eval ${POL} @${N}: $(grep -aoE 'Metrics: \{[^}]*\}' "$LOGS/eval_${POL}_${N}.log" | tail -1)"
      recoger "$LOGS/_antes_${POL}_${N}.txt" "$RES/${POL}_${N}demos.hdf5"
      [ -s "$RES/${POL}_${N}demos.hdf5" ] && marca ev_${POL}$N \
        || anota "eval ${POL} @${N}: sin HDF5, no se marca"
    else
      anota "eval ${POL} @${N}: el servidor no llego a escuchar"
    fi
    kill -9 $PID_S 2>/dev/null; sleep 8
  done
done

anota "================ NOCHE FINAL: COMPLETA ================"
