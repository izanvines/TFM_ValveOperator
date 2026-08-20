#!/usr/bin/env python3
"""Mide la orientacion REAL del splat NuRec dentro del stage que compone Arena.

Existe porque calcular la rotacion sobre el fichero de origen y suponer que Arena la aplica tal
cual no funciono: USD compone en vector-fila, `object_base.py:83` pasa el cuaternion como wxyz
aunque el campo se llame xyzw, y Arena mete el asset bajo `{ENV_REGEX_NS}/...` con su propia pose.
Demasiadas capas para predecirlas. Esto abre el stage ya compuesto y lee la matriz de mundo del
prim `Volume`, que es lo unico que de verdad determina como se ve.

Los angulos se imprimen en el convenio de la UI de Isaac Sim. El control para saber que el
convenio es el bueno esta dentro: /World/gauss tiene autorizado rotateZYX = (-89, 0, 0), asi que
la descomposicion valida es la que devuelve -89 y no +89.
"""
import math

from isaaclab.app import AppLauncher

from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
from isaaclab_arena_environments.cli import add_example_environments_cli_args

parser = get_isaaclab_arena_cli_parser()
add_example_environments_cli_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(vars(args_cli))
simulation_app = app_launcher.app

from isaaclab_arena_environments.cli import get_arena_builder_from_cli  # noqa: E402
from pxr import Gf, Usd, UsdGeom  # noqa: E402


def euler_ui(M):
    """Euler XYZ en el convenio que muestra la UI (USD es vector-fila -> transponer)."""
    R = [[M[j][i] for j in range(3)] for i in range(3)]
    sy = -R[2][0]
    if abs(sy) < 0.999999:
        y = math.asin(sy)
        x = math.atan2(R[2][1], R[2][2])
        z = math.atan2(R[1][0], R[0][0])
    else:
        y = math.asin(sy)
        x = math.atan2(-R[1][2], R[1][1])
        z = 0.0
    return [round(math.degrees(v), 3) for v in (x, y, z)]


def main():
    env = get_arena_builder_from_cli(args_cli).make_registered()
    env.reset()
    stage = env.unwrapped.sim.stage if hasattr(env.unwrapped.sim, "stage") else Usd.Stage.GetCurrent()
    try:
        import omni.usd

        stage = omni.usd.get_context().get_stage()
    except Exception:
        pass

    print("\n=== prims NuRec en el stage compuesto ===", flush=True)
    encontrados = 0
    for p in stage.Traverse():
        if p.GetTypeName() != "Volume":
            continue
        encontrados += 1
        M = UsdGeom.Xformable(p).ComputeLocalToWorldTransform(0)
        R = Gf.Matrix4d(M)
        R.SetTranslateOnly(Gf.Vec3d(0, 0, 0))
        t = M.ExtractTranslation()
        print(f"  {p.GetPath()}")
        print(f"     rotacion en MUNDO (Euler XYZ, convenio UI): {euler_ui(R)}")
        print(f"     traslacion en MUNDO: [{t[0]:.4f}, {t[1]:.4f}, {t[2]:.4f}]")
        # cadena de padres, para ver quien aporta que
        q = p
        while q and q.GetPath() != stage.GetPseudoRoot().GetPath():
            L = UsdGeom.Xformable(q).GetLocalTransformation(0) if q.IsA(UsdGeom.Xformable) else None
            if L is not None:
                Rl = Gf.Matrix4d(L)
                Rl.SetTranslateOnly(Gf.Vec3d(0, 0, 0))
                tl = L.ExtractTranslation()
                print(f"       {str(q.GetPath()):60s} rot={euler_ui(Rl)} tras=[{tl[0]:.3f},{tl[1]:.3f},{tl[2]:.3f}]")
            q = q.GetParent()
    if not encontrados:
        print("  NINGUNO. El asset no ha cargado como NuRec.")
    print("=== fin ===", flush=True)
    simulation_app.close()


main()
