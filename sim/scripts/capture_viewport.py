# Captura el viewport de Kit a PNG. Sirve para saber si lo que el livestream
# transmite (el framebuffer de la aplicacion) lleva pixeles o esta vacio, sin
# depender de un cliente WebRTC para averiguarlo.
#
# Se lanza con --viz kit igual que el stream, pero SIN --livestream (para no
# pelearse por el puerto 49100 con la sesion que este emitiendo).

from isaaclab.app import AppLauncher

from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
from isaaclab_arena_environments.cli import add_example_environments_cli_args

parser = get_isaaclab_arena_cli_parser()
parser.add_argument("--out", type=str, default="/eval/viewport_check.png")
parser.add_argument("--settle", type=int, default=60)
parser.add_argument("--cam_eye", type=str, default="2.2,-1.9,1.8")
parser.add_argument("--cam_target", type=str, default="0.35,0.0,1.0")
add_example_environments_cli_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(vars(args_cli))
simulation_app = app_launcher.app

import torch  # noqa: E402

from isaaclab_arena_environments.cli import get_arena_builder_from_cli  # noqa: E402


def log(m):
    print(m, flush=True)


def _xyz(t):
    p = [float(x) for x in t.split(",")]
    return (p[0], p[1], p[2])


def main():
    env = get_arena_builder_from_cli(args_cli).make_registered()
    env.reset()
    unwrapped = env.unwrapped
    sim = unwrapped.sim

    try:
        sim.set_camera_view(_xyz(args_cli.cam_eye), _xyz(args_cli.cam_target))
    except Exception as exc:  # noqa: BLE001
        log(f"!! set_camera_view: {type(exc).__name__}: {exc}")

    a = torch.zeros((unwrapped.num_envs, unwrapped.action_manager.total_action_dim), device=unwrapped.device)
    a[:, 2:5] = torch.tensor([0.22, 0.20, 0.05], device=unwrapped.device)
    a[:, 5:9] = torch.tensor([0.0, 0.0, 0.0, 1.0], device=unwrapped.device)
    a[:, 9:12] = torch.tensor([0.22, -0.20, 0.05], device=unwrapped.device)
    a[:, 12:16] = torch.tensor([0.0, 0.0, 0.0, 1.0], device=unwrapped.device)
    a[:, 19] = 0.75
    for _ in range(args_cli.settle):
        env.step(a)
        sim.render()

    try:
        from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport

        vp = get_active_viewport()
        log(f">> viewport activo: {vp}")
        if vp is None:
            log("!! NO HAY VIEWPORT ACTIVO -> el livestream transmitiria un buffer vacio")
        else:
            capture_viewport_to_file(vp, file_path=args_cli.out)
            for _ in range(20):
                sim.render()
            log(f">> capturado en {args_cli.out}")
    except Exception as exc:  # noqa: BLE001
        log(f"!! captura fallida: {type(exc).__name__}: {exc}")

    env.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
