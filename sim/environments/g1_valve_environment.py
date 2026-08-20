# Copyright (c) 2026. TFM: G1 valve manipulation.
# SPDX-License-Identifier: Apache-2.0

"""Static-base G1 valve-opening environment (WBC/AGILE balance, no locomotion).

A deliberately bare ("diáfano") scene: just a ground plane, a dome light, the G1 humanoid
standing in place under AGILE whole-body balance, and a standpipe hand-wheel valve in front
of it. The task is to reach out and turn the wheel to open the valve.

This mirrors the structure of ``galileo_g1_static_pick_and_place_environment`` but:
  * drops the warehouse background for an empty ground+light scene,
  * swaps the apple/plate rigid objects for the ``valve`` articulation (``Openable``), now
    backed by jescobars' CAD rig rather than the procedural placeholder,
  * swaps ``PickAndPlaceTask`` for ``OpenDoorTask`` (rotate-a-revolute-joint, success on
    openness > threshold).

Poses are MEASURED, not guessed: see `/eval/arena_extras/measure_valve_rig.py`, which
reads the wheel body's real world pose out of the articulation and characterises where the
WBC actually leaves the robot after a reset. The constants below carry the numbers and the
reasoning; re-run that script before changing any of them.
"""

from __future__ import annotations

import argparse
import os
from typing import TYPE_CHECKING

from isaaclab_arena_environments.example_environment_base import ExampleEnvironmentBase

if TYPE_CHECKING:
    from isaaclab_arena.environments.isaaclab_arena_environment import IsaacLabArenaEnvironment


# Geometry of the CAD rig, MEASURED in-sim rather than derived -- see
# `/eval/arena_extras/measure_valve_rig.py`, which reads the wheel body's actual world
# pose out of the articulation instead of assuming an offset.
#
# The naive derivation is wrong and it is worth saying why. The rig authors its hand-wheel
# 0.122 m along the asset's local +Z, so rotating the asset about world Z "obviously"
# leaves that offset in z. It does not: the rig also bakes a `FixedJoint` whose
# `localRot1` is -90 deg about X, which reorients the bodies relative to the articulation
# root before our spawn rotation is applied. The two compose to send local +Z onto world
# -X, and the measurement confirms it:
#
#     wheel centre = VALVE_SPAWN_XYZ + (-0.10, 0, 0)
#
# The wheel's rotation axis lands along world X, pointing at the robot -- correct for a
# hand-wheel you face and turn, and consistent with the offset, since the wheel sits at
# the end of an axle stub pointing the same way.
#
# Arena's Pose takes the quaternion as XYZW. jescobars' scene authored the same rotation
# in USD's WXYZ order as (0.707, 0, 0, 0.707) -- do not paste that in directly.
# Lowered from z=1.00 to z=0.80 on 2026-08-18: at 1.00 the wheel sat 0.26 m above the
# pinned pelvis, roughly chest height, and came out halfway up the robot's head camera --
# the frame that IS the policy's input. 0.80 puts it just above the wrists' resting height
# (0.762), which is also the natural posture for a two-handed grip you have to pull against.
VALVE_SPAWN_XYZ = (0.55, 0.0, 0.80)  # -> wheel centre at (0.45, 0, 0.80)
VALVE_SPAWN_QUAT_XYZW = (0.0, 0.0, 0.70710678, 0.70710678)  # +90 deg about Z

# --- Las dos disposiciones de valvula --------------------------------------------------------
#
# Las dos existen en planta y la politica deberia resolver ambas:
#
#   frontal  el volante mira al robot, eje horizontal. Es una valvula sobre una linea VERTICAL,
#            y se gira de frente, como un timon. Es la que se grabo en sesion_01.
#   cenital  el volante mira hacia arriba, eje vertical. Es una valvula sobre una linea
#            HORIZONTAL, y se gira alcanzando por encima.
#
# La rotacion de `cenital` sale de anadir -90 grados sobre Y a la de `frontal`. El motivo de que
# sea sobre Y y no sobre algo mas evidente: el eje de giro de la rueda NO es un eje del asset tal
# cual. El rig CAD lleva un `FixedJoint` con `localRot1` de -90 grados en X que reorienta los
# cuerpos ANTES de aplicar la rotacion de spawn, asi que con la rotacion `frontal` el eje acaba en
# X del mundo (medido, no derivado). Llevar ese eje de X a Z es lo que hace el -90 sobre Y.
#
# Y por eso mismo el offset del centro de la rueda -- (-0.10, 0, 0) respecto a VALVE_SPAWN_XYZ en
# la disposicion frontal -- NO vale para la cenital: rota con la orientacion. Hay que medirlo con
# `measure_valve_rig.py`, que lee la pose real del cuerpo de la rueda en vez de derivarla.
#
# ALTURAS. La frontal esta a 0.80 m, justo por encima de la altura de reposo de las munecas
# (0.762), que es la postura natural para tirar de un volante con las dos manos. La cenital pide
# otra cosa: para girar desde arriba el volante tiene que quedar POR DEBAJO de las munecas, o el
# operador acaba con la muneca doblada. El valor es provisional hasta medirlo y probarlo con las
# gafas.
VALVE_LAYOUTS = {
    "frontal": {
        "quat_xyzw": (0.0, 0.0, 0.70710678, 0.70710678),
        "pos": (0.55, 0.0, 0.80),  # -> rueda en (0.45, 0, 0.80)
    },
    "cenital": {
        "quat_xyzw": (-0.5, -0.5, 0.5, 0.5),
        "pos": (0.45, 0.0, 0.76),  # -> rueda en (0.45, 0, 0.66)
    },
}

# MEDIDO con `measure_valve_rig.py` el 2026-08-20, y es la razon de que cada disposicion lleve su
# posicion completa en vez de compartir XY y cambiar solo la altura:
#
#   disposicion   raiz -> centro de la rueda      dist. munecas
#   frontal       (-0.10,  0,     0)              0.33 - 0.38 m
#   cenital       (  0,    0,  -0.10)             0.46 - 0.48 m  <- con la raiz en (0.55, 0, 0.62)
#
# El offset ROTA con la orientacion, igual que rotaba el de la disposicion frontal respecto a la
# geometria del asset. En cenital la rueda no se acerca 10 cm en X, sino que baja 10 cm, asi que
# con la misma raiz queda mas baja Y mas lejos: 0.46 m contra 0.33, y 0.22 m por debajo de la
# pelvis. Bajando la raiz a X=0.45 y subiendola a Z=0.76 la rueda acaba en (0.45, 0, 0.66),
# a ~0.10 m por debajo de las munecas (0.762) -- que es la altura util para girar por encima --
# y a una distancia comparable a la de la disposicion frontal.

# Jitter de posicion por episodio, en metros. Acotado por el alcance: el volante queda a 0.45 m de
# la pelvis y las munecas descansan a 0.762 m, asi que no sobra margen antes de que el operador
# tenga que forzar la postura. Se aplica sobre XY y sobre la Z propia de cada disposicion.
VALVE_JITTER_XYZ = (0.04, 0.06, 0.03)

# Fuerza una disposicion concreta en vez de sortearla. Sirve para medir y para grabar sesiones
# dedicadas a una sola disposicion. Vacio = sorteo 50/50 en cada reset.
VALVE_LAYOUT_FIJA = os.environ.get("ARENA_VALVE_LAYOUT", "").strip().lower() or None
if VALVE_LAYOUT_FIJA is not None and VALVE_LAYOUT_FIJA not in VALVE_LAYOUTS:
    raise ValueError(
        f"ARENA_VALVE_LAYOUT={VALVE_LAYOUT_FIJA!r} no existe. Opciones: {sorted(VALVE_LAYOUTS)}"
    )

# SPAWN THE ROBOT ALREADY STANDING. This is the single most important line in the file
# for data quality, and z=0 -- inherited from the pick-and-place env this was derived from
# -- is wrong once anything sits within arm's reach in front of the robot.
#
# At z=0 the pelvis starts inside the floor and the AGILE WBC hauls the whole robot upward
# over the first ~100 steps, sweeping the torso and arms through the space the valve
# occupies. Measured over 5 resets each (`measure_valve_rig.py --repeats 5
# --settle_steps 120`, holding a stable arm pose at base_height_cmd = 0.75):
#
#   spawn z=0,    valve in front   sigma (0.300, 0.149, 0.310) m, 1 of 5 resets fell over
#   spawn z=0,    valve behind     sigma (0.029, 0.029, 0.024) m, no falls
#   spawn z=0.74, valve in front   sigma (0.001, 0.001, 0.001) m, no falls
#
# Same scene, same physics: the only thing that changes is whether the robot has to stand
# up through the valve. Spawning it at standing height makes the reset essentially
# deterministic -- one millimetre of spread -- and that matters far beyond tidiness. Every
# demonstration starts from the same pose, so the policy learns the task instead of
# learning to compensate for a random initial condition, and a failed rollout at
# evaluation time is attributable to the policy rather than to a bad reset.
#
# One trap this measurement disarmed: with the zero action the robot does NOT settle at
# all. Index [19] is base_height_cmd, and zero commands pelvis height 0, so it obediently
# sits on the floor -- any reach figure taken that way describes a robot lying down.
#
# Resulting geometry: pelvis settles at (-0.067, 0.007, 0.755), wheel centre at
# (0.45, 0, 1.00) -- 0.52 m in front of and 0.25 m above the settled pelvis, with both
# wrists measuring 0.44 m from the wheel in the neutral hold pose. Comfortably inside the
# G1's reach rather than at the edge of it, which leaves room for the operator commanding
# very different wrist targets during teleoperation than the fixed pose used here.
ROBOT_SPAWN_XYZ = (0.0, 0.0, 0.74)

# Success when the wheel is turned past this fraction of its 0..360 deg travel.
OPENNESS_SUCCESS_THRESHOLD = 0.5

# Episode budget. NVIDIA's data-collection guidance targets 200-400 timesteps per episode;
# the env steps at 50 Hz (dt=0.005 with decimation 4), so 8 s is ~400 steps -- the top of
# that range.
#
# Raised to 15 s when the procedural placeholder was replaced by the CAD rig. The rig
# drives its wheel with `damping=100, maxForce=1000, stiffness=0`, i.e. a genuinely heavy
# valve, so half a revolution takes longer to teleoperate than it did against the
# frictionless placeholder. This is a *ceiling*, not a target -- episodes terminate on
# success, so a demo the operator completes in 6 s is still recorded as 6 s and a generous
# ceiling costs only the time to abort a failed attempt. The asymmetry matters: too tight
# and demos die by timeout and are never written to the HDF5, which is silent and only
# discovered after the recording session.
EPISODE_LENGTH_S = float(os.environ.get("ARENA_VALVE_EPISODE_S", "15.0"))




def randomize_valve_layout(
    env,
    env_ids,
    asset_cfg,
    layouts: dict,
    jitter_xyz: tuple,
    layout_fijo: str | None = None,
) -> None:
    """Sortea disposicion y posicion de la valvula en cada reset.

    Dos disposiciones discretas, no un rango continuo. Arena convierte un `PoseRange` en un
    `randomize_object_pose` que muestrea UNIFORME, y eso daria valvulas a 37 o 62 grados --
    orientaciones que en una refineria no existen y que ensucian el argumento del TFM. Las dos que
    se sortean aqui (volante de frente sobre linea vertical, volante hacia arriba sobre linea
    horizontal) existen las dos en planta.

    La posicion lleva ademas un jitter uniforme por episodio. Sin el, todos los episodios arrancan
    identicos y la politica puede resolver la tarea memorizando una trayectoria en vez de mirando
    la camara: medido el 2026-08-19, GR00T y ACT dieron 10/10 los dos sobre 25 demos sin variacion,
    que es un empate del que no se concluye nada.

    Se delega en `set_object_pose` de Arena en vez de escribir la pose a mano: `Pose.to_tensor`
    devuelve el cuaternion en xyzw y la convencion que espera IsaacLab no coincide con la que
    sugiere el nombre del campo. Reutilizar el camino que ya funciona evita repetir ese error.

    La pose sorteada NO hay que guardarla aparte: `InitialStateRecorder` graba
    `initial_state/articulation/valve/root_pose` en el post-reset, y `env.reset_to` la restaura al
    re-renderizar, asi que la etapa B reproduce la disposicion exacta de cada episodio.
    """
    import random

    from isaaclab_arena.terms.events import set_object_pose
    from isaaclab_arena.utils.pose import Pose

    if env_ids is None:
        return

    nombres = sorted(layouts)
    for _ in (env_ids.tolist() if hasattr(env_ids, "tolist") else list(env_ids)):
        elegido = layout_fijo if layout_fijo else random.choice(nombres)
        cfg = layouts[elegido]
        base = cfg["pos"]
        pos = tuple(base[i] + random.uniform(-jitter_xyz[i], jitter_xyz[i]) for i in range(3))
        set_object_pose(
            env,
            env_ids,
            asset_cfg=asset_cfg,
            pose=Pose(position_xyz=pos, rotation_xyzw=cfg["quat_xyzw"]),
        )
        # `set_object_pose` escribe la MISMA pose en todos los env_ids, asi que con varios entornos
        # todos compartirian disposicion. Con num_envs=1 (lo unico que admite el embodiment de
        # teleoperacion) es correcto; si algun dia hacen falta varios, hay que trocear env_ids.
        break


def _apply_nurec_render_settings() -> None:
    """Reaplica los ajustes de render que un asset NuRec declara y que Arena pierde al referenciarlo.

    Un `.usd`/`.usdz` de NuRec lleva sus ajustes de render en el `customLayerData` de su capa raiz.
    Cuando abres el fichero a mano en Isaac Sim, esa es la capa raiz del stage y Kit los aplica: se
    ve nitido, con ray tracing, a 60 fps. Cuando Arena lo mete como fondo, el asset pasa a ser una
    capa **referenciada**, y USD ignora el `customLayerData` de las capas referenciadas. Los
    ajustes se caen en silencio -- no hay aviso, no hay error, solo se ve mal.

    Dos de ellos son la diferencia entre que funcione y que no:

        rtx:post:registeredCompositing:invertToneMap
        rtx:post:registeredCompositing:invertColorCorrection

    `registeredCompositing` es la etapa donde se componen las gaussianas de NuRec. Esos dos flags
    le dicen que deshaga el mapeo de tonos y la correccion de color antes de componer. Sin ellos el
    splat se tonemapea DOS VECES y sale lavado a blanco. Medido el 2026-08-19: la camara del robot
    daba media 250 sobre 255 con el fondo puesto, y apagar la dome light no cambiaba nada -- porque
    no era iluminacion, era post-proceso.

    Los nueve valores son los que declaran los tres assets que hay en disco (`living_sim.usdz`,
    `office_video_nurec.usdz` y su version podada), identicos en los tres. Los nombres estan
    verificados contra las cadenas de `librtx.hydra.so`, no inventados.

    Se aplican por `carb.settings` en vez de por `--kit_args` para que no dependan de que alguien
    se acuerde de pasar diez flags en cada lanzamiento.
    """
    ajustes = {
        "/rtx/rendermode": "RaytracedLighting",
        "/rtx/post/tonemap/op": 2,
        "/rtx/post/registeredCompositing/enabled": True,
        "/rtx/post/registeredCompositing/invertColorCorrection": True,
        "/rtx/post/registeredCompositing/invertToneMap": True,
        "/rtx/post/histogram/enabled": False,
        "/rtx/directLighting/sampledLighting/samplesPerPixel": 8,
        "/rtx/material/enableRefraction": False,
        "/rtx/matteObject/visibility/secondaryRays": True,
        "/rtx/raytracing/fractionalCutoutOpacity": False,
    }
    try:
        import carb

        s = carb.settings.get_settings()
        for k, v in ajustes.items():
            s.set(k, v)
        print(f"[arena] NuRec: reaplicados {len(ajustes)} ajustes de render del asset")
    except Exception as exc:  # pragma: no cover - depende del runtime de Kit
        print(f"[arena] AVISO: no se pudieron aplicar los ajustes de render de NuRec: {exc}")

class G1ValveEnvironment(ExampleEnvironmentBase):
    """G1 (WBC/AGILE, no nav) opening a hand-wheel valve on an empty ground plane."""

    name: str = "g1_valve"

    def get_env(self, args_cli: argparse.Namespace) -> IsaacLabArenaEnvironment:
        from isaaclab_arena.environments.isaaclab_arena_environment import IsaacLabArenaEnvironment
        from isaaclab_arena.scene.scene import Scene
        from isaaclab_arena.tasks.open_door_task import OpenDoorTask
        from isaaclab_arena.utils.pose import Pose

        # --- Diáfano scene: ground plane + dome light (no background USD) ---
        # With a photorealistic backdrop the 100x100 m grid mesh is a problem: it is opaque,
        # extends far beyond the room and sits at the exact height of the reconstructed floor,
        # so it hides the office and z-fights with it. Hiding it costs nothing physically --
        # `spawn_ground_plane` ends in `set_prim_visibility(prim, cfg.visible)`, and USD
        # visibility does not disable PhysX: collision comes from PhysicsCollisionAPI on
        # `GroundPlane/CollisionPlane`, which is already `purpose = "guide"` (never drawn).
        # So the robot still stands on a solid floor, you just see the office instead.
        from isaaclab.sim.spawners.from_files.from_files_cfg import GroundPlaneCfg as _GroundPlaneCfg

        _has_background = getattr(args_cli, "background", "none") not in (None, "none")
        _show_grid = getattr(args_cli, "show_ground_grid", False) or not _has_background
        ground = self.asset_registry.get_asset_by_name("ground_plane")(
            spawner_cfg=_GroundPlaneCfg(visible=_show_grid)
        )
        # Dome light intensity is configurable via OFFICE_GS_LIGHT: a photorealistic
        # splat backdrop carries baked-in lighting, so a bright dome washes it out to
        # white. Default keeps the original 3000 for the diafano scene.
        import os as _os
        from isaaclab.sim import DomeLightCfg as _DomeLightCfg

        _light_intensity = float(_os.environ.get("OFFICE_GS_LIGHT", "3000"))
        light = self.asset_registry.get_asset_by_name("light")(
            spawner_cfg=_DomeLightCfg(color=(0.75, 0.75, 0.75), intensity=_light_intensity)
        )

        # --- The valve (articulated Openable object) ---
        valve = self.asset_registry.get_asset_by_name("valve")()
        valve.set_initial_pose(Pose(position_xyz=VALVE_SPAWN_XYZ, rotation_xyzw=VALVE_SPAWN_QUAT_XYZW))

        # --- The G1 embodiment with AGILE whole-body balance ---
        embodiment = self.asset_registry.get_asset_by_name(args_cli.embodiment)(
            enable_cameras=args_cli.enable_cameras,
            lock_waist=args_cli.lock_waist,
        )
        # Mirror the robot setup of ``galileo_g1_static_pick_and_place``: both are
        # static-base manipulation tasks on the same embodiment, so the same two calls
        # apply here. Without them the robot spawns with its arms pinned to the torso and
        # the WBC has to unfold them while it is *also* lifting the pelvis off the floor;
        # it settles leaning backwards and pushes the valve out of reach.
        #   * High-friction fingers: needed to hold the wheel spokes without slipping.
        #   * Open-arm posture: shoulder roll/yaw only, arms clear of the torso.
        from isaaclab_arena_environments.mdp.galileo_g1_static_pick_and_place.robot_configs import (
            G1_STATIC_FINGER_DYNAMIC_FRICTION,
            G1_STATIC_FINGER_FRICTION_MATERIAL_PATH,
            G1_STATIC_FINGER_PRIM_NAME_MARKERS,
            G1_STATIC_FINGER_STATIC_FRICTION,
            G1_STATIC_OPEN_ARM_JOINT_POS,
        )

        embodiment.set_finger_contact_friction(
            material_path=G1_STATIC_FINGER_FRICTION_MATERIAL_PATH,
            static_friction=G1_STATIC_FINGER_STATIC_FRICTION,
            dynamic_friction=G1_STATIC_FINGER_DYNAMIC_FRICTION,
            prim_name_markers=G1_STATIC_FINGER_PRIM_NAME_MARKERS,
        )
        # WBC lifts the pelvis to standing height at runtime, so init z = 0 is correct.
        embodiment.set_initial_pose(Pose(position_xyz=ROBOT_SPAWN_XYZ, rotation_xyzw=(0.0, 0.0, 0.0, 1.0)))
        embodiment.set_joint_initial_pos(G1_STATIC_OPEN_ARM_JOINT_POS)

        # --- Fixed pelvis -------------------------------------------------------------
        # Turning a hand-wheel feeds a reaction torque back through the arms. With a free
        # root the AGILE balance controller absorbs it the only way it can: by rotating the
        # whole robot. Observed in the headset on 2026-08-18 -- the operator turns the wheel
        # and the robot swings round with it.
        #
        # That is fatal for the dataset, not merely ugly. Every demonstration would encode
        # "the base drifts while I turn" as part of the skill, the wheel would leave arm
        # reach mid-episode, and the wrist poses the policy regresses on are expressed in the
        # pelvis frame -- a pelvis that moves makes identical hand motions look like
        # different actions.
        #
        # `ARENA_STATIC_BASE=1` is NOT enough: it freezes the locomotion *commands*
        # (`g1_pink_locomanipulation_pipeline.py:153`), so the operator cannot walk the robot
        # away, but the base is still a free-floating body that reacts to contact forces.
        # Pinning the root link is what actually holds it.
        #
        # AGILE keeps running and keeps the legs in a standing posture; it simply no longer
        # has a pelvis it can move. The action space is untouched at 23 dims, so every
        # downstream config (the 43-DoF joint space, the GR00T conversion, the recorder
        # terms) stays valid.
        #
        # Set ARENA_FIX_BASE=0 to get the free-floating balancing robot back.
        _fix_base = _os.environ.get("ARENA_FIX_BASE", "1") not in ("0", "", "false", "False")
        if _fix_base:
            embodiment.scene_config.robot.spawn.articulation_props.fix_root_link = True
            print("[arena] ARENA_FIX_BASE: pelvis pinned to the world (fix_root_link=True)")

        if args_cli.teleop_device is not None:
            teleop_device = self.device_registry.get_device_by_name(args_cli.teleop_device)()
        else:
            teleop_device = None

        task = OpenDoorTask(
            openable_object=valve,
            openness_threshold=OPENNESS_SUCCESS_THRESHOLD,
            reset_openness=0.0,  # every episode starts with the valve closed
            episode_length_s=EPISODE_LENGTH_S,
            task_description=args_cli.task_description,
        )

        # --- Encuadre de la camara de tercera persona -----------------------------------
        # `RotateRevoluteJointTask.get_viewer_cfg` mira a la valvula desde
        # `offset = (-1.3, -1.3, 1.3)`. Sirve para depurar, pero para las figuras y los videos de
        # la memoria deja al robot pequeno, descentrado y visto desde arriba: el volante -- que es
        # lo unico que importa -- ocupa unos pocos pixeles.
        #
        # El encuadre bueno es lateral y a la altura del pecho, mirando al punto medio entre la
        # pelvis del robot y el volante, para que se vean a la vez las manos y lo que hacen. Se
        # sobreescribe aqui en vez de tocar la clase de upstream porque es una preferencia de este
        # TFM, no un defecto de Arena. `ARENA_VIEW_OFFSET="x,y,z"` lo cambia sin editar codigo.
        from isaaclab.envs import ViewerCfg as _ViewerCfg

        _off = _os.environ.get("ARENA_VIEW_OFFSET", "0.35,-1.45,0.30")
        _dx, _dy, _dz = (float(v) for v in _off.split(","))
        _mira = (
            (ROBOT_SPAWN_XYZ[0] + VALVE_SPAWN_XYZ[0]) / 2.0,
            (ROBOT_SPAWN_XYZ[1] + VALVE_SPAWN_XYZ[1]) / 2.0,
            VALVE_SPAWN_XYZ[2] - 0.05,
        )
        _ojo = (_mira[0] + _dx, _mira[1] + _dy, _mira[2] + _dz)
        _vista = _ViewerCfg(eye=_ojo, lookat=_mira, origin_type="env")
        task.get_viewer_cfg = lambda _v=_vista: _v
        print(f"[arena] camara de tercera persona: ojo={_ojo} mira={_mira}")

        # Optional photorealistic backdrop (Gaussian Splatting / NuRec) for sim2real.
        scene_assets = [ground, light, valve]
        if getattr(args_cli, "background", "none") not in (None, "none"):
            background = self.asset_registry.get_asset_by_name(args_cli.background)()
            scene_assets.insert(0, background)
            if "nurec" in getattr(background, "tags", []):
                _apply_nurec_render_settings()

        scene = Scene(assets=scene_assets)
        # --- Sorteo de disposicion y posicion de la valvula ---------------------------------
        # Se sustituye el evento `valve` que Arena genera solo. `object_base._init_event_cfg()`
        # mira el tipo de la pose inicial: con un `Pose` fijo produce un `set_object_pose` con esa
        # pose, y con un `PoseRange` un `randomize_object_pose` que muestrea UNIFORME. Ninguno de
        # los dos sirve: queremos DOS disposiciones discretas mas jitter, no un continuo.
        #
        # Se hace por `env_cfg_callback` para no tocar el nucleo de Arena; es el gancho que existe
        # justo para esto (`arena_env_builder.py:272`).
        from isaaclab.managers import EventTermCfg as _EventTermCfg
        from isaaclab.managers import SceneEntityCfg as _SceneEntityCfg

        def _sortear_valvula(env_cfg):
            env_cfg.events.valve = _EventTermCfg(
                func=randomize_valve_layout,
                mode="reset",
                params={
                    "asset_cfg": _SceneEntityCfg("valve"),
                    "layouts": VALVE_LAYOUTS,
                    "jitter_xyz": VALVE_JITTER_XYZ,
                    "layout_fijo": VALVE_LAYOUT_FIJA,
                },
            )
            return env_cfg

        if VALVE_LAYOUT_FIJA:
            print(f"[arena] valvula: disposicion FIJA '{VALVE_LAYOUT_FIJA}'")
        else:
            print(f"[arena] valvula: sorteo entre {sorted(VALVE_LAYOUTS)} + jitter {VALVE_JITTER_XYZ} m")

        return IsaacLabArenaEnvironment(
            name=self.name,
            embodiment=embodiment,
            scene=scene,
            task=task,
            teleop_device=teleop_device,
            env_cfg_callback=_sortear_valvula,
        )

    @staticmethod
    def add_cli_args(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--embodiment", type=str, default="g1_wbc_agile_pink")
        parser.add_argument(
            "--background",
            type=str,
            default="none",
            help=(
                "Visual background. 'none' keeps the empty diafano scene; 'office_gs' "
                "overlays the office Gaussian-Splatting (NuRec) backdrop."
            ),
        )
        parser.add_argument(
            "--show_ground_grid",
            action="store_true",
            help=(
                "Keep the 100x100 m grid mesh visible even with a background loaded. Off by "
                "default because it hides the reconstructed floor; the collider is unaffected "
                "either way, so this is purely a debug aid for checking where z=0 is."
            ),
        )
        parser.add_argument("--teleop_device", type=str, default=None)
        parser.add_argument(
            "--task_description",
            type=str,
            default="Reach out and turn the wheel to open the valve.",
            help="Natural-language task description for language-conditioned policies.",
        )
        parser.add_argument(
            "--lock_waist",
            action=argparse.BooleanOptionalAction,
            default=True,
            help=(
                "Lock the waist joints out of the upper-body Pink IK so the torso stays fixed "
                "during teleoperation and recording. On by default for this static task."
            ),
        )
