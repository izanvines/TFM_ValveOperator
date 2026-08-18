# Comprueba si el volante gira con un par realista de la mano del G1.
#
# El rig venia con `drive:angular:physics:damping = 100` (freno viscoso: par = 100*w),
# lo que exigia ~1000 N*m para 10 deg/s. `valve_rig_arena.usda` lo baja. Este script
# mide si el nuevo valor deja girar la rueda con el par que un brazo puede dar.
#
# Aplica un par puro alrededor del eje del joint sobre el cuerpo del volante y mide
# la velocidad angular y el angulo alcanzado.

import math

from isaaclab.app import AppLauncher

from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
from isaaclab_arena_environments.cli import add_example_environments_cli_args

parser = get_isaaclab_arena_cli_parser()
parser.add_argument("--torque", type=float, default=1.5, help="par aplicado en N*m")
parser.add_argument("--steps", type=int, default=150)
add_example_environments_cli_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(vars(args_cli))
simulation_app = app_launcher.app

import torch  # noqa: E402

from isaaclab_arena_environments.cli import get_arena_builder_from_cli  # noqa: E402


def log(m):
    print(m, flush=True)


def _t(x):
    try:
        import warp as wp

        if isinstance(x, wp.array):
            return wp.to_torch(x)
    except Exception:
        pass
    return x


def main():
    env = get_arena_builder_from_cli(args_cli).make_registered()
    env.reset()
    u = env.unwrapped
    valve = u.scene["valve"]

    dev = u.device
    nombres = list(valve.body_names)
    rueda = next(i for i, b in enumerate(nombres) if "50_AL" in b or "wheel" in b.lower())
    log(f">> cuerpo del volante: [{rueda}] {nombres[rueda]}")

    amort = _t(valve.data.joint_damping)[0]
    rigid = _t(valve.data.joint_stiffness)[0]
    log(f">> joint_damping leido en sim = {[float(x) for x in amort]}")
    log(f">> joint_stiffness leido en sim = {[float(x) for x in rigid]}")

    # accion de mantener al robot de pie, para que no se caiga durante el test
    a = torch.zeros((u.num_envs, u.action_manager.total_action_dim), device=dev)
    a[:, 2:5] = torch.tensor([0.22, 0.20, 0.05], device=dev)
    a[:, 5:9] = torch.tensor([0.0, 0.0, 0.0, 1.0], device=dev)
    a[:, 9:12] = torch.tensor([0.22, -0.20, 0.05], device=dev)
    a[:, 12:16] = torch.tensor([0.0, 0.0, 0.0, 1.0], device=dev)
    a[:, 19] = 0.75

    # El eje del joint local +Z acaba apuntando a -X en mundo (medido, ver
    # g1_valve_environment.py). Un par puro alrededor de X mueve el volante.
    forces = torch.zeros((u.num_envs, 1, 3), device=dev)
    torques = torch.zeros((u.num_envs, 1, 3), device=dev)
    torques[:, 0, 0] = args_cli.torque

    log(f">> aplicando {args_cli.torque} N*m alrededor de X sobre el volante, {args_cli.steps} pasos")
    for i in range(args_cli.steps):
        valve.set_external_force_and_torque(forces, torques, body_ids=[rueda])
        env.step(a)
        if (i + 1) % 30 == 0:
            q = float(_t(valve.data.joint_pos)[0, 0])
            w = float(_t(valve.data.joint_vel)[0, 0])
            log(f"   paso {i+1:3d}: angulo {math.degrees(q):7.2f} deg   vel {math.degrees(w):7.2f} deg/s")

    q = float(_t(valve.data.joint_pos)[0, 0])
    w = float(_t(valve.data.joint_vel)[0, 0])
    log("\n" + "=" * 60)
    log(f"par aplicado        : {args_cli.torque} N*m")
    log(f"angulo alcanzado    : {math.degrees(q):.2f} deg")
    log(f"velocidad final     : {math.degrees(w):.2f} deg/s")
    log(f"openness            : {math.degrees(q)/360:.3f}  (exito si > 0.5)")
    if math.degrees(q) < 1.0:
        log("VEREDICTO: SIGUE BLOQUEADA")
    else:
        log("VEREDICTO: GIRA")
    log("=" * 60)
    env.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
