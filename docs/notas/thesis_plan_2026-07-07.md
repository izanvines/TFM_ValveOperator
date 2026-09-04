# TFM Plan v2 — Learning to Operate Valves by Imitation, on the Real Unitree G1

**Working title:** Imitation Learning for Valve Manipulation with the Unitree G1
**Track:** Master's thesis (TFM), Robotics & AI
**Status:** v2 — revised for a **2-month deadline** and **confirmed real G1 hardware access**
**Date:** 2026-07-06 (supersedes the v1 draft: 9-month timeline, dual-simulator IL+RL comparison)

---

## 0. What changed from v1, and why

v1 assumed a ~9-month timeline and treated a three-way IL/RL/residual-RL comparison across two simulators as the core contribution. With a **hard 2-month deadline** and **real G1 access already confirmed**, that scope is not achievable. v2 narrows to a single, well-supported method chain:

> Collect real teleoperated demonstrations of the G1 opening/closing a valve while standing in a fixed, stable pose → train an imitation-learning policy (ACT) on them → evaluate success rate and basic robustness on the real robot.

RL (from-scratch, residual, or otherwise), the Isaac Lab vs. MuJoCo comparison, and full loco-manipulation are demoted to **future work** (§10) — worth a paragraph in the thesis discussion, not something to execute in 8 weeks.

## 1. Problem statement (revised)

Core deliverable, in priority order:
1. A **demonstration dataset** (RGB(+depth) + joint state + action, LeRobot format) of a real Unitree G1 opening and closing a valve, collected via teleoperation.
2. An **imitation-learning policy (ACT)** trained on that dataset that reproduces the behavior closed-loop on the robot.
3. An **evaluation** of success rate and robustness (at minimum: varying the valve's starting angle within reach).

The robot's lower body is not part of the learning problem: it holds a fixed standing pose via its existing stock stabilization controller, and only the arm(s) — and possibly waist — are commanded by the learned policy. See §4.

## 2. Why imitation learning, and which technology

This section exists because IL was previously unfamiliar territory — the reasoning below is the answer to "is teaching by demonstration actually possible, and is IL the right call."

**Yes, it's feasible, and it's the right call given your constraints.** The evidence:
- **ACT (Action Chunking with Transformers)**, introduced in the ALOHA paper *Learning Fine-Grained Bimanual Manipulation with Low-Cost Hardware* (arXiv 2304.13705), reached **80–90% success on fine-grained manipulation tasks from only ~10 minutes of teleoperated demonstrations**, using simple (non-dexterous) grippers. That effort/result ratio is exactly what a 2-month TFM needs.
- Unitree has already built the tooling you need: **`unitree_lerobot`** (github.com/unitreerobotics/unitree_lerobot — Unitree's adaptation of Hugging Face's LeRobot for dual-arm IL) plus **`avp_teleoperate`** for collecting demonstrations. It handles the full chain: teleoperated data collection → GUI episode editor (trim/discard bad episodes) → conversion to LeRobot dataset format (optionally pushed to the HF Hub) → training → real-robot evaluation, plus an optional sim-based evaluation path via `unitree_sim_isaaclab`. It natively supports both G1 arm variants (G1_23, G1_29) and, on the end-effector side, Dex1, Dex3, **Inspire1**, and Brainco hands, with ACT, Diffusion Policy, Pi0, Pi05, and Groot as training backends.
- **Open item:** the repo lists **"Inspire1"** as a supported hand, not "Inspire DFX / RH56DFX" by that exact name — verify whether these refer to the same hand family before assuming out-of-the-box support for the specific DFX unit (§9).
- Unitree's own published datasets (`G1_Pouring_Dataset`, `G1_Dex3_ToastedBread_Dataset`) show this exact recipe already validated on this exact robot. You are following a proven path, not inventing one.

**Recommended stack:** ACT via `unitree_lerobot`, demonstrations via `avp_teleoperate`. Not Diffusion Policy, Pi0/Pi05, or Groot for the core result — all are heavier and more data-hungry than ACT and unnecessary at this scope; keep them as a "if there's time" comparison, not a dependency.

**Suggested first step, before touching the real robot:** clone `unitree_lerobot` and run its training pipeline on one of Unitree's already-published datasets (e.g. `G1_Pouring_Dataset`) end-to-end (data → training → inference). This de-risks the *pipeline mechanics* (environment setup, dataset format, training command, checkpoint loading) in parallel with getting the physical valve fixture and teleoperation hardware ready, so week 1 isn't the first time you touch any of this tooling.

**Why not RL as the core method:** RL needs a tuned reward function, many more environment interactions than you can collect on real hardware in weeks, and — if done in sim to get those interactions cheaply — reopens the sim2real problem in §3. It stays as future work (§10).

## 3. Simulation vs. real hardware

**Decision: train and evaluate on the real robot; do not build a simulated valve-manipulation training pipeline.**

Reasoning: sim2real transfer for contact-rich, sustained-force manipulation (grasp + apply torque against resistance, exactly what valve turning is) is still an open, actively-researched problem — *VIRAL* (arXiv 2511.15200) and *VisualMimic* (arXiv 2509.20322) are 2025-era papers explicitly about closing this gap, and they're frontier research, not a solved technique you can casually replicate. Given real hardware access, the entire problem disappears: an IL policy trained on real teleoperated data learns the real dynamics directly. Simulation (MuJoCo, if used at all) is optional and limited to cheap qualitative checks — e.g. visualizing reachability or a candidate approach pose — never as a source of training data.

## 4. Decoupling upper-body manipulation from lower-body balance

This directly answers the "robot falls over when it grasps/moves something" problem you observed with the default biped locomotion policy (which is trained for walking, not for reacting to manipulation loads).

**It is both possible and the standard solution in the literature.** *TOP: Time Optimization Policy for Stable and Accurate Standing Manipulation* (arXiv 2508.00355) explicitly decouples an upper-body controller (precision manipulation) from a lower-body RL controller (balance/robustness). *EMP: Executable Motion Prior for Humanoid Robot Standing Upper-body Motion Imitation* (arXiv 2507.15649) follows the same pattern for upper-body motion imitation while keeping the robot stable.

**Given the 2-month budget, don't train a new lower-body balance policy.** Instead: use the G1's existing stock standing/stabilization controller to hold a fixed stance, and let the learned IL policy command only the arm (and optionally waist) joints. This is exactly the pattern behind Unitree's own manipulation demos (pouring, bread task): the robot stands still on its stock controller while the arms are teleoperated/learned separately. It resolves the instability problem without any new RL training.

**Action item, do this in week 1:** test empirically whether the stock stand controller stays stable under the reaction torque of turning a valve. If it holds — great, proceed as planned. If the valve's resistance torque destabilizes it, note this as an observed limitation in the thesis and leave a custom TOP/EMP-style lower-body controller as future work (§10) rather than trying to solve it mid-project.

## 5. Hand / end-effector choice

**Recommendation: start with the static (simple) gripper — whichever is already mechanically mounted and calibrated on the robot today.**

Reasoning: fewer actuated DOF means a smaller action space, which converges faster with fewer demonstrations — and it's exactly the configuration ACT already proved out (80–90% success, simple grippers, ~10 min of demos). Don't lose days of your 8-week budget to a hardware swap and recalibration before you've even collected data.

Treat the **Inspire DFX dexterous hand** (RH56DFX: 6 DOF / 12 joints, 5-finger, integrated force sensing, ~3 kg payload rating) as an optional generalization experiment for the final 1–2 weeks, only if the static-gripper pipeline is working solidly by then. A "does the extra dexterity help or just add noise" comparison would be a nice addition to the thesis, but it is not a Month-1 dependency.

**Tooling caveat:** `unitree_lerobot` lists **"Inspire1"** as a supported hand — confirm whether that's the same hardware family as your Inspire DFX/RH56DFX before relying on out-of-the-box support in the stretch phase (§9).

## 6. Revised methodology (real hardware only)

1. **Lock scope**: static gripper, single valve, single fixed mounting position for the robot. Empirically confirm the stock stand controller holds under valve-turning reaction torque (§4).
2. **Set up teleoperation + recording**: `avp_teleoperate` (or `xr_teleoperate`, depending on which XR headset/device is available) feeding the `unitree_lerobot` recording pipeline — camera(s), joint state, and action stream saved in LeRobot dataset format.
3. **Build/place a real valve fixture** at a fixed, reachable position. Keep geometry fixed for the core result; vary only the valve's starting angle across episodes for a minimal but real robustness axis.
4. **Collect demonstrations**: ~50–100 teleoperated episodes of open + close. (ACT's original result used ~10 minutes of demonstration time total — treat that as a lower bound, not a target; collect more if early training results are weak.)
5. **Clean the dataset** with the LeRobot data editor — trim or discard failed/noisy episodes.
6. **Train an ACT policy** via `unitree_lerobot` (native G1_23/G1_29 support).
7. **Evaluate closed-loop on the real robot**: success rate over N trials, with some variation in the valve's starting angle.
8. **(Stretch, only if ahead of schedule)** mount the Inspire DFX hand, recollect a smaller demonstration set, and compare.

## 7. Evaluation plan (trimmed)

| Axis | Metric |
|---|---|
| Task success | Valve fully opened/closed within a time budget, over N real-robot trials |
| Robustness | Success rate across varied valve starting angles (within reach) |
| Efficiency | Demonstrations needed to reach a usable success rate (useful even as a negative result) |
| Stretch: end-effector | Static gripper vs. Inspire DFX — success rate comparison, if time allows |
| Stretch: stability | Qualitative note on stock lower-body controller behavior under manipulation load |

## 8. Two-month timeline (week by week)

| Week | Focus |
|---|---|
| 1 | Lock scope; empirically test stock stand-controller stability under valve-turning torque; set up teleop + recording pipeline; build/place the valve fixture |
| 2 | Collect and clean the demonstration dataset (~50–100 episodes) |
| 3 | First ACT training run; get the full pipeline (data → training → deployment on robot) working end-to-end, even if success rate is still low |
| 4 | Iterate on training (more/cleaner data, hyperparameters); first closed-loop evaluation on the real robot; first working demo |
| 5 | Formal evaluation protocol: success rate, robustness to starting angle |
| 6 | Stretch experiment (Inspire DFX comparison) **or** deeper failure-mode analysis if the stretch isn't reached |
| 7 | Results write-up: figures, videos, failure-mode analysis |
| 8 | Writing, buffer for delays, defense prep |

## 9. Open questions to resolve immediately (gate everything else)

- **Stock stand-controller robustness** — does it hold under the valve's reaction torque? Test this in week 1; it determines whether §4's plan works as-is or needs a fallback.
- **Which hand is mechanically ready today** — confirm before week 1 starts so no time is lost to hardware swaps.
- **"Inspire1" (in `unitree_lerobot`) vs. "Inspire DFX / RH56DFX" (your physical hand)** — confirm these are the same hand family before assuming the stretch-goal comparison in §5/§8 has out-of-the-box tooling support; if not, budget extra integration time or drop the stretch goal.
- **How much starting-angle variation is realistic** with a single physical valve fixture and 8 weeks — sets the ceiling on the robustness claim in §7.
- **Advisor sign-off** that RL / cross-simulator work being pushed entirely to "future work" is acceptable framing for the thesis's core contribution (dataset + IL policy).

## 10. Out of scope / future work (moved out of the 2-month core)

- RL fine-tuning or residual RL on top of the IL policy
- Cross-simulator (Isaac Lab vs. MuJoCo) comparison
- Full loco-manipulation (walking to an arbitrarily placed valve)
- A custom lower-body balance controller (TOP/EMP-style) beyond the stock one, unless §4's week-1 test shows it's actually needed

## 11. Reference list

**Imitation learning method**
- ALOHA / ACT: Learning Fine-Grained Bimanual Manipulation with Low-Cost Hardware — https://arxiv.org/pdf/2304.13705
- ALOHA project page (demos, videos) — https://tonyzhaozh.github.io/aloha/
- A Comparison of Imitation Learning Algorithms for Bimanual Manipulation — https://arxiv.org/pdf/2408.06536

**Tooling (Unitree G1 + LeRobot)**
- `unitree_lerobot` (GitHub) — https://github.com/unitreerobotics/unitree_lerobot — the primary tool: data collection → editing → LeRobot dataset conversion → training (ACT, Diffusion Policy, Pi0, Pi05, Groot) → real-robot and sim evaluation, for G1_23/G1_29 with Dex1/Dex3/Inspire1/Brainco hands
- LeRobot (Hugging Face, upstream framework) — https://github.com/huggingface/lerobot
- `avp_teleoperate` (GitHub) — https://github.com/unitreerobotics/avp_teleoperate
- `xr_teleoperate` (GitHub, alternative depending on XR device) — https://github.com/unitreerobotics/xr_teleoperate
- Unitree G1 published manipulation datasets (Hugging Face) — https://huggingface.co/datasets/unitreerobotics/G1_Pouring_Dataset

**Decoupled upper/lower-body control (context for §4, and for future work if needed)**
- TOP: Time Optimization Policy for Stable and Accurate Standing Manipulation with Humanoid Robots — https://arxiv.org/html/2508.00355
- EMP: Executable Motion Prior for Humanoid Robot Standing Upper-body Motion Imitation — https://arxiv.org/html/2507.15649

**Sim2real difficulty (context for §3)**
- VIRAL: Visual Sim-to-Real at Scale for Humanoid Loco-Manipulation — https://arxiv.org/pdf/2511.15200
- VisualMimic: Visual Humanoid Loco-Manipulation via Motion Tracking and Generation — https://arxiv.org/pdf/2509.20322

**End-effector reference**
- Inspire DFX (RH56DFX) Dexterous Hand — https://support.unitree.com/home/en/G1_developer/inspire_dfx_dexterous_hand

**Retained from v1 (grasp-strategy inspiration, still useful during demo collection)**
- DARPA Robotics Challenge valve task — team approaches (wrap grasp, hook-and-rotate) remain a good reference for how to grasp/turn a valve, regardless of learning method.
- Residual Policy Learning — https://ar5iv.labs.arxiv.org/html/1812.06298 (kept as the reference for future-work RL, §10)
