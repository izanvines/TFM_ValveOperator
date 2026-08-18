# Política "mantener pose" para inspeccionar la escena sin que el G1 se desmorone.
#
# Por qué existe: `zero_action` manda la acción entera a cero, y en el espacio de acción del
# G1 WBC+Pink los índices [2:16] son las poses de muñeca izquierda y derecha. Ceros = ambas
# muñecas comandadas a (0,0,0), que es el ORIGEN DE LA PELVIS -> el robot junta las manos
# dentro del cuerpo, la IK de Pink devuelve una postura extrema y el robot se cae.
# (El cuaternión de norma cero no es el problema: `g1_decoupled_wbc_pink_action.py:254` ya lo
# sanea a identidad.)
#
# Esta política comanda una pose fija "en L" (brazo colgando, codo a 90 grados, antebrazo hacia
# delante), con las muñecas bien separadas para que las manos no colisionen entre sí.
#
# DOS DETALLES DE CONVENCIÓN QUE COSTARON UNA ITERACIÓN:
#   1. `left_wrist_pose_pelvis_frame` de la observación NO es pos+quat: es una MATRIZ 4x4
#      (`transforms.py::transform_pose_from_world_to_target_frame` devuelve el resultado de
#      `make_pose`). Leer sus 7 primeros valores da filas de la matriz de rotación, o sea
#      basura. Las observaciones limpias son `left_eef_pos` (3) y `left_eef_quat` (4).
#   2. `get_target_link_quaternion_in_target_frame` devuelve **wxyz** (convención IsaacLab),
#      pero la acción espera **xyzw** (ver `_identity_if_zero_norm_xyzw`). Hay que reordenar.
#
# Vive FUERA del repo a propósito, para no tocar el checkout. `policy_runner.py` acepta una
# ruta de importación con puntos, así que basta con tenerla en el PYTHONPATH:
#
#   PYTHONPATH=/eval/arena_extras \
#   /isaac-sim/python.sh isaaclab_arena/evaluation/policy_runner.py \
#     --policy_type hold_pose_policy.HoldPosePolicy ...
#
# Ajuste por variables de entorno (todo en frame de pelvis, metros):
#   HOLD_LEFT_POS  / HOLD_RIGHT_POS   "x,y,z"     posición de cada muñeca
#   HOLD_LEFT_QUAT / HOLD_RIGHT_QUAT  "x,y,z,w"   orientación (xyzw, como espera la acción)
#   HOLD_FROM_OBS=1                   congela la pose observada en el primer step en vez de
#                                     usar la pose fija (útil para ver la pose "natural")

import argparse
import gymnasium as gym
import os
import torch
from dataclasses import dataclass
from gymnasium.spaces.dict import Dict as GymSpacesDict

from isaaclab_arena.policy.policy_base import PolicyBase

# Layout de la acción del G1 WBC+Pink (23 dims), de action_constants.py
LEFT_WRIST_POS = slice(2, 5)
LEFT_WRIST_QUAT = slice(5, 9)
RIGHT_WRIST_POS = slice(9, 12)
RIGHT_WRIST_QUAT = slice(12, 16)
BASE_HEIGHT = 19

# Altura de pelvis que espera el WBC. Dejarla a 0 (como hace `zero_action`, y como hacía la
# primera versión de esta política) le pide al controlador que ponga la pelvis a 0 m: el robot
# obedece, se acuclilla y se sienta en el suelo en cada reset. El valor de referencia sale de
# `g1_decoupled_wbc_joint_action.py:86` ("base_height_cmd: 0.75 as pelvis height") y del test
# `test_g1_agile_policy.py:62` ("avoids squatting to match 0-height").
DEFAULT_BASE_HEIGHT = 0.75

# Pose "en L" por defecto, en frame de pelvis:
#   hombro a z~+0.27, brazo colgando ~0.20 -> codo a z~+0.05
#   antebrazo hacia delante ~0.22          -> muñeca a x~+0.22
# Las muñecas quedan separadas 0.40 m en Y, así que las manos no se tocan.
DEFAULT_LEFT_POS = (0.22, 0.20, 0.05)
DEFAULT_RIGHT_POS = (0.22, -0.20, 0.05)
DEFAULT_LEFT_QUAT = (0.0, 0.0, 0.0, 1.0)  # xyzw
DEFAULT_RIGHT_QUAT = (0.0, 0.0, 0.0, 1.0)


def _env_vec(name, default):
    raw = os.environ.get(name)
    if not raw:
        return default
    return tuple(float(v) for v in raw.split(","))


def _from_obs(observation, key):
    """Busca una clave en la observación, plana o agrupada (policy/wbc/action)."""
    if not isinstance(observation, dict):
        return None
    if key in observation:
        return observation[key]
    for group in observation.values():
        if isinstance(group, dict) and key in group:
            return group[key]
    return None


@dataclass
class HoldPosePolicyArgs:
    """Sin parámetros de CLI: todo se ajusta por variables de entorno."""

    @classmethod
    def from_cli_args(cls, args: argparse.Namespace) -> "HoldPosePolicyArgs":
        _ = args
        return cls()


class HoldPosePolicy(PolicyBase):
    """Comanda una pose de brazos fija y estable; el resto de la acción a cero."""

    name = "hold_pose"
    config_class = HoldPosePolicyArgs

    def __init__(self, config: HoldPosePolicyArgs | None = None):
        super().__init__(config if config is not None else HoldPosePolicyArgs())
        self._action: torch.Tensor | None = None
        self._from_obs = os.environ.get("HOLD_FROM_OBS", "0") == "1"
        self._left_pos = _env_vec("HOLD_LEFT_POS", DEFAULT_LEFT_POS)
        self._right_pos = _env_vec("HOLD_RIGHT_POS", DEFAULT_RIGHT_POS)
        self._left_quat = _env_vec("HOLD_LEFT_QUAT", DEFAULT_LEFT_QUAT)
        self._right_quat = _env_vec("HOLD_RIGHT_QUAT", DEFAULT_RIGHT_QUAT)
        self._base_height = float(os.environ.get("HOLD_BASE_HEIGHT", DEFAULT_BASE_HEIGHT))
        # HOLD_DEBUG_HEIGHT=N -> traza la altura de la raiz cada N steps (0 = desactivado).
        self._debug_every = int(os.environ.get("HOLD_DEBUG_HEIGHT", "0"))
        self._steps = 0

    @staticmethod
    def _wxyz_to_xyzw(q: torch.Tensor) -> torch.Tensor:
        return q[:, [1, 2, 3, 0]]

    def _build(self, env: gym.Env, observation) -> torch.Tensor:
        device = torch.device(env.unwrapped.device)
        action = torch.zeros(env.action_space.shape, device=device)
        n = action.shape[0]

        # Traza informativa: la pose natural del robot al arrancar, para poder compararla.
        lp, lq = _from_obs(observation, "left_eef_pos"), _from_obs(observation, "left_eef_quat")
        rp, rq = _from_obs(observation, "right_eef_pos"), _from_obs(observation, "right_eef_quat")
        if lp is not None and rp is not None:
            print(
                "[hold_pose] pose observada (frame pelvis) izq=%s der=%s"
                % (
                    [round(float(v), 3) for v in torch.as_tensor(lp).reshape(-1)[:3]],
                    [round(float(v), 3) for v in torch.as_tensor(rp).reshape(-1)[:3]],
                )
            )

        if self._from_obs and None not in (lp, lq, rp, rq):
            lp = torch.as_tensor(lp, device=device).reshape(n, -1)[:, :3]
            rp = torch.as_tensor(rp, device=device).reshape(n, -1)[:, :3]
            lq = self._wxyz_to_xyzw(torch.as_tensor(lq, device=device).reshape(n, -1)[:, :4])
            rq = self._wxyz_to_xyzw(torch.as_tensor(rq, device=device).reshape(n, -1)[:, :4])
            action[:, LEFT_WRIST_POS], action[:, LEFT_WRIST_QUAT] = lp, lq
            action[:, RIGHT_WRIST_POS], action[:, RIGHT_WRIST_QUAT] = rp, rq
            print("[hold_pose] congelando la pose observada (HOLD_FROM_OBS=1)")
        else:
            action[:, LEFT_WRIST_POS] = torch.tensor(self._left_pos, device=device)
            action[:, RIGHT_WRIST_POS] = torch.tensor(self._right_pos, device=device)
            action[:, LEFT_WRIST_QUAT] = torch.tensor(self._left_quat, device=device)
            action[:, RIGHT_WRIST_QUAT] = torch.tensor(self._right_quat, device=device)
            print(
                "[hold_pose] pose fija en L -> izq=%s der=%s (separación %.2f m)"
                % (list(self._left_pos), list(self._right_pos), abs(self._left_pos[1] - self._right_pos[1]))
            )

        # Sin esto el WBC se acuclilla hasta sentarse en cada reset.
        action[:, BASE_HEIGHT] = self._base_height
        print("[hold_pose] base_height_cmd = %.2f m" % self._base_height)

        return action

    def _report_stage_frames(self, env: gym.Env) -> None:
        """Vuelca los ejes REALES de los prims: zanja la convencion del cuaternion.

        La documentacion se contradice: `AssetBaseCfg.InitialStateCfg.rot` dice "(x,y,z,w)"
        con default (0,0,0,1), pero `asset_base.py` lo pasa sin convertir a `XFormPrim`, que
        documenta seis veces "scalar-first (w,x,y,z)". No hay conversion en medio (`validate()`
        solo comprueba campos MISSING), asi que solo lo resuelve mirar el resultado.

        El splat se spawnea con rot=(0.707107,-0.707107,0,0), que es maximamente diagnostico:
            leido wxyz -> giro de -90 sobre X   -> Z=(0,0,1) acaba en (0,+1,0)
            leido xyzw -> giro de 180 sobre (1,-1,0)/raiz(2) -> Z=(0,0,1) acaba en (0,0,-1)
        """
        from pxr import Gf, Usd, UsdGeom

        try:
            import isaacsim.core.utils.stage as stage_utils

            stage = stage_utils.get_current_stage()
        except Exception as exc:  # noqa: BLE001
            print(f"[hold_pose] no pude obtener el stage: {exc!r}")
            return

        basis = {"X": Gf.Vec3d(1, 0, 0), "Y": Gf.Vec3d(0, 1, 0), "Z": Gf.Vec3d(0, 0, 1)}
        for path in (
            "/World/envs/env_0/office_gs",
            "/World/envs/env_0/valve",
            "/World/envs/env_0/Robot",
        ):
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                print(f"[hold_pose] {path}: no existe")
                continue
            mat = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            trans = mat.ExtractTranslation()
            ejes = "  ".join(
                f"{n}->({(v := mat.TransformDir(b))[0]:+.3f},{v[1]:+.3f},{v[2]:+.3f})" for n, b in basis.items()
            )
            print(f"[hold_pose] {path}")
            print(f"              pos=({trans[0]:+.3f},{trans[1]:+.3f},{trans[2]:+.3f})  {ejes}")

    def _report_height(self, env: gym.Env) -> None:
        """Altura real de la raiz del robot: convierte "¿se cae?" en un numero.

        Sirve para dos comprobaciones que a ojo son ambiguas: que el WBC levanta la pelvis a
        `base_height_cmd` y no se sienta, y que el suelo invisible (`GroundPlaneCfg(visible=
        False)`) sigue colisionando -- si la altura cae monotona hacia valores negativos, el
        robot esta atravesando el suelo y la colision se perdio.
        """
        try:
            scene = env.unwrapped.scene
        except AttributeError:
            return
        for key in ("robot", "embodiment", "g1"):
            asset = None
            try:
                asset = scene[key]
            except (KeyError, TypeError):
                continue
            if asset is None or not hasattr(asset, "data"):
                continue
            # Ojo: con `use_fabric=True` esto no es un tensor de torch sino un array de warp
            # (de vec3), que no admite indexado 2D -> `[0, 2]` revienta con "tuple index out
            # of range". Se convierte antes y se aplana, que funciona para (N,3) y para (3,).
            pos = asset.data.root_pos_w
            if not torch.is_tensor(pos):
                import warp as wp

                pos = wp.to_torch(pos)
            z = float(pos.reshape(-1)[2])
            flag = "OK" if z > 0.4 else "CAIDO/ATRAVESANDO"
            print(f"[hold_pose] step {self._steps:6d}  altura raiz = {z:+.3f} m  [{flag}]")
            return
        try:
            print(f"[hold_pose] no encontre el robot en la escena; claves = {list(scene.keys())}")
        except Exception:
            pass

    def get_action(self, env: gym.Env, observation: GymSpacesDict) -> torch.Tensor:
        if self._action is None:
            self._action = self._build(env, observation)
        if self._steps == 0 and os.environ.get("HOLD_DEBUG_STAGE", "0") == "1":
            try:
                self._report_stage_frames(env)
            except Exception as exc:  # noqa: BLE001
                print(f"[hold_pose] volcado de ejes fallido: {exc!r}")
        if self._debug_every and self._steps % self._debug_every == 0:
            # La telemetria es un extra: jamas debe tumbar una ejecucion larga.
            try:
                self._report_height(env)
            except Exception as exc:  # noqa: BLE001
                print(f"[hold_pose] traza de altura desactivada tras un fallo: {exc!r}")
                self._debug_every = 0
        self._steps += 1
        return self._action

    @staticmethod
    def add_args_to_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
        return parser

    @staticmethod
    def from_args(args: argparse.Namespace) -> "HoldPosePolicy":
        return HoldPosePolicy(HoldPosePolicyArgs.from_cli_args(args))
