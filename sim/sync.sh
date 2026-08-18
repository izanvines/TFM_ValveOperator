#!/usr/bin/env bash
# Mueve el trabajo de la valvula entre este repo y el checkout vivo de IsaacLab-Arena.
#
# Por que existe: la simulacion NO corre desde aqui. Corre desde
# ~/TFM/IsaacLab-Arena, que esta montado dentro del contenedor en
# /workspaces/isaaclab_arena. Este repo guarda la copia versionada; sin un script
# que las mantenga iguales, las dos se separan en silencio y acabas depurando la
# version equivocada.
#
#   ./sync.sh pull   Arena -> repo   (recoge lo que hayas tocado en el checkout vivo)
#   ./sync.sh push   repo  -> Arena  (instala esta version en el checkout vivo)
#   ./sync.sh diff   solo enseña las diferencias, no toca nada
#
# Los ficheros se dividen en dos grupos:
#
#   * NUEVOS: no existen en upstream (isaac-sim/IsaacLab-Arena). Se copian enteros.
#   * MODIFICADOS: si existen en upstream y solo cambian unas lineas. Se guardan como
#     parche `.patch` para que se vea exactamente que se toco y por que, y para poder
#     rebasar sobre una version nueva de Arena sin perder el contexto.
#
# `push` copia los NUEVOS y te dice que parches aplicar; NO aplica parches solo
# porque re-aplicar un parche ya aplicado deja el fichero corrupto sin avisar.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARENA="${ARENA_DIR:-$HOME/TFM/IsaacLab-Arena}"
EXTRAS="${EXTRAS_DIR:-$HOME/eval/arena_extras}"

if [ ! -d "$ARENA" ]; then
  echo "No encuentro el checkout de Arena en $ARENA. Ponlo con ARENA_DIR=..." >&2
  exit 1
fi

# repo_relativo : ruta_dentro_de_arena
NUEVOS=(
  "environments/g1_valve_environment.py:isaaclab_arena_environments/g1_valve_environment.py"
  "assets/valve_rig_arena.usda:isaaclab_arena/assets/usd/valve_rig_arena.usda"
  "assets/valve_rig.usdz:isaaclab_arena/assets/usd/valve_rig.usdz"
  "assets/valve_rig_PROVENANCE.md:isaaclab_arena/assets/usd/valve_rig_PROVENANCE.md"
  "config/g1_valve_config.yaml:isaaclab_arena_gr00t/lerobot/config/g1_valve_config.yaml"
)

# ficheros de upstream que llevan parche local
PARCHEADOS=(
  "isaaclab_arena/assets/object_library.py:object_library.patch"
  "isaaclab_arena/scripts/imitation_learning/teleop.py:teleop.patch"
  "isaaclab_arena/scripts/imitation_learning/record_demos.py:record_demos.patch"
  "isaaclab_arena_environments/cli.py:cli.patch"
  "isaaclab_arena_g1/teleop/g1_pink_locomanipulation_pipeline.py:g1_pink_locomanipulation_pipeline.patch"
  "isaaclab_arena/assets/background_library.py:background_library.patch"
)

SCRIPTS=(stream_valve.py measure_valve_rig.py capture_viewport.py test_valve_torque.py
         inspect_valve_physics.py inspect_hdf5.py hold_pose_policy.py
         record_robotcam_video.py launch_record_valve.sh)

accion="${1:-diff}"

case "$accion" in
  pull)
    for par in "${NUEVOS[@]}"; do
      cp -v "$ARENA/${par#*:}" "$REPO/${par%%:*}"
    done
    ( cd "$ARENA"
      for par in "${PARCHEADOS[@]}"; do
        f="${par%%:*}"; nombre="${par#*:}"
        git diff -- "$f" > "$REPO/patches/$nombre"
      done
      git -C submodules/IsaacLab diff > "$REPO/patches/isaaclab_submodule.patch" || true
    )
    for s in "${SCRIPTS[@]}"; do
      [ -f "$EXTRAS/$s" ] && cp -v "$EXTRAS/$s" "$REPO/scripts/"
    done
    echo "Listo. Revisa 'git status' en el repo."
    ;;

  push)
    for par in "${NUEVOS[@]}"; do
      destino="$ARENA/${par#*:}"
      mkdir -p "$(dirname "$destino")"
      cp -v "$REPO/${par%%:*}" "$destino"
    done
    mkdir -p "$EXTRAS"
    for s in "${SCRIPTS[@]}"; do
      [ -f "$REPO/scripts/$s" ] && cp -v "$REPO/scripts/$s" "$EXTRAS/"
    done
    echo
    echo "Ficheros nuevos copiados. Los PARCHES no se aplican solos -- aplicalos a mano"
    echo "y solo si el checkout esta limpio para ese fichero:"
    for par in "${PARCHEADOS[@]}"; do
      echo "    git -C $ARENA apply $REPO/patches/${par#*:}"
    done
    ;;

  diff)
    for par in "${NUEVOS[@]}"; do
      if ! diff -q "$REPO/${par%%:*}" "$ARENA/${par#*:}" >/dev/null 2>&1; then
        echo "DIFIERE: ${par%%:*}"
      fi
    done
    for s in "${SCRIPTS[@]}"; do
      if [ -f "$EXTRAS/$s" ] && ! diff -q "$REPO/scripts/$s" "$EXTRAS/$s" >/dev/null 2>&1; then
        echo "DIFIERE: scripts/$s"
      fi
    done
    echo "(sin lineas 'DIFIERE' = repo y checkout estan iguales)"
    ;;

  *)
    echo "Uso: $0 {pull|push|diff}" >&2
    exit 1
    ;;
esac
