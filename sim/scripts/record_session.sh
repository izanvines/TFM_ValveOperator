#!/bin/bash
# Graba una sesion de demostraciones de `g1_valve` por teleoperacion XR.
#
#   ./record_session.sh 03          # graba sesion_03.hdf5, 25 demos
#   NUM_DEMOS=40 ./record_session.sh 04
#
# Es EXACTAMENTE lo que corrio la sesion 02 del 2026-08-21, congelado en un fichero para que
# las sesiones no se vayan separando unas de otras. Cambiar algo aqui cambia el dataset a
# mitad, que es justo lo que hay que evitar: la politica no distingue "el operador mejoro"
# de "el entorno cambio".
#
# PREREQUISITO: el runtime de CloudXR corriendo (deja el 49100 y el 48322 escuchando).
#   docker exec -e HOME=/home/ivines isaaclab_arena-latest \
#     /isaac-sim/python.sh -m isaacteleop.cloudxr --accept-eula
#
# Por que cada cosa esta como esta -- el detalle largo esta en LAUNCH.md, modo C:
#   --device cpu        fisica en GPU + XR + camaras = CUDA illegal access a los 23 s, siempre
#   --enable_cameras    es lo que escribe la camara en el HDF5, y esa camara ES la entrada
#                       de la politica; en teleop.py esto no se puede
#   --viz kit           sin el no hay viewport (receta de referencia de NVIDIA)
#   ARENA_STATIC_BASE   congela los 4 canales de locomocion; sin esto cada roce del joystick
#                       entra en el dataset como una orden de caminar
#   ARENA_FIX_BASE      pelvis clavada; sin esto el par de reaccion del volante gira el robot
#   ARENA_XR_ANTIALIASING=""  evita que teleop/record fuercen RealTimePathTracing
#   sin ARENA_VALVE_LAYOUT    -> sorteo 50/50 frontal/cenital. NO lo fijes en las sesiones
#                       definitivas: la aleatorizacion es parte del dataset
#   EPISODE_S=30        el episodio termina solo al conseguir el exito, asi que un presupuesto
#                       largo solo alarga los fallos; corto convierte un casi-exito en timeout,
#                       y una demo que expira NO SE ESCRIBE
set -u

SESION="${1:?uso: record_session.sh <numero de sesion, p.ej. 03>}"
DESTINO="/datasets/isaaclab_arena/g1_valve/sesion_${SESION}.hdf5"

if [ -e "${HOME}/datasets/isaaclab_arena/g1_valve/sesion_${SESION}.hdf5" ]; then
  echo "ABORTADO: sesion_${SESION}.hdf5 ya existe. record_demos.py no sobreescribe."
  exit 1
fi
if ! ss -tln | grep -q ':49100'; then
  echo "ABORTADO: CloudXR no esta escuchando en el 49100. Arrancalo primero."
  exit 1
fi

docker exec -w /workspaces/isaaclab_arena isaaclab_arena-latest bash -c \
 "source /home/ivines/.cloudxr/run/cloudxr.env && unset DISPLAY && export HOME=/home/ivines && \
  export ARENA_STATIC_BASE=1 && export ARENA_FIX_BASE=1 && export ARENA_XR_ANTIALIASING='' && \
  export ARENA_VALVE_EPISODE_S=${EPISODE_S:-30} && unset ARENA_VALVE_LAYOUT && \
  /isaac-sim/python.sh -u isaaclab_arena/scripts/imitation_learning/record_demos.py \
    --viz kit --device cpu --enable_cameras --livestream 2 \
    --dataset_file ${DESTINO} \
    --num_demos ${NUM_DEMOS:-25} --num_success_steps 10 --disable_full_sim_buffer_reset \
    --kit_args='--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0 --/persistent/xr/profile/ar/renderQuality=performance --/rtx/rendermode=RaytracedLighting --/rtx/post/tonemap/op=2 --/exts/omni.kit.livestream.app/primaryStream/signalPort=49120 --/exts/omni.kit.livestream.app/primaryStream/streamPort=48020 --/exts/omni.kit.livestream.app/primaryStream/publicIp=172.22.41.51' \
    g1_valve --teleop_device openxr --embodiment g1_wbc_agile_pink --background none"
