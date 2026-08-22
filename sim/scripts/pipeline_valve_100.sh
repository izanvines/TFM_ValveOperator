#!/bin/bash
# Cadena completa del dataset de 100 demos, para correr DESACOPLADA dentro del contenedor.
#
# Por que existe: `docker exec` sin `-d` muere con su cliente. Un re-render de 12 minutos
# lanzado desde una shell que se cierra se queda a medias -- pasó el 2026-08-21 a 7/25.
# Este script se lanza con `docker exec -d` y sobrevive a la sesion que lo arranca.
#
#   docker exec -d isaaclab_arena-latest bash /eval/arena_extras/pipeline_valve_100.sh
#
# Progreso en /eval/logs/pipeline_valve_100.log. Cada etapa escribe un centinela en
# /eval/logs/etapa_*.ok para poder retomar sin repetir lo ya hecho.
set -u
unset DISPLAY
export HOME=/home/ivines
unset OFFICE_GS_LIGHT          # 3000, el valor con el que se genero TODO el dataset
cd /workspaces/isaaclab_arena || exit 1

LOGS=/eval/logs
mkdir -p "$LOGS"
REG="$LOGS/pipeline_valve_100.log"
DIR=/datasets/isaaclab_arena/g1_valve

anota() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$REG"; }

# --- Etapa 1: re-render de las sesiones que falten -------------------------------------
for S in 04 05; do
  if [ -f "$LOGS/etapa_rerender_${S}.ok" ]; then anota "rerender ${S}: ya hecho, salto"; continue; fi
  rm -f "${DIR}/sesion_${S}_office.hdf5"
  anota "rerender ${S}: empieza"
  /isaac-sim/python.sh -u /eval/arena_extras/rerender_demos.py \
      --dataset_file "${DIR}/sesion_${S}.hdf5" \
      --output_file  "${DIR}/sesion_${S}_office.hdf5" \
      --enable_cameras --device cuda:0 \
      g1_valve --background office_gs --embodiment g1_wbc_agile_pink \
      > "$LOGS/rerender_${S}.log" 2>&1
  n=$(grep -acE '^\[rerender\] +[0-9]+/25' "$LOGS/rerender_${S}.log")
  perdidas=$(grep -acE 'PERDIDA' "$LOGS/rerender_${S}.log")
  anota "rerender ${S}: ${n}/25 reproducidas, ${perdidas} perdidas"
  if [ "$n" != "25" ]; then anota "rerender ${S}: INCOMPLETO, abandono"; exit 1; fi
  touch "$LOGS/etapa_rerender_${S}.ok"
done

# --- Etapa 2: fusionar las cuatro sesiones ---------------------------------------------
if [ ! -f "$LOGS/etapa_merge.ok" ]; then
  anota "merge: empieza"
  /isaac-sim/python.sh isaaclab_arena/scripts/imitation_learning/merge_demos.py \
      "${DIR}/sesion_02_office.hdf5" "${DIR}/sesion_03_office.hdf5" \
      "${DIR}/sesion_04_office.hdf5" "${DIR}/sesion_05_office.hdf5" \
      -o "${DIR}/valve_100.hdf5" --overwrite > "$LOGS/merge.log" 2>&1 || { anota "merge: FALLO"; exit 1; }
  anota "merge: hecho"
  touch "$LOGS/etapa_merge.ok"
fi

# --- Etapa 3: convertir a GR00T-LeRobot -------------------------------------------------
# `rm -rf` del destino antes: si existe, dataset_config.py:154 llama a un input() pelado y
# cuelga. El </dev/null lo convierte en EOFError si aun asi se llegara a el.
if [ ! -f "$LOGS/etapa_convert.ok" ]; then
  anota "conversion: empieza"
  rm -rf "${DIR}/valve_100"
  /isaac-sim/python.sh -u isaaclab_arena_gr00t/lerobot/convert_hdf5_to_lerobot.py \
      --yaml_file isaaclab_arena_gr00t/lerobot/config/g1_valve_config.yaml \
      < /dev/null > "$LOGS/convert.log" 2>&1 || { anota "conversion: FALLO"; exit 1; }
  # Lo escribe root; GR00T necesita escribir estadisticas DENTRO al entrenar.
  chown -R 1003:1003 "${DIR}/valve_100"
  anota "conversion: hecha"
  touch "$LOGS/etapa_convert.ok"
fi

anota "PIPELINE COMPLETO"
