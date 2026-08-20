#!/usr/bin/env python3
"""Comprueba que el sorteo de disposicion y posicion de la valvula hace lo que dice.

Resetea el entorno N veces y saca la pose de la valvula en cada reset, clasificandola por
disposicion segun su cuaternion. Es la prueba de aceptacion de la aleatorizacion: sin esto uno se
queda con que "parece que cambia".

Lo que hay que ver:
  * las DOS disposiciones aparecen, en proporcion cercana al 50/50;
  * dentro de cada una, la posicion varia dentro del jitter pedido y no mas;
  * ningun sorteo deja la rueda fuera del alcance comodo del G1.
"""
import math
from collections import Counter

from isaaclab.app import AppLauncher

from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
from isaaclab_arena_environments.cli import add_example_environments_cli_args, get_arena_builder_from_cli

parser = get_isaaclab_arena_cli_parser()
parser.add_argument("--resets", type=int, default=20)
add_example_environments_cli_args(parser)
args_cli = parser.parse_args()
app_launcher = AppLauncher(vars(args_cli))
simulation_app = app_launcher.app

import torch  # noqa: E402


def _t(x):
    """IsaacLab puede devolver `wp.array` (backend Newton/Warp) en vez de tensores torch."""
    try:
        import warp as wp

        if isinstance(x, wp.array):
            return wp.to_torch(x)
    except Exception:
        pass
    return x

from isaaclab_arena_environments.g1_valve_environment import VALVE_JITTER_XYZ, VALVE_LAYOUTS  # noqa: E402


def clasificar(q_xyzw) -> str:
    """Devuelve el nombre de la disposicion cuyo cuaternion mas se parece."""
    mejor, mejor_d = "?", 9e9
    for nombre, cfg in VALVE_LAYOUTS.items():
        ref = cfg["quat_xyzw"]
        # |producto escalar| ~ 1 significa la misma rotacion (q y -q son la misma)
        d = 1.0 - abs(sum(a * b for a, b in zip(q_xyzw, ref)))
        if d < mejor_d:
            mejor, mejor_d = nombre, d
    return mejor if mejor_d < 1e-3 else f"?({mejor_d:.3f})"


def main():
    env = get_arena_builder_from_cli(args_cli).make_registered()
    unwrapped = env.unwrapped
    valvula = unwrapped.scene["valve"]

    print(f"\njitter configurado: {VALVE_JITTER_XYZ} m")
    print(f"{'reset':>6}  {'disposicion':<12}{'x':>9}{'y':>9}{'z':>9}   rueda_z")
    cuenta, poses = Counter(), []
    for i in range(args_cli.resets):
        env.reset()
        raiz = _t(valvula.data.root_pos_w)[0].tolist()
        # El cuaternion vuelve EN EL MISMO ORDEN en que se escribio en `quat_xyzw` -- medido el
        # 2026-08-20: con la disposicion cenital configurada como (-0.5,-0.5,0.5,0.5), root_quat_w
        # devuelve exactamente [-0.5,-0.5,0.5,0.5]. Reordenarlo suponiendo wxyz, que es lo que
        # documenta IsaacLab, rompe la clasificacion. Se compara tal cual.
        q_xyzw = tuple(_t(valvula.data.root_quat_w)[0].tolist())
        nombre = clasificar(q_xyzw)
        # la rueda es el segundo cuerpo; su pose real, no derivada
        rueda_z = float(_t(valvula.data.body_pos_w)[0, 1, 2])
        cuenta[nombre] += 1
        poses.append((nombre, raiz))
        print(f"{i + 1:>6}  {nombre:<12}{raiz[0]:>9.3f}{raiz[1]:>9.3f}{raiz[2]:>9.3f}   {rueda_z:>7.3f}")

    print("\nreparto:", dict(cuenta))
    for nombre in VALVE_LAYOUTS:
        xs = [p for n, p in poses if n == nombre]
        if not xs:
            print(f"  {nombre}: NO HA SALIDO NINGUNA VEZ")
            continue
        base = VALVE_LAYOUTS[nombre]["pos"]
        for eje, idx in (("x", 0), ("y", 1), ("z", 2)):
            v = [p[idx] for p in xs]
            desv = max(abs(a - base[idx]) for a in v)
            tope = VALVE_JITTER_XYZ[idx]
            marca = "ok" if desv <= tope + 1e-6 else "FUERA DEL JITTER"
            print(f"  {nombre:<9} {eje}: rango [{min(v):+.3f}, {max(v):+.3f}]  "
                  f"desviacion max {desv:.3f} / {tope:.3f}  {marca}")
    simulation_app.close()


main()
