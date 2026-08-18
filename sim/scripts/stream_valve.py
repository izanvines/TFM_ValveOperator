# Mantiene `g1_valve` corriendo indefinidamente para poder VERLO por WebRTC.
#
# Por que existe: `policy_runner.py --policy_type zero_action` no sirve de escaparate
# (el indice [19] es base_height_cmd y un cero sienta al robot en el suelo), y ademas
# termina a los N pasos. Esto se queda vivo hasta que lo mates.
#
# Los dos detalles que hacian que el stream saliera NEGRO:
#
#   1. `/isaaclab/has_gui` NUNCA se escribe en esta version de Isaac Lab
#      (`app_launcher.py` solo escribe `/isaaclab/render/offscreen`,
#      `/isaaclab/render/active_viewport`, `/isaaclab/xr/*`). Por tanto
#      `SimulationContext.is_rendering` es False cuando se lanza con
#      `--livestream N` a secas, y el bucle de `ManagerBasedRLEnv.step()` (linea 194:
#      `if ... and is_rendering: self.sim.render()`) NO renderiza nunca. Kit no
#      actualiza su framebuffer y el livestream transmite un buffer vacio.
#      -> Aqui se llama a `sim.render()` explicitamente en cada paso, ademas de
#         lanzar con `--enable_cameras` (que pone `_offscreen_render=True` porque
#         livestream fuerza headless, `app_launcher.py:815-817`).
#
#   2. El RTX necesita un fotograma de calentamiento: el render 0 sale a negro
#      (max=0) y a partir del 1 ya trae pixeles (max=245). Medido con
#      `grab_frame2.py`. Por eso se renderizan varios fotogramas antes de anunciar
#      que el stream esta listo.
#
# Uso:
#   unset DISPLAY && export HOME=/home/ivines && export PUBLIC_IP=<ip del server>
#   /isaac-sim/python.sh -u /eval/arena_extras/stream_valve.py \
#     --livestream 1 --enable_cameras --device cuda:0 g1_valve --background none

from isaaclab.app import AppLauncher

from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
from isaaclab_arena_environments.cli import add_example_environments_cli_args

parser = get_isaaclab_arena_cli_parser()
parser.add_argument("--steps", type=int, default=0, help="0 = infinito, hasta que lo mates")
parser.add_argument("--cam_eye", type=str, default="2.2,-1.9,1.8", help="posicion de la camara del viewport")
parser.add_argument("--cam_target", type=str, default="0.35,0.0,1.0", help="a donde mira la camara")
add_example_environments_cli_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(vars(args_cli))
simulation_app = app_launcher.app

import torch  # noqa: E402

from isaaclab_arena_environments.cli import get_arena_builder_from_cli  # noqa: E402


def log(msg: str) -> None:
    print(msg, flush=True)


def _hold_action(unwrapped):
    """Pose estable de pie. Mismos valores que `hold_pose_policy.py` / `measure_valve_rig.py`."""
    dev = unwrapped.device
    a = torch.zeros((unwrapped.num_envs, unwrapped.action_manager.total_action_dim), device=dev)
    a[:, 2:5] = torch.tensor([0.22, 0.20, 0.05], device=dev)  # muneca izq
    a[:, 5:9] = torch.tensor([0.0, 0.0, 0.0, 1.0], device=dev)  # quat xyzw
    a[:, 9:12] = torch.tensor([0.22, -0.20, 0.05], device=dev)  # muneca der
    a[:, 12:16] = torch.tensor([0.0, 0.0, 0.0, 1.0], device=dev)
    a[:, 19] = 0.75  # base_height_cmd
    return a


def _xyz(texto: str):
    partes = [float(p) for p in texto.split(",")]
    return (partes[0], partes[1], partes[2])


def main() -> None:
    log(">> construyendo entorno")
    env = get_arena_builder_from_cli(args_cli).make_registered()
    log(">> reset")
    env.reset()

    unwrapped = env.unwrapped
    sim = unwrapped.sim

    # Encuadre del viewport. Sin esto el stream muestra el `ViewerCfg` por defecto, que
    # deja el suelo como un rombo gris a lo lejos sin robot ni valvula a la vista.
    try:
        sim.set_camera_view(_xyz(args_cli.cam_eye), _xyz(args_cli.cam_target))
        log(f">> camara del viewport: eye={args_cli.cam_eye} target={args_cli.cam_target}")
    except Exception as exc:  # noqa: BLE001
        log(f"!! no se ha podido mover la camara ({type(exc).__name__}: {exc}); se usa la de por defecto")

    # Calentamiento del RTX: el primer render sale negro.
    for _ in range(8):
        sim.render()
    log(">> RTX calentado")

    accion = _hold_action(unwrapped)
    log(">> STREAM LISTO - conectate ya con el cliente WebRTC")

    paso = 0
    try:
        while simulation_app.is_running():
            env.step(accion)
            sim.render()  # imprescindible: is_rendering es False bajo --livestream
            paso += 1
            if paso % 200 == 0:
                log(f"   paso {paso}")
            if args_cli.steps and paso >= args_cli.steps:
                break
    except KeyboardInterrupt:
        log(">> interrumpido")

    env.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
