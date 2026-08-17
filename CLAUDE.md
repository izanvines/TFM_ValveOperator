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
configs, evaluation and comparison analysis.

**The simulation code is NOT here.** It lives in `~/TFM/IsaacLab-Arena` — a checkout of
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

- **Scene ("diáfano")**: ground plane + dome light only. No background USD. Keep it that way —
  the Gaussian-Splatting office backdrop has an unresolved XR rendering bug (see notes) and is
  **out of scope** for the TFM.
- **Embodiment**: `g1_wbc_agile_pink` — legs held by the AGILE ONNX whole-body-balance policy,
  upper body driven by Pink IK from teleop. `--lock_waist` defaults to **on** (static task).
- **Valve**: jescobars' CAD rig, `isaaclab_arena/assets/usd/valve_rig.usdz`, wrapped by
  `valve_rig_arena.usda` and registered as the `Valve` asset in
  `isaaclab_arena/assets/object_library.py`. Joint name is **`RevoluteJoint`**. The
  procedural placeholder `valve_handwheel_v1.usda` (joint `valve_joint`) is still on disk.
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
- **Pin the GPU via `--kit_args`** (`--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0`).
  Without it XR dies with `VK_ERROR_OUT_OF_DEVICE_MEMORY`. **Never use `CUDA_VISIBLE_DEVICES`** —
  it leaves CUDA in a state that renders the WebRTC monitor black.
- **No native Isaac Sim window during XR over VNC** (`GLXBadFBConfig`). Go headless and stream.
- **Locomotion is still active** in the teleop path (left joystick walks). Data collection for a
  static task needs it disabled.
- The **third-person WebRTC monitor** (port 49200) is the highest-value debugging tool — comparing
  it against the headset view isolated two separate bugs.
- Chrome only for the WebXR client; one tab at a time.

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
- Gaussian-Splatting backdrop **out of scope**; the diáfano scene is the deliverable.
- **Only the valve asset is taken from jescobars' (Javi's) work** — see "Do not swap the robot".
- Robot **stays standing under the AGILE policy** — this mirrors the real deployment. Locomotion
  commands are to be frozen/removed from the action space, not merely left untouched (see above).

## Current state (2026-08-17)

**Zero demonstrations recorded.** The only HDF5 in `~/datasets/isaaclab_arena/g1_valve/` is 96
bytes — an empty session file from 2026-08-05.

The environment itself is verified working with the CAD valve. Confirmed in-sim: the
articulation loads with bodies `['valve_model_stl_001', 'mesh_50_AL_250_B7_8_A_stl']` and
joint `['RevoluteJoint']` at limits [0°, 360°]; both material bindings resolve, so the
wheel keeps its staticFriction 1.2 / dynamicFriction 1.0; the AGILE ONNX policy loads; the
action manager reports 23 dims; both recorder terms register; and the reset is deterministic
to a millimetre with both wrists 0.44 m from the wheel.

Not yet done, in order:

1. **Record one demo end to end** and confirm the HDF5 holds an episode with camera frames.
   Everything above is necessary but not sufficient — recording has never once succeeded here.
2. Convert that single demo to LeRobot (copy `g1_static_apple_config.yaml`) before recording
   in bulk.
3. Freeze or drop the locomotion dims `[16:19]` from the action space.
4. **Get the valve work onto a branch** — it is all uncommitted and one `git checkout` erases it.
5. The 400-demo session.
6. In parallel: a separate venv with LeRobot for the ACT arm.

Untested and worth watching at step 1: the rig drives its wheel with `damping=100,
maxForce=1000, stiffness=0` — a deliberately heavy valve. Whether the G1 can actually turn
it against that damping has not been demonstrated, only that it can reach it.
