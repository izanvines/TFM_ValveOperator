# Copyright (c) 2026. TFM: G1 valve manipulation.
# SPDX-License-Identifier: Apache-2.0
"""Headless Isaac Sim smoke test for the procedural hand-wheel valve.

Loads ``valve_handwheel_v1.usda`` as a real articulation, confirms the joint/limits match
what we authored, drives ``valve_joint`` from closed (0 deg) to open, and renders the motion
to a GIF + stills -- all offscreen (no display needed).

Diagnostics are written to ``_valve_preview/diag.txt`` with flush, because Isaac Sim hard-exits
on ``simulation_app.close()`` and drops any buffered Python stdout.

Run inside the isaaclab_arena container:
    /isaac-sim/python.sh /workspaces/isaaclab_arena/tools/valve/preview_valve.py
"""

from __future__ import annotations

import math
import os

import sys

# Launch the app exactly the way Arena's (camera-rendering) tests do: pass the full CLI
# namespace to AppLauncher via get_app_launcher, not loose kwargs. This is the proven path
# that actually renders cameras headlessly in this container.
from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser  # noqa: E402
from isaaclab_arena.utils.isaaclab_utils.simulation_app import get_app_launcher  # noqa: E402

_argv_backup = sys.argv[:]
sys.argv = [sys.argv[0]]  # hide script args from Kit
_args = get_isaaclab_arena_cli_parser().parse_args([])
_args.headless = True
_args.enable_cameras = True
app_launcher = get_app_launcher(_args)
simulation_app = app_launcher.app
sys.argv = _argv_backup

import numpy as np  # noqa: E402
import torch  # noqa: E402
import warp as wp  # noqa: E402

import isaaclab.sim as sim_utils  # noqa: E402
from isaaclab.actuators import ImplicitActuatorCfg  # noqa: E402
from isaaclab.assets import Articulation, ArticulationCfg  # noqa: E402
from isaaclab.sensors import Camera, CameraCfg  # noqa: E402
from isaaclab.sim import SimulationCfg, SimulationContext  # noqa: E402

USD_PATH = "/workspaces/isaaclab_arena/isaaclab_arena/assets/usd/valve_handwheel_v1.usda"
OUT_DIR = "/workspaces/isaaclab_arena/_valve_preview"
VALVE_POS = (0.6, 0.0, 0.0)

_diag_fh = None


def log(msg):
    print(msg, flush=True)
    if _diag_fh is not None:
        _diag_fh.write(str(msg) + "\n")
        _diag_fh.flush()


def to_np(x):
    """Isaac Lab 3.0 (Newton) exposes sim data as warp arrays; cameras as torch. Normalize."""
    if isinstance(x, torch.Tensor):
        return x.detach().cpu().numpy()
    try:
        return wp.to_torch(x).detach().cpu().numpy()
    except Exception:  # noqa: BLE001
        return np.asarray(x)


def main():
    global _diag_fh
    os.makedirs(OUT_DIR, exist_ok=True)
    _diag_fh = open(os.path.join(OUT_DIR, "diag.txt"), "w")

    sim = SimulationContext(SimulationCfg(dt=1.0 / 60.0, device="cuda:0"))

    # --- diáfano scene: ground + distant light (matches IsaacLab's working camera tutorial) ---
    sim_utils.GroundPlaneCfg().func("/World/ground", sim_utils.GroundPlaneCfg())
    sim_utils.DistantLightCfg(intensity=3000.0, color=(0.75, 0.75, 0.75)).func(
        "/World/Light", sim_utils.DistantLightCfg(intensity=3000.0, color=(0.75, 0.75, 0.75))
    )
    sim_utils.DomeLightCfg(intensity=800.0, color=(0.8, 0.8, 0.8)).func(
        "/World/DomeLight", sim_utils.DomeLightCfg(intensity=800.0, color=(0.8, 0.8, 0.8))
    )

    # --- valve articulation (add an actuator so we can drive the joint) ---
    valve_cfg = ArticulationCfg(
        prim_path="/World/Valve",
        spawn=sim_utils.UsdFileCfg(usd_path=USD_PATH, activate_contact_sensors=False),
        init_state=ArticulationCfg.InitialStateCfg(pos=VALVE_POS),
        actuators={
            "wheel": ImplicitActuatorCfg(joint_names_expr=["valve_joint"], stiffness=40.0, damping=8.0),
        },
    )
    valve = Articulation(valve_cfg)

    # --- third-person camera looking at the wheel ---
    cam_cfg = CameraCfg(
        prim_path="/World/preview_cam",
        height=720,
        width=1280,
        data_types=["rgb"],
        spawn=sim_utils.PinholeCameraCfg(
            focal_length=24.0, focus_distance=400.0, horizontal_aperture=20.955, clipping_range=(0.1, 1.0e5)
        ),
    )
    cam = Camera(cam_cfg)

    sim.reset()
    cam.set_world_poses_from_view(
        eyes=torch.tensor([[-0.7, -1.3, 1.5]], device=sim.device),
        targets=torch.tensor([[0.45, 0.0, 0.95]], device=sim.device),
    )

    # --- report what actually loaded (the real in-sim physics validation) ---
    log("=" * 60)
    log("VALVE LOADED IN SIM")
    log(f"joint_names: {valve.joint_names}")
    limits = to_np(valve.data.joint_pos_limits)[0].tolist()
    log(f"joint_pos_limits (rad): {limits}  deg: {[[round(math.degrees(a), 1) for a in p] for p in limits]}")
    log(f"num_bodies: {valve.num_bodies} | body_names: {valve.body_names}")
    log("=" * 60)

    jidx = valve.joint_names.index("valve_joint")
    open_rad = math.radians(330.0)

    # --- warmup renders so the RTX pipeline produces valid frames ---
    for _ in range(20):
        sim.step()
        valve.update(1.0 / 60.0)
        cam.update(1.0 / 60.0)

    frames = []
    n_steps = 150
    for i in range(n_steps):
        frac = min(1.0, i / (n_steps * 0.66))
        target = torch.zeros((valve.num_instances, valve.num_joints), device=sim.device)
        target[:, jidx] = frac * open_rad
        valve.set_joint_position_target(target)
        valve.write_data_to_sim()
        sim.step()
        valve.update(1.0 / 60.0)
        cam.update(1.0 / 60.0)
        if i % 5 == 0:
            rgb = to_np(cam.data.output["rgb"])[0, ..., :3]
            angle = math.degrees(float(to_np(valve.data.joint_pos)[0, jidx]))
            log(f"step {i:3d} | wheel_angle {angle:6.1f} deg | rgb min/max/mean "
                f"{int(rgb.min())}/{int(rgb.max())}/{rgb.mean():.1f}")
            frames.append(rgb)
            if i in (0, n_steps // 2, n_steps - 5):
                _save_png(rgb, os.path.join(OUT_DIR, f"valve_step_{i:03d}.png"))

    angle_now = math.degrees(float(to_np(valve.data.joint_pos)[0, jidx]))
    log(f"FINAL wheel angle: {angle_now:.1f} deg (openness ~ {angle_now / 360.0:.2f})")
    _save_gif(frames, os.path.join(OUT_DIR, "valve_open.gif"))
    log(f"DONE. {len(frames)} frames -> {OUT_DIR}")
    _diag_fh.close()
    simulation_app.close()


def _save_png(rgb, path):
    try:
        import imageio.v3 as iio

        iio.imwrite(path, rgb.astype("uint8"))
        log(f"wrote {path}")
    except Exception as e:  # noqa: BLE001
        log(f"PNG save failed: {e}")


def _save_gif(frames, path):
    try:
        import imageio

        imageio.mimsave(path, [f.astype("uint8") for f in frames], duration=0.08, loop=0)
        log(f"wrote {path}")
    except Exception as e:  # noqa: BLE001
        log(f"GIF save failed: {e}")


if __name__ == "__main__":
    main()
