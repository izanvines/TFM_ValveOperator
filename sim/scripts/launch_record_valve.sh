#!/bin/bash
# Grabacion de demostraciones de `g1_valve` por teleoperacion XR, con el fondo de la
# oficina (Gaussian Splatting / NuRec) y la base del robot congelada.
#
# Hermano de `launch_teleop_office.sh`. Lo que cambia respecto a aquel:
#
#   * `record_demos.py` en vez de `teleop.py`.
#   * **CON `--enable_cameras`**, que aqui SI se puede y ademas hace falta. En `teleop.py`
#     era imposible (llama a `remove_camera_configs()` de forma incondicional cuando hay
#     XR y revienta el termino de observacion). `record_demos.py:217` en cambio solo las
#     quita `if not args_cli.enable_cameras`, y su linea 226 activa
#     `ArenaEnvRecorderManagerCfg()`, que es la que escribe la camara en el HDF5.
#     Es LA camara del dataset: lo que se salga de ese encuadre no existe para la politica.
#   * **`ARENA_STATIC_BASE=1`**: congela los 4 canales de locomocion a `[0, 0, 0, 0.72]`.
#     Sin esto, cada roce del joystick entra en el dataset como una orden de caminar y la
#     politica aprende a imitarla. Ojo: NO vale con poner los cuatro a cero, porque
#     `hip_height` es una altura ABSOLUTA en metros (neutro 0.72, recorte a [0.4, 1.0]);
#     un cero ahi es "agachate hasta el suelo" y tumba el robot. Y tampoco vale hacerlo
#     por configuracion: `rot_vel_z` sale como el valor CRUDO del thumbstick derecho
#     (`rotation_scale` escala la integracion de la altura, no la rotacion).
#   * **`ARENA_XR_ANTIALIASING=""`**: `record_demos.py:219` asigna
#     `antialiasing_mode = "DLSS"` de forma incondicional cuando hay XR, igual que hacia
#     `teleop.py`. Esa asignacion acaba en `rep.settings.set_render_rtx_realtime()`, cuya
#     PRIMERA linea es `carb_settings("/rtx/rendermode", "RealTimePathTracing")`, o sea
#     que pisa nuestro `RaytracedLighting` DESPUES de los kit_args y deja el splat
#     sobreexpuesto y con huecos. Requiere el parche equivalente al de `teleop.py`.
#
# DEPENDE DE TRES PARCHES EN EL REPO (bind-mount, `/workspaces/isaaclab_arena`):
#   1. `isaaclab_arena_g1/teleop/g1_pink_locomanipulation_pipeline.py` -> lee ARENA_STATIC_BASE
#   2. `isaaclab_arena/scripts/imitation_learning/record_demos.py`     -> lee ARENA_XR_ANTIALIASING
#   3. `isaaclab_arena_environments/g1_valve_environment.py`           -> episodio de 15 s a 8 s
# Sin ellos el script ARRANCA IGUAL, pero: el robot podra caminar, el splat saldra
# sobreexpuesto, y los episodios duraran 15 s (~750 pasos, por encima de los 200-400 que
# recomienda la doc de NVIDIA).
#
# PREREQUISITO: runtime de CloudXR en marcha.
#   docker exec -it -e HOME=/home/ivines isaaclab_arena-latest \
#     /isaac-sim/python.sh -m isaacteleop.cloudxr
#
# Variables: DATASET_DIR, DATASET_FILE, NUM_DEMOS, ACTIVE_GPU, SIM_DEVICE, MONITOR,
# BACKGROUND, y las de imagen (RENDER_MODE, TONEMAP_OP, NUREC_HINTS, FABRIC_TRANSFORMS,
# OFFICE_GS_*).

set -u

CLOUDXR_ENV=/home/ivines/.cloudxr/run/cloudxr.env
if [ ! -f "${CLOUDXR_ENV}" ]; then
  echo "FALTA ${CLOUDXR_ENV}. Arranca antes el runtime de CloudXR:"
  echo "    docker exec -it -e HOME=/home/ivines isaaclab_arena-latest \\"
  echo "      /isaac-sim/python.sh -m isaacteleop.cloudxr"
  exit 1
fi
# shellcheck disable=SC1090
source "${CLOUDXR_ENV}"

unset DISPLAY
export HOME=/home/ivines
cd /workspaces/isaaclab_arena || exit 1

# --- Dataset -----------------------------------------------------------------
# Convencion de la doc de NVIDIA: un directorio por tarea. Cada SESION escribe su propio
# fichero; luego se unen con `merge_demos.py`, que valida que coincidan format_version,
# forma de la accion, claves de observacion y geometria de camara.
export DATASET_DIR=${DATASET_DIR:-/datasets/isaaclab_arena/g1_valve}
mkdir -p "${DATASET_DIR}" || exit 1
SESION=${DATASET_FILE:-${DATASET_DIR}/g1_valve_session_$(date +%Y%m%d_%H%M%S).hdf5}
NUM_DEMOS=${NUM_DEMOS:-20}

if [ -e "${SESION}" ]; then
  echo "AVISO: ${SESION} ya existe. Usa DATASET_FILE=... para no pisarlo."
  exit 1
fi

# --- Fondo de la oficina (splat) ---------------------------------------------
export OFFICE_GS_USD=${OFFICE_GS_USD:-/datasets/office_video_aligned.usda}
export OFFICE_GS_SCALE=${OFFICE_GS_SCALE:-1.0}
export OFFICE_GS_POS=${OFFICE_GS_POS:-0,0,0}
export OFFICE_GS_ROT=${OFFICE_GS_ROT:-0,0,0,1}
export OFFICE_GS_LIGHT=${OFFICE_GS_LIGHT:-300}

export PYTHONUNBUFFERED=1
export PYTHONPATH="/eval/arena_extras:${PYTHONPATH:-}"

# Base congelada y sin DLSS (ver cabecera).
export ARENA_STATIC_BASE=${ARENA_STATIC_BASE:-1}
export ARENA_XR_ANTIALIASING="${ARENA_XR_ANTIALIASING-}"

# Guardia de red: `object_library.py` llama a la API de Lightwheel al IMPORTAR, y un
# parpadeo mata el arranque despues de minutos de carga.
for intento in 1 2 3 4 5; do
  if timeout 60 /isaac-sim/python.sh -c "
from lightwheel_sdk.loader import object_loader
object_loader.acquire_by_registry(registry_type='fixtures', file_name='Microwave039', file_type='USD')
" >/dev/null 2>&1; then
    echo "[guardia] Lightwheel OK en el intento ${intento}"
    break
  fi
  echo "[guardia] Lightwheel no responde (intento ${intento}/5), reintento en 15 s"
  [ "${intento}" = "5" ] && { echo "[guardia] ABORTADO: la API de Lightwheel no responde."; exit 1; }
  sleep 15
done

# Ajustes de imagen. Kit solo aplica los `renderSettings` del `customLayerData` de la capa
# RAIZ y el splat entra referenciado, asi que hay que pasarlos por linea de comandos.
# FABRIC_TRANSFORMS va a **true** en XR (al reves que sin XR): el NuRec solo llega a ser
# el rprim `OmniNuRecVolume` por la via de Fabric, y las poses del casco se actualizan
# por ahi cada frame.
KIT_IMAGEN="--/renderer/multiGpu/enabled=false --/renderer/activeGpu=${ACTIVE_GPU:-0} \
--/persistent/xr/profile/ar/renderQuality=${XR_RENDER_QUALITY:-performance} \
--/rtx/rendermode=${RENDER_MODE:-RaytracedLighting} \
--/rtx/post/tonemap/op=${TONEMAP_OP:-2} \
--/omni/rtx/nre/compositing/rendererHints=${NUREC_HINTS:-0} \
--/rtx/hydra/readTransformsFromFabricInRenderDelegate=${FABRIC_TRANSFORMS:-true}"

# Monitor en 3a persona. Hace falta para pulsar la pestana XR (con `--viz kit` no eres
# headless, asi que `/isaaclab/xr/auto_start` queda en False y la sesion XR NO arranca
# sola: `app_launcher.py:1071`). Cuesta un producto de render entero, asi que en cuanto
# la sesion este en marcha conviene cerrar el cliente del monitor.
if [ "${MONITOR:-1}" = "1" ]; then
  MONITOR_ARGS="--livestream 2"
  KIT_MONITOR="--/exts/omni.kit.livestream.app/primaryStream/allowDynamicResize=${DYNAMIC_RESIZE:-false} \
--/exts/omni.kit.livestream.app/primaryStream/targetFps=${TARGET_FPS:-60} \
--/exts/omni.kit.livestream.app/primaryStream/signalPort=${SIGNAL_PORT:-49120} \
--/exts/omni.kit.livestream.app/primaryStream/streamPort=${STREAM_PORT:-48020} \
--/exts/omni.kit.livestream.app/primaryStream/publicIp=${STREAM_PUBLIC_IP:-172.22.41.51}"
else
  MONITOR_ARGS=""
  KIT_MONITOR=""
fi

echo "[record] dataset  : ${SESION}"
echo "[record] demos    : ${NUM_DEMOS}"
echo "[record] base fija: ARENA_STATIC_BASE=${ARENA_STATIC_BASE}"
echo "[record] fondo    : ${BACKGROUND:-office_gs}"

exec /isaac-sim/python.sh isaaclab_arena/scripts/imitation_learning/record_demos.py \
  --viz kit \
  --device "${SIM_DEVICE:-cuda}" \
  --enable_cameras \
  --dataset_file "${SESION}" \
  --num_demos "${NUM_DEMOS}" \
  --num_success_steps 10 \
  --disable_full_sim_buffer_reset \
  ${MONITOR_ARGS} \
  --kit_args="${KIT_IMAGEN} ${KIT_MONITOR}" \
  g1_valve \
  --teleop_device openxr \
  --embodiment g1_wbc_agile_pink \
  --background "${BACKGROUND:-office_gs}"
