# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

TFM (Máster en Robótica e IA, Universidad de León): **imitation learning on the Unitree G1 for
opening hand-wheel valves** (Oil & Gas standpipe valves), **in simulation only**. The deliverable is
a comparison of two IL approaches trained on the *same* teleoperated dataset:

- **A — VLA:** fine-tune NVIDIA GR00T N1.x on the task.
- **B — classical IL:** ACT (and/or Diffusion Policy) via HuggingFace LeRobot.

Metric: success rate on the `g1_valve` task, plus the partial-progress metric
`revolute_joint_moved_rate`, compared numerically and visually.

**Hard deadline: end of August 2026.** Time, not compute, is the binding constraint — prefer the
route that is already known to work over the more elegant one.

## Repository layout — read this first

This directory (`~/Desktop/VLA-HumanoidG1`) is the **umbrella repo**: TFM docs, task-specific
configs, evaluation and comparison analysis. It is the repo that gets published.

- **[`LAUNCH.md`](LAUNCH.md)** — the verified launch commands: view the sim, teleoperate with the
  PICO, record the dataset, convert to LeRobot, stop everything, and the failure table. Start here.
- **[`sim/`](sim/README.md)** — the versioned copy of everything that defines the `g1_valve` task:
  the environment file, the valve USD, the patches over upstream Arena, and the helper scripts.
  `sim/sync.sh {diff,pull,push}` keeps it in step with the live checkout.

**The simulation still RUNS from `~/TFM/IsaacLab-Arena`**, not from `sim/`. That is a checkout of
`isaac-sim/IsaacLab-Arena` — a checkout of
`isaac-sim/IsaacLab-Arena` on branch `release/0.2.1`, with local (uncommitted) changes. Its own
`CLAUDE.md` is just `@AGENTS.md`; read `~/TFM/IsaacLab-Arena/AGENTS.md` for upstream conventions
(pytest layout, pre-commit/black-120, DCO sign-off, `env.unwrapped` rule).

Other relevant paths on the host:

| Path | Role |
|---|---|
| `~/TFM/IsaacLab-Arena` | Simulation code, mounted at `/workspaces/isaaclab_arena` in the container |
| `~/datasets` | → `/datasets`. Recorded HDF5 and converted LeRobot datasets |
| `~/models` | → `/models`. Checkpoints. `isaaclab_arena/static_apple_tutorial/` is NVIDIA's reference fine-tune |
| `~/eval` | → `/eval`. Logs and `arena_extras/` launch scripts |
| `~/TFM/*.md` | Prior working notes — see "Existing notes" below |

## Everything runs inside the container

The container `isaaclab_arena-latest` (image `isaaclab_arena:latest`) is long-running; its
healthcheck reports `unhealthy` but the container works — ignore it. Isaac Sim cannot run on the
host.

```bash
docker exec isaaclab_arena-latest bash -c "cd /workspaces/isaaclab_arena && <command>"
```

`python` inside the container is `/isaac-sim/python.sh`. Use the explicit path in `docker exec`
lines, where the alias is not active.

Started/rebuilt from `~/TFM/IsaacLab-Arena` with `./docker/run_docker.sh` (`-r` rebuild,
`-g` GR00T deps, `-d ~/datasets -m ~/models -e ~/eval` mounts).

Verified inside the container: `torch 2.10.0+cu128`, CUDA available, **2 GPUs**, `gr00t 0.1.0`
(editable, from `submodules/Isaac-GR00T`, `n1.5-release`), `robomimic 0.4.0`.
**LeRobot is not installed anywhere** — approach B needs its own environment.

Hardware: 2× RTX PRO 6000 Blackwell (96 GB each), 250 GB RAM, ~1.4 TB free.

## The `g1_valve` task

Defined in `~/TFM/IsaacLab-Arena/isaaclab_arena_environments/g1_valve_environment.py`, registered
under the name `g1_valve` in `isaaclab_arena_environments/cli.py`.

- **Scene**: there are two, and which one you want depends on what you are doing. **Diáfano**
  (ground plane + dome light, `--background none`) is what gets **recorded** — the splat costs
  ~39 ms per step and you pay that in headset FPS across hours of teleoperation. **Office**
  (`--background office_gs`, a NuRec Gaussian Splat of the Madrid office) is what ends up in the
  **dataset**, applied afterwards by replaying the recorded actions through
  `train/scripts/rerender_demos.py`. Reversed on 2026-08-19; the "out of scope" line under
  *Decisions taken (2026-08-17)* is historical.
- **Embodiment**: `g1_wbc_agile_pink` — legs held by the AGILE ONNX whole-body-balance policy,
  upper body driven by Pink IK from teleop. `--lock_waist` defaults to **on** (static task).
- **Valve**: jescobars' CAD rig, `isaaclab_arena/assets/usd/valve_rig.usdz`, wrapped by
  `valve_rig_arena.usda` and registered as the `Valve` asset in
  `isaaclab_arena/assets/object_library.py`. Joint name is **`RevoluteJoint`**. The
  procedural placeholder `valve_handwheel_v1.usda` (joint `valve_joint`) is still on disk.
- **Valve layout**: drawn at every reset, 50/50, between `frontal` (wheel facing the robot,
  horizontal axis — a valve on a vertical line, turned like a ship's wheel) and `cenital` (wheel
  facing up, vertical axis — a valve on a horizontal line, reached over the top), plus
  ±(4, 6, 3) cm of position jitter. Both layouts exist in a real plant, so the policy should
  solve both. `VALVE_LAYOUTS` in `g1_valve_environment.py`; force one with
  **`ARENA_VALVE_LAYOUT=frontal|cenital`** to measure, or for a session dedicated to one.
  The two sit at deliberately *different* distances (0.43 m and 0.30 m from the pelvis) —
  turning a wheel from above wants the elbow closer in, so equal distances are not equally
  comfortable. Both numbers came out of the headset, not out of a calculation.
- **Success**: openness > 0.5 (half a turn), via `OpenDoorTask`.
- **Episode budget**: `EPISODE_LENGTH_S`, default 15 s at 50 Hz. Override with
  `ARENA_VALVE_EPISODE_S`. If turning the wheel needs longer than the budget, demos die by
  timeout and are **never written** — raise it rather than losing recordings.
- **All poses in the file are measured**, not guessed — see below.

### Two traps this task already fell into

Both were caught before recording and both would have been silent. Read
`valve_rig_arena.usda`'s `doc` and the constants in `g1_valve_environment.py` before
touching any of it.

**The joint limits.** The CAD rig authors the wheel's travel as 539.7° → 2879.8°, i.e. 6.5
turns, faithful to a real multi-turn gate valve. `Openable.get_openness` normalises
linearly over the joint's *limits* (`isaaclab_arena/utils/joint_utils.py:53-63`) and
success is openness > 0.5, so against the raw limits every demo would need **3.25 complete
revolutions inside one episode**. Unreachable by teleoperation → every episode ends by
timeout → nothing is ever written to the HDF5. `valve_rig_arena.usda` overrides the limits
to 0° → 360° so openness spans one turn and the 0.5 threshold means half a revolution. The
range is rebased to zero rather than shifted because Isaac Lab spawns articulations with
`joint_pos = {'.*': 0.0}` and validates against the limits.

**The robot spawn height.** `ROBOT_SPAWN_XYZ` must keep the pelvis at standing height
(0.74), not 0. At z=0 the pelvis starts inside the floor and the AGILE WBC hauls the robot
up through the space the valve occupies. Measured over 5 resets each:

| config | sigma (m) | falls |
|---|---|---|
| spawn z=0, valve in front | (0.300, 0.149, 0.310) | 1 of 5 |
| spawn z=0, valve behind | (0.029, 0.029, 0.024) | 0 of 5 |
| spawn z=0.74, valve in front | (0.001, 0.001, 0.001) | 0 of 5 |

Spawning standing makes the reset deterministic to a millimetre. That is a data-quality
property, not tidiness: every demo starts from the same pose, so the policy learns the task
rather than learning to compensate for a random initial condition, and a failed rollout at
evaluation is attributable to the policy rather than to a bad reset.

### Measuring poses

`/eval/arena_extras/measure_valve_rig.py` — reads the wheel body's real world pose out of
the articulation and characterises where the WBC leaves the robot. Use `--repeats N` to get
the spread; a single sample is misleading here.

```bash
docker exec isaaclab_arena-latest bash -c "cd /workspaces/isaaclab_arena && \
  unset DISPLAY && export HOME=/home/ivines && \
  /isaac-sim/python.sh -u /eval/arena_extras/measure_valve_rig.py \
  --device cpu --settle_steps 120 --repeats 5 g1_valve --background none"
```

Do **not** use the older `measure_valve_reach.py`: it dies before printing anything (its
2026-08-05 log ends at the same qpsolvers warning), and it computed the wheel position from
a hardcoded offset that only applied to the procedural placeholder.

Never measure with the zero action. Index [19] is `base_height_cmd`, and zero commands
pelvis height 0 — the robot sits on the floor and any reach figure describes a robot lying
down. `/eval/arena_extras/hold_pose_policy.py` has the correct standing action, and its
header documents two convention traps (observation poses are 4×4 matrices, not pos+quat;
`get_target_link_quaternion_in_target_frame` returns wxyz while the action wants xyzw).

## Pipeline

```
teleop (PICO 4 Ultra → CloudXR)
  └─ record_demos.py ──► HDF5 in /datasets/isaaclab_arena/g1_valve/
       └─ convert_hdf5_to_lerobot.py --yaml_file <cfg> ──► GR00T-LeRobot dataset
            ├─ A: GR00T fine-tune ──► gr00t_closedloop_policy ──┐
            └─ B: LeRobot ACT / Diffusion ─────────────────────┤
                                                                └─► policy_runner.py → success_rate
```

**Stage 1 — record.** `isaaclab_arena/scripts/imitation_learning/record_demos.py`. Launch recipe
(GPU pinning, CloudXR, ports, failure table) is in `~/TFM/TELEOP_G1_VALVE.md`; the concrete valve
invocation is at the end of that file. `~/eval/arena_extras/launch_record_valve.sh` wraps it.

**Stage 2 — convert.** `isaaclab_arena_gr00t/lerobot/convert_hdf5_to_lerobot.py --yaml_file <cfg>`.
It takes a single YAML. **Copy `isaaclab_arena_gr00t/lerobot/config/g1_static_apple_config.yaml`**
as the template — it is the same G1 embodiment (43-DoF joint space, `unitree_g1`,
`observation.images.ego_view`, fps 50) and only the task-specific top fields change (`data_root`,
`language_instruction`, `task_index`, `hdf5_name`).

**Stage 3A — GR00T.** Fine-tune entrypoint `submodules/Isaac-GR00T/gr00t/experiment/launch_finetune.py`;
closest reference recipe is `submodules/Isaac-GR00T/examples/GR00T-WholeBodyControl/finetune_g1.sh`.
Data configs for this embodiment already exist:
`isaaclab_arena_gr00t/embodiments/g1/g1_sim_wbc_data_config.py` and the **N1.7** variant
`g1_sim_wbc_data_gr00t_n_1_7_config.py`. Note the pinned submodule is `n1.5-release` — confirm
which checkpoint generation is actually loadable before promising N1.7 in the thesis.

**Stage 3B — ACT/Diffusion.** Not started. LeRobot must be installed in a **separate** Python
environment; do not pip-install it into the Isaac Sim interpreter — LeRobot pins its own
torch/torchvision and would break the simulator you need for evaluation.

The two approaches **share the simulation env, the recording and the conversion**. GR00T-LeRobot is
a superset of plain LeRobot v2.x: same parquet/video/`info.json`/`tasks.jsonl` layout, plus a
`modality.json` that ACT ignores. One conversion feeds both — verify this with a single demo before
recording in bulk.

Cross-environment evaluation is already solved by the repo, so ACT is scored in the *same*
simulator with the *same* metric:

- `policy_runner.py --policy_type` accepts **any dotted import path**, not a fixed list
  (`isaaclab_arena/evaluation/policy_runner.py:39-48`) — register a custom policy class.
- `isaaclab_arena/remote_policy/` is a ZMQ client/server. Run ACT as a `PolicyServer` in its own
  venv; the sim connects as a client. `isaaclab_arena_gr00t/policy/gr00t_remote_closedloop_policy.py`
  is the working example, and `replay_lerobot_action_policy.py` shows how LeRobot-format actions
  are consumed inside the sim.

## Action space — 23 dims

From `isaaclab_arena_g1/g1_env/mdp/actions/g1_decoupled_wbc_pink_action.py:226-234`:

```
[0]      left_hand_state             1   0=open, 1=close
[1]      right_hand_state            1
[2:5]    left_arm_pos                3   xyz
[5:9]    left_arm_quat               4   xyzw
[9:12]   right_arm_pos               3
[12:16]  right_arm_quat              4
[16:19]  navigate_cmd                3   locomotion velocity
[19]     base_height_cmd             1
[20:23]  torso_orientation_rpy_cmd   3
```

### Dims [0] and [1] are not "hand open/closed"

They carry `thumb_rotation` from the TriHand retargeter
(`isaacteleop/retargeters/G1/trihand_motion_controller.py:176`):

```python
thumb_rotation = 0.5 * trigger - 0.5 * squeeze
if not self._is_left:
    thumb_rotation = -thumb_rotation
```

Three consequences, all of which bite silently:

- **Trigger and squeeze cancel.** Pressing both fully gives 0, and the environment reads
  `if hand_state == 0` as *open*
  (`g1_wbc_upperbody_controller.py:256`). Squeezing harder can open the hand. **Record with the
  trigger only.**
- **The right hand's sign is inverted.** The same closing gesture records ≈ `+0.5` on the left
  and ≈ `-0.5` on the right. Not a bug to fix, but the policy sees an asymmetry.
- **The environment binarises** (`== 0` vs anything else) while the policy regresses a
  continuous value, so 0.02 of noise closes the hand. Fragile by design; upstream's, not ours.

The first recorded demo has both dims constant 0 — the wheel was pushed with an open hand.
**The decision (2026-08-18) is to grasp**, so every demo must show the trigger being used, and
`sim/scripts/inspect_hdf5.py` must show these dims non-constant before the bulk session starts.

**Standing under AGILE is not the same as having the nav channel in the action space.** The design
keeps AGILE balancing the legs (that is the realism argument and it stays), but if the operator
simply never touches the joystick, dims `[16:19]` are **constant zero across all 400 demos**. Two
consequences: normalization statistics get std=0 on those dims (division by zero, or an epsilon
that amplifies noise), and at inference a noisy action head can emit a nonzero `navigate_cmd` and
walk the robot away mid-evaluation — `NAVIGATE_THRESHOLD` gives a deadband but no guarantee.
Freeze or drop those three dims rather than relying on operator discipline.

**Stage 4 — evaluate.** `isaaclab_arena/evaluation/policy_runner.py`, e.g. with
`--policy_type zero_action` as a smoke test. Recorder terms `success_rate` and
`revolute_joint_moved_rate` are already active on this task. Closed-loop policy configs live in
`isaaclab_arena_gr00t/policy/config/` — `g1_static_apple_gr00t_closedloop_config.yaml` is the
template to copy.

## Do not swap the robot

The G1 used here is spawned from Isaac Nucleus, traced as
`g1_valve_environment.py:150` → embodiment `g1_wbc_agile_pink`
(`isaaclab_arena/embodiments/g1/g1.py:177`) → `G1_AGILE_CFG` (`g1.py:458`) → `G1_CFG` (`g1.py:238`):

```python
usd_path = f"{ISAAC_NUCLEUS_DIR}/Samples/Groot/Robots/g1_29dof_with_hand_rev_1_0.usd"
```

This is the **`with_hand`** model — 7 actuated joints per hand (`thumb_0/1/2`, `index_0/1`,
`middle_0/1`), which is exactly why `gr00t_43dof_joint_space.yaml` is 43 DoF: 29 body + 7 + 7.

jescobars' setup is built on a different framework (`unitree_rl_lab`, plain IsaacLab
`InteractiveSceneCfg`) around the **`with_inspire`** G1 — a different hand kinematics with
different joint names. Replacing the robot USD would break, in cascade: the actuator gains in
`G1_AGILE_CFG`, the joint ordering the AGILE ONNX policy expects (loss of balance), the retargeter
and Pink IK config, and the 43-DoF joint space that the GR00T conversion and fine-tune configs are
built on. **Take the valve asset only.**

Consequently none of these are needed: `g1_inspire_arm_collisions.usda`, the `vendor_g1_inspire.usd`
symlink, `tasks/.../valve/base_cfg.py` (Arena composes scenes via the asset registry +
`Scene(assets=[...])`, which `g1_valve_environment.py` already does), or the hardcoded
`UNITREE_MODEL_DIR`. No access to `TR-ROBOTICS/unitree_rl_lab` is required — one USD file is.

Transplanting the valve touches only the `Valve` class in
`isaaclab_arena/assets/object_library.py:203-231` (`usd_path`, `openable_joint_name` — the RL rig
will not call it `valve_joint` — and the joint limits that Arena maps to openness 0→1), plus
`VALVE_SPAWN_XYZ` in `g1_valve_environment.py:35` to keep the wheel within arm reach. A `.usda` may
carry `subLayers`/`references`/`payloads`; make sure the asset arrives self-contained.

## Things that cost hours if forgotten

Distilled from `~/TFM/TELEOP_G1_VALVE.md` and `~/TFM/ESTADO_TELEOP_XR.md`:

- **`unset DISPLAY` before any `docker exec` that launches Isaac Sim.** Otherwise it
  segfaults ~2 s in, inside `libX11!XOpenDisplay` via `omni.platforminfo.plugin`, and the
  only visible output is a breakpad minidump with no Python traceback. Also
  `export HOME=/home/ivines`.
- **`--enable_cameras` breaks `teleop.py`** — it drops the cameras whenever XR is active and the
  observation term hangs, so the env never builds. Cameras belong to `record_demos.py`, which is
  also what writes them into the HDF5.
- **Record with `--device cpu`, not `cuda`.** GPU physics + XR + `--enable_cameras` together kill
  the environment at creation with `CUDA error: an illegal memory access was encountered`, raised
  inside `GpuArticulationView.cpp`, always ~23 s in. Bisected on 2026-08-18: GPU+cameras without
  XR is fine, GPU+XR without cameras is fine, and it reproduces with the pelvis free as well as
  pinned, so neither the cameras nor `fix_root_link` is the culprit on its own. `GpuArticulationView`
  only exists with GPU physics, so CPU physics never walks that path. It costs no framerate — the
  ~20 FPS in the headset come from `renderQuality=performance` and `rendermode=RaytracedLighting`,
  not from the physics device.
- **Pin the GPU via `--kit_args`** (`--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0`).
  Without it XR dies with `VK_ERROR_OUT_OF_DEVICE_MEMORY`. **Never use `CUDA_VISIBLE_DEVICES`** —
  it leaves CUDA in a state that renders the WebRTC monitor black.
- **No native Isaac Sim window during XR over VNC** (`GLXBadFBConfig`). Go headless and stream.
- **Locomotion is still active** in the teleop path (left joystick walks). Data collection for a
  static task needs it disabled.
- The **third-person WebRTC monitor** is the highest-value debugging tool — comparing it against
  the headset view isolated two separate bugs. Ports below.
- Chrome only for the WebXR client; one tab at a time.

### Watching the sim over WebRTC — the two things that make it black

Both were hit on 2026-08-18 and cost a full session. A black WebRTC stream is *always* one of
these two, never the client.

**1. No `--viz kit` means there is nothing to stream.** In this Isaac Lab build the viewport is a
*visualizer* you have to ask for. `app_launcher.py` never writes `/isaaclab/has_gui` (it only
writes `render/offscreen`, `render/active_viewport`, `xr/*`), so `SimulationContext.is_rendering`
is False under `--livestream N` alone and `ManagerBasedRLEnv.step()` never calls `sim.render()`.
With no Kit visualizer there is no viewport at all, and `omni.kit.livestream.app` — which streams
*the application framebuffer* — transmits an empty buffer. Launch with **`--viz kit`** and, in a
custom loop, call `sim.render()` explicitly each step. Verified: with `--viz kit`,
`get_active_viewport()` returns a live `ViewportAPI` and `capture_viewport_to_file` writes a 388 KB
PNG of the scene; without it, nothing. `/eval/arena_extras/capture_viewport.py` is that check —
run it before blaming the network. Note RTX needs one warm-up frame: render 0 is black (max 0),
render 1 has pixels (max 245).

**2. The ports must exist in ufw, and `--livestream 1` hardcodes ones that do not.**
`ufw` is active with `DEFAULT_INPUT_POLICY=DROP`, so a SYN to a port with no rule is dropped in
silence — no error, no rejection, no log line. `--livestream 1` ("WebRTC public") pins
**signalPort=49100/tcp** and **streamPort=47998/udp** in `app_launcher.py:662-666`; the rules on
this host are for **49110/48010** and **49120/48020**, scoped to `172.22.41.0/24`. Either open
49100+47998 or override the ports via `--kit_args` to ones already allowed — the launch scripts
already do the latter:

```
--/exts/omni.kit.livestream.app/primaryStream/signalPort=49120
--/exts/omni.kit.livestream.app/primaryStream/streamPort=48020
--/exts/omni.kit.livestream.app/primaryStream/publicIp=172.22.41.51
```

Do not diagnose this from the workstation: a probe from a Docker bridge namespace
(172.17.0.x → 172.22.41.51) reports the ports open even when the LAN path is dropped. That is a
false positive; container-to-host traffic does not take the same chain. Test from the laptop.

Signalling is TCP, **media is UDP**. An SSH tunnel forwards TCP only, so connecting the client to
`127.0.0.1` through a tunnel negotiates the session and then shows black forever. Point the client
at `172.22.41.51` directly.

`/eval/arena_extras/stream_valve.py` is the standalone viewer: builds `g1_valve`, holds the robot
in a stable standing pose, frames the viewport on robot + valve, and steps until killed.

## Uncommitted local patches — do not lose these

`git status` in `~/TFM/IsaacLab-Arena` shows modified tracked files, none committed. Each has a
`.bak` beside it. A `git checkout` or `git submodule update` silently destroys them:

| File | Purpose |
|---|---|
| `submodules/IsaacLab/.../xr_anchor_manager.py` | Creates the XR anchor prim with raw USD when `SingleXFormPrim` fails. Without it you are anchored at pelvis height in the headset |
| `isaaclab_arena/scripts/imitation_learning/teleop.py` | Makes DLSS optional via `ARENA_XR_ANTIALIASING`; the default path forces `RealTimePathTracing` and overexposes the scene |
| `lightwheel_sdk/client/client.py` (**inside the container only** — lost on rebuild) | Network retries; without it a blink kills Arena startup after minutes of loading |

Also modified: `background_library.py`, `object_library.py` (the `Valve` asset), `record_demos.py`,
`isaaclab_arena_environments/cli.py`, `g1_pink_locomanipulation_pipeline.py`,
`g1_static_apple_gr00t_closedloop_config.yaml`. **The valve work itself is uncommitted** — getting
it onto a branch is worth doing early.

## Existing notes (host paths, not in this repo)

- `~/TFM/TELEOP_G1_VALVE.md` — launch guide for teleoperating `g1_valve`, verified 2026-07-23
- `~/TFM/ESTADO_TELEOP_XR.md` — state as of 2026-08-04, incl. the open Gaussian-Splatting XR bug
  and the list of already-discarded hypotheses (do not re-test them)
- `~/TFM/WBC.md`, `~/TFM/VISOR_ISAAC_SIM_VNC.md` — whole-body control and VNC viewer notes
- `~/TFM/.claude/skills/` — existing skills: `isaac-sim-troubleshooting`, `g1-troubleshooting`,
  `physical-ai-tutor`

## Decisions taken (2026-08-17)

- **400 demonstrations recorded by hand**, following NVIDIA's e2e tutorial. Isaac Lab Mimic
  (`generate_dataset.py`) was considered and rejected as a schedule risk.
- **PICO 4 Ultra**, real headset, already proven to connect.
- ~~Gaussian-Splatting backdrop **out of scope**~~ — **reversed on 2026-08-19**. Recording
  still happens in the diáfano scene; the splat goes in afterwards, by re-render.
- **Only the valve asset is taken from jescobars' (Javi's) work** — see "Do not swap the robot".
- Locomotion commands are to be frozen/removed from the action space, not merely left untouched
  (see "Action space" above). `ARENA_STATIC_BASE=1` does the freezing.

### Reversed on 2026-08-18: the pelvis is now pinned

The earlier decision was that the robot **stays standing under AGILE**, on the argument that it
mirrors the real deployment. Teleoperation killed it. Turning a hand-wheel feeds a reaction torque
back through the arms, and with a free root the balance controller absorbs it the only way it can:
by rotating the whole robot. The operator turns the wheel and the robot swings round with it.

That is fatal for the dataset, not merely ugly. Every demonstration would encode "the base drifts
while I turn" as part of the skill; the wheel would leave arm reach mid-episode; and the wrist
poses the policy regresses on are expressed in the *pelvis frame*, so a pelvis that moves makes
identical hand motions look like different actions.

`g1_valve_environment.py` now sets `fix_root_link=True` on the robot spawn, gated by
**`ARENA_FIX_BASE`** (default on). Measured over 3 resets afterwards: pelvis drift
`(0.000, 0.000, 0.000)` m, spread `0.000` m — against up to 0.30 m before. AGILE keeps running and
keeps the legs standing; it simply no longer has a pelvis it can move. **The action space stays at
23 dims**, so the 43-DoF joint space, the GR00T conversion and the recorder terms are all
unaffected.

`ARENA_STATIC_BASE` and `ARENA_FIX_BASE` are not the same thing and neither replaces the other:
the first stops the operator walking the robot away, the second stops physics moving it.

## State on 2026-08-18, evening (historical — see "Current state" at the end)

**One demonstration recorded, verified, and converted.** The pipeline runs end to end for the
first time: teleoperate → HDF5 with camera frames → GR00T-LeRobot dataset.

The recorded demo (`~/datasets/isaaclab_arena/g1_valve/g1_valve_demo01.hdf5`, 97 MB):

| | |
|---|---|
| `success` | `True`, 301 steps = 6.0 s at 50 Hz |
| valve joint | reaches 3.494 rad = **200°**, openness 0.556 over the 0.5 threshold |
| `/camera_obs/robot_head_cam_rgb` | (301, 480, 640, 3) uint8, **zero black frames**, mean 82 |
| `/actions` | (301, 23) |
| robot `root_velocity` | all zeros — the pinned pelvis holds under load |
| `navigate_cmd` | constant 0 — `ARENA_STATIC_BASE` works |

Converted with `isaaclab_arena_gr00t/lerobot/config/g1_valve_config.yaml` (a copy of the apple
config with only `data_root`, `language_instruction`, `task_index`, `hdf5_name` changed):
300-row parquet, `observation.state` and `action` both (300, 43), h264 ego_view at 50 fps.
The `fps: 50` is now measured, not assumed — `--step_hz 30` only throttles wall-clock pacing,
while the dataset gets one row per environment step at decimation 4 × dt 0.005 = 50 Hz.

### The bug that blocked recording all day

Recording with `--enable_cameras` under XR was impossible until `manager_based_env.py` was
patched. `_init_sim` calls `scene.update()` under a comment saying it is "needed for the
observation manager to get valid tensors", but `scene.update()` never renders, so an RTX
sensor has no frame when `ObservationManager._prepare_terms` asks the camera for one. Without
XR it resolves itself; with XR the tiled camera blocks forever in `wp.launch`, and with GPU
physics the same situation surfaces as `CUDA illegal memory access` in `GpuArticulationView`.
The non-tiled camera returns an empty buffer instead, giving an observation term of shape
`(0,)` — no image ever reaches the dataset.

Scenes with a large background USD work by accident, because the load time lets a frame get
produced first. That made it look like a scene-content problem for hours. Ruled out by
measurement: hiding the ground grid, the ground material's missing textures (downloaded and
fixed anyway), an empty background asset, visible geometry in view, the dome light sampling
strategy, the light type, DLSS/rendermode, and `fix_root_link`. The fix is
`sim/patches/isaaclab_prerender.patch` — four renders before the managers are built, gated on
RTX sensors being present, disabled with `ARENA_PRERENDER=0`.

Recording also needs **`--viz kit`** (NVIDIA's own reference recipe) and **`--device cpu`**, and
under XR `record_demos.py` starts **paused** — the operator presses START.

### Two data-quality findings from the first demo

- **The hands never close.** Action dims `[0]` and `[1]` (`left_hand_state`, `right_hand_state`)
  are constant 0 for the whole episode: the wheel was turned by pushing with an open hand, not
  by grasping a spoke. Whatever is decided, it has to be consistent across all 400 demos.
- **Eight of 23 dims have std = 0**: `[0,1]` hands, `[16,17,18]` locomotion, `[20,21,22]` torso
  orientation. Normalisation divides by that. Concrete evidence for the "freeze or drop the
  locomotion dims" item below.

Also measured: the wheel reached −11.8 rad/s (−677 °/s), so `damping = 0.01` leaves it spinning
loosely. For a heavier, more realistic valve raise **`physxJoint:jointFriction`** (dry friction,
a constant break-away torque, which is how a real gate valve behaves) rather than the damping
(viscous, speed-proportional).

Not yet done **as of that date** — superseded by the final section:

1. **Record one grasping demo and verify dims [0]/[1] are no longer constant**, then the
   400-demo session. Grasping is the decision (2026-08-18): more realistic for an Oil & Gas
   thesis than pushing the wheel with an open hand.
2. Freeze or drop the locomotion dims `[16:19]` from the 23-dim action layout before the GR00T
   conversion.
3. A separate venv with LeRobot for the ACT arm.
4. Merge per-session HDF5s with `merge_demos.py` (validates format_version, action shape,
   observation keys and camera geometry).

Open, lower priority: the valve floats with no standpipe (a probe sphere proved extra geometry
is not needed for the *bug*, but the standpipe is still worth it for the thesis figures); the
`ViewerCfg` third-person framing is poor for figures.

---

## Current state (2026-08-21)

Where this and the 08-18 entries disagree, this one wins.

### Both training arms have been run, end to end, on real recorded data

Not a smoke test: 25 teleoperated demos → LeRobot → **GR00T fine-tune** and **ACT**, both
evaluated inside the simulator on `g1_valve`, both at 10/10 successes. The full recipe, with the
commands, is in **[`TRAIN.md`](TRAIN.md)**; the dry run and its numbers are written up in
[`docs/ensayo_2026-08.md`](docs/ensayo_2026-08.md), and there is a video of each policy acting
in `videos/`.

That result is *encouraging but not the thesis*. It is 25 demos of a single valve layout with no
grasp, and both policies saw the same easy initial condition every time. Do not read it as
"the task is solved".

Four things cost hours and will cost them again:

- **GR00T on 2 GPUs hangs.** NCCL sits at "rank to GPU mapping is currently unknown", both ranks
  burn CPU and neither touches the GPU. `NUM_GPUS=1` trains at 3.2 steps/s — 10k steps in 54
  minutes, which is fast enough that the multi-GPU path is not worth debugging.
- **ACT emitted exactly zeros**, and it was not a training failure. Moving the policy to `cuda:1`
  leaves the normalisation buffers' std at 0, the state normalises to ~1e8 and the network
  saturates. Use `CUDA_VISIBLE_DEVICES=1` with `--device cuda`, never `--device cuda:1`.
  `train/scripts/act_remote_policy.py` now refuses to start if those buffers look wrong.
- **`lerobot==0.3.3` is the last v2.1 release.** 0.4.0 moves to dataset format v3.0 and will not
  read what the converter writes.
- **CloudXR owns port 49100**, hardcoded, which is also `--livestream 1`'s default signal port.
  On this shared workstation the livestream has to move to **49120/48020** (allowed in ufw for
  `172.22.41.0/24`). A black WebRTC stream during teleoperation is usually this.

### The Madrid office splat is in, and it goes in by re-render

`office_gs` now resolves to `/datasets/office_video_nurec_rot.usd` (the Madrid reconstruction —
*not* `office_video_nurec.usdz`, which is a different office in Bilbao), rotated +90° about Z.

The splat is **not** rendered while teleoperating. Demos are recorded in the diáfano scene and
the office is applied afterwards by `train/scripts/rerender_demos.py`, which replays the recorded
actions with the background loaded and re-records the camera. Measured:

| | |
|---|---|
| cost of the splat | ~39 ms/step → ~2.4 h to re-render 400 demos, unattended |
| survival | 24 of 25 (the one lost was already succeeding by 0.8°) |
| replay drift in the final valve angle | mean +1.5°, range −24° to +50° |
| does NuRec perturb the physics? | **no** — same 257 steps with and without |
| size | 60.7 MB/demo; the office compresses worse (2.77 GB vs 1.52 GB for 25) |

Two traps in the splat itself, both silent. USD **ignores `customLayerData` on a referenced
layer**, so the render settings the splat ships with never get applied — `g1_valve_environment.py`
reapplies them as carb settings when the background is tagged `nurec`. And `rotation_xyzw` really
is **xyzw**, whatever `~/TFM/VISOR_ISAAC_SIM_VNC.md` says; identity is `0,0,0,1`. Measure it with
`sim/scripts/measure_gs_pose.py` instead of trusting either note — that one cost three wrong
guesses in a row.

### The re-render has to force the recorded state, or it does not reproduce the demo

Found on 2026-08-21 and it invalidated a whole session's output before anyone noticed. Replaying
the recorded actions in the office scene produced a *different* trajectory: of 25 demos that all
succeeded when teleoperated, only 16 still turned the wheel past half a turn on replay. Worst
case `demo_14`, 191.1° recorded → **113.7°** replayed.

`--validate_states` located it exactly. The states diverge at **step 1**, not gradually, and not
in the joint positions but in the joint *velocities*:

```
demo_14 paso 1: ["robot"]["joint_velocity"] max|d|=13.11 en [14]: dataset 3.2552 runtime -9.8579
472 of 473 steps discrepant
```

Index `[14]` is `right_ankle_pitch_joint` and `[18]` is `right_ankle_roll_joint` — **ankles**.
That is the whole explanation: the HDF5 stores the 23-dim action, which drives the arms and the
command channels, but **the legs are driven by AGILE in closed loop and are not replayed — they
re-run**. They land somewhere else from the first step, the torso ends up slightly different, the
wrists grip the spoke at a different point, and by the end of the episode the wheel is 80° short.
Pushing a wheel head-on with an open hand tolerates that; grasping a spoke from above does not,
which is why the frontal-only `sesion_01` lost 1 of 25 and looked fine.

The fix is not to make the physics deterministic — it is not to simulate at all. The HDF5 records
the **full scene state at every step**, so `rerender_demos.py` now imposes it after each `step()`
instead of letting the controllers run free. Measured over all 50 demos of `sesion_02` +
`sesion_03`: **50/50 reproduce, worst wheel-angle difference 1.1°** (against 81° before), no black
frames. That residual 1.1° is one step of physics — the frame is rendered inside `step()`, just
before the state is imposed.

Two traps in implementing it:

- Use **`env.scene.reset_to(...)`**, never `env.reset_to(...)`. The latter calls
  `record_pre_reset()` and `_reset_idx()`, so calling it per step would export an episode and
  **re-draw the valve layout on every step**.
- `ArticulationData` hands these fields back as `wp.array` on some paths, and `wp.array` does not
  support item indexing — `data.joint_pos[0, 0]` raises `RuntimeError: Item indexing is not
  supported on wp.array objects`. It only bites when reading a scalar, so it killed the run
  *after* two minutes of loading. `_a_torch()` normalises first.

`--libre` restores the old open-loop behaviour if it is ever needed for comparison.

### Decisions taken on 2026-08-21

- **Grasp the wheel with the trigger.** Settled after being open since the 18th. Only the
  trigger: trigger and grip together cancel to 0, and 0 means *open hand* to the environment.
- **`sesion_01` (25 demos, pushing with an open hand) is a pipeline test, not training data.**
  It goes in the TFM as validation that the flow works. The definitive dataset starts at
  `sesion_02` and is recorded with a grasp.
- **Sessions of 25.** NVIDIA recommends 20–50; operator fatigue shows up in the demonstrations
  and the policy copies exactly that.
- Episode budget raised to **30 s** for recording. The episode ends by itself on success, so a
  generous budget only lengthens *failures* — while too short a budget turns a near-success into
  a timeout, and **a demo that times out is never written**.
- **Overhead valve at 0.30 m from the pelvis**, frontal at 0.43 m. Tried 0.20 m in the headset
  and it was too close — consistent with the geometry, since the wheel's 0.10 m radius puts its
  near edge on the robot's own body at that distance.
- **`sesion_02` and `sesion_03` recorded**: 50 demos, 25 each, all successful, grasping with the
  trigger, valve layout drawn at every reset. Hands non-constant (closed 51–56 % of steps), no
  black frames. Both re-rendered with the office at 50/50.
- **The two hands record the same sign** (−0.5 closed, 0 open), not the +0.5/−0.5 the retargeter
  note predicts. Since the value is `0.5·trigger − 0.5·squeeze` negated on one side, both reading
  −0.5 means one hand is on the grip and the other on the trigger. It works — and is *more*
  uniform than the documented asymmetry — but the gesture must not change mid-dataset, or
  "closed" ends up encoded two contradictory ways.

### 2026-08-22: 100 demos, both policies trained, and the first comparison that means anything

Sessions 04 and 05 recorded, so the definitive dataset is **100 demos** — and the layout split
came out at exactly **50 frontal / 50 cenital** without anyone forcing it. Re-rendered 100/100
with the office, merged into `valve_100.hdf5`, converted, verified (0 failures).

| | success over 100 rollouts | frontal | cenital |
|---|---|---|---|
| **GR00T N1.7** | **91 %** (84–95) | 37/37 | 54/63 |
| **ACT** | **83 %** (74–89) | 36/37 | 47/63 |

**The 91-vs-83 gap is NOT significant** (z = 1.68, p = 0.093) — do not write "GR00T beats ACT"
off this. What *is* significant is the layout: both policies are clearly worse overhead
(Fisher p = 0.024 for GR00T, p = 0.0045 for ACT), which matches everything else measured about
that layout. `revolute_joint_moved_rate` is 100 % for both, so it does not discriminate here:
every failure is "did not finish half a turn", never "never found the valve".

Full write-up, with what to do next, in [`docs/resultados_100demos.md`](docs/resultados_100demos.md).
Figures in `~/eval/figuras/`, policy videos in `~/eval/videos/politicas/`.

Two operational lessons from the unattended run:

- **`docker exec` without `-d` dies with its client.** A 12-minute re-render launched from a
  shell that then closed stopped at 7 of 25. Long jobs go through
  `sim/scripts/pipeline_valve_100.sh` (container, `-d`) and the host drivers under `setsid`,
  each writing a per-stage sentinel so a rerun skips what is done.
- **Evaluate with the background the policy was trained on.** The images come from the office
  re-render, so evaluation runs `--background office_gs` with `OFFICE_GS_LIGHT` unset.

### Still open

1. Record the remaining demos toward 400 (100 done), re-rendering each session as it lands.
   Consider 40/60 in favour of the overhead layout: the dataset is balanced but the results say
   that half is the hard one.
2. Freeze or drop the locomotion dims `[16:19]` before the GR00T conversion — 8 of 23 dims still
   have std = 0.
3. ~~`--device cpu` is not honoured during the re-render.~~ Still true — the env cfg comes up
   `cuda:0` whatever you pass — but it stopped mattering once the state is forced, since the
   physics no longer decides the outcome. Do **not** try to fix it by passing `--device cpu`:
   that path hangs (28 min without finishing one episode) and PhysX reports
   `Failed to get a valid attached USD stage id`.
4. `sesion_01_office_ok` was produced by the old open-loop re-render, so its images do not
   reproduce the recorded demos either — the drift just never crossed the threshold, being
   frontal-only pushes. It is a pipeline test and **not training data**, so it is being left as
   is; redo it with state forcing only if it ends up in a figure.
5. ~~Dome light: 3000 at re-render, 1500 at recording.~~ Checked on 2026-08-21 and it is a
   non-issue: `OFFICE_GS_LIGHT` is only read on the NuRec path
   (`g1_valve_environment.py:326`, default **3000**), so the `OFFICE_GS_LIGHT=1500` in
   `LAUNCH.md`'s Mode C is inert with `--background none`. The dataset's images all come from
   the re-render, so what matters is that **every re-render leaves the variable unset** —
   `sesion_01_office_ok` was produced that way. Set it and you split the dataset in two.
6. Cosmetic, for the figures: the valve floats with no standpipe, there is a doubled ground plane
   (`/World/Plane` plus Arena's `ground_plane`) and a nested `/PhysicsScene`.
7. ~~`LAUNCH.md` still recommends port 49100 for Mode A; add the re-render as a Mode D.~~ Done
   on 2026-08-21: Mode A now warns that 49100 is CloudXR's, and **Mode D** documents the
   re-render and the video extraction.
