# Graba un mp4 desde la CAMARA DEL ROBOT (robot_head_cam), no desde el viewport.
#
# Por que: el viewport de ViewerCfg no encuadra la escena (sale el plano de suelo a lo
# lejos y nada mas), pero robot_head_cam si produce imagen valida -- y es ademas la que
# se escribe en el HDF5, asi que este video muestra literalmente lo que vera el VLA.
from isaaclab.app import AppLauncher
from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
from isaaclab_arena_environments.cli import add_example_environments_cli_args

parser = get_isaaclab_arena_cli_parser()
parser.add_argument("--steps", type=int, default=300)
parser.add_argument("--outdir", type=str, default="/eval/robotcam")
add_example_environments_cli_args(parser)
args_cli = parser.parse_args()
app_launcher = AppLauncher(vars(args_cli))
simulation_app = app_launcher.app

import os  # noqa: E402
import numpy as np, torch  # noqa: E402
from isaaclab_arena_environments.cli import get_arena_builder_from_cli  # noqa: E402

def log(m): print(m, flush=True)

os.makedirs(args_cli.outdir, exist_ok=True)
for f in os.listdir(args_cli.outdir):
    if f.endswith(".png"):
        os.remove(os.path.join(args_cli.outdir, f))

env = get_arena_builder_from_cli(args_cli).make_registered()
env.reset()
u = env.unwrapped
a = torch.zeros((u.num_envs, u.action_manager.total_action_dim), device=u.device)
a[:, 2:5] = torch.tensor([0.22, 0.20, 0.05], device=u.device)
a[:, 5:9] = torch.tensor([0.0, 0.0, 0.0, 1.0], device=u.device)
a[:, 9:12] = torch.tensor([0.22, -0.20, 0.05], device=u.device)
a[:, 12:16] = torch.tensor([0.0, 0.0, 0.0, 1.0], device=u.device)
a[:, 19] = 0.75

cam = u.scene.sensors["robot_head_cam"]
from PIL import Image  # noqa: E402

saved = 0
for i in range(args_cli.steps):
    env.step(a)
    rgb = cam.data.output["rgb"]
    arr = rgb.detach().cpu().numpy() if hasattr(rgb, "detach") else np.asarray(rgb)
    frame = arr[0, ..., :3].astype(np.uint8)
    if frame.max() == 0:
        continue
    Image.fromarray(frame).save(os.path.join(args_cli.outdir, f"f{saved:05d}.png"))
    saved += 1
    if saved % 50 == 0:
        log(f"  {saved} fotogramas")
log(f">> guardados {saved} fotogramas en {args_cli.outdir}")
env.close()
simulation_app.close()
