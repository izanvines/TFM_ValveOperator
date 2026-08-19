# Copyright (c) 2026. TFM Universidad de Leon -- G1 abriendo valvulas de volante.
# SPDX-License-Identifier: Apache-2.0
"""Sirve una politica ACT (LeRobot) por la pila ZMQ nativa de Arena.

Gemelo de `arena_replay_server.py` y de `Gr00tRemoteServerSidePolicy`: mismo protocolo, mismas
claves de observacion, misma accion de 50 dimensiones. Esa simetria es el argumento de la
comparacion del TFM -- el comando del cliente es identico para las tres politicas y lo unico que
cambia es quien escucha en el puerto.

Corre en ~/venvs/lerobot-act (LeRobot 0.3.3, torch 2.7.1+cu128). NO puede correr dentro del
contenedor: el interprete de Isaac Sim tiene numpy 1.26 fijado y LeRobot moderno pide numpy >= 2.

    PYTHONPATH=~/TFM/IsaacLab-Arena:~/Desktop/VLA-HumanoidG1/train/scripts \
      ~/venvs/lerobot-act/bin/python -u \
      -m isaaclab_arena.remote_policy.remote_policy_server_runner \
      --policy_type act_remote_policy.ActRemoteServerSidePolicy \
      --host 127.0.0.1 --port 5561 --timeout_ms 120000 \
      --checkpoint ~/models/isaaclab_arena/g1_valve/act_valve_dryrun/checkpoints/020000/pretrained_model \
      --device cuda:1
"""
from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch
import yaml

from isaaclab_arena.remote_policy.action_protocol import ChunkingActionProtocol
from isaaclab_arena.remote_policy.server_side_policy import ServerSidePolicy

N_JOINTS = 43
IDX_NAV, IDX_BASE_H, IDX_TORSO = slice(43, 46), 46, slice(47, 50)
ACTION_DIM = 50
CAM_KEY = "camera_obs.robot_head_cam_rgb"
STATE_KEY = "policy.robot_joint_pos"


@dataclass
class ActRemoteArgs:
    checkpoint: str
    device: str = "cuda"
    stats_json: str | None = None
    embodiment_dir: str | None = None

    @classmethod
    def from_cli_args(cls, args: argparse.Namespace) -> "ActRemoteArgs":
        return cls(
            checkpoint=args.checkpoint,
            device=args.device,
            stats_json=args.stats_json,
            embodiment_dir=args.embodiment_dir,
        )


class ActRemoteServerSidePolicy(ServerSidePolicy):
    config_class = ActRemoteArgs

    def __init__(self, config: ActRemoteArgs) -> None:
        super().__init__(config)
        from lerobot.policies.act.modeling_act import ACTPolicy

        self.device = torch.device(config.device)
        self.policy = ACTPolicy.from_pretrained(config.checkpoint).to(self.device).eval()
        self.horizon = int(self.policy.config.chunk_size)
        print(f"[act] checkpoint {config.checkpoint}")
        print(f"[act] chunk_size={self.horizon} n_action_steps={self.policy.config.n_action_steps}")
        print(f"[act] input_features={list(self.policy.config.input_features)}")
        print(f"[act] output_features={list(self.policy.config.output_features)}")
        self._comprobar_buffers_de_normalizacion()

        # --- permutacion de juntas -------------------------------------------------------------
        # El dataset guarda estado y accion en orden de la POLITICA (grupos GR00T: piernas, cintura,
        # brazo+mano izq, brazo+mano der). El simulador manda y espera orden del SIMULADOR. Son
        # permutaciones puras de los mismos 43 nombres.
        emb = pathlib.Path(config.embodiment_dir) if config.embodiment_dir else self._buscar_embodiment_dir()
        sim_idx = yaml.safe_load((emb / "43dof_joint_space.yaml").read_text())["joints"]
        grupos = yaml.safe_load((emb / "gr00t_43dof_joint_space.yaml").read_text())["joints"]
        policy_names = [n for g in grupos.values() for n in g]
        assert sorted(policy_names) == sorted(sim_idx.keys()), "los dos YAML no declaran los mismos nombres"
        self.perm = np.array([sim_idx[n] for n in policy_names])   # politica[j] = sim[perm[j]]
        inv = np.empty_like(self.perm)
        inv[self.perm] = np.arange(N_JOINTS)
        assert np.array_equal(self.perm[inv], np.arange(N_JOINTS)), "la permutacion no es biyectiva"

        # --- altura de pelvis ------------------------------------------------------------------
        # Rellenar la cola de 7 dims con ceros es lo obvio y es un error: el indice 46 es
        # base_height_cmd y un cero pide pelvis a 0 m, con lo que el robot se sienta en el suelo.
        # El valor real de la sesion sale de las estadisticas, no se escribe a mano.
        self.base_height = self._leer_base_height(config.stats_json)
        print(f"[act] base_height_cmd = {self.base_height:.4f} (indice 46 de las 50)")

    def _comprobar_buffers_de_normalizacion(self) -> None:
        """Aborta si los buffers de normalizacion han llegado corruptos a la GPU.

        Medido el 2026-08-19 con torch 2.7.1+cu128 sobre 2x RTX PRO 6000: mover la politica a
        **`cuda:1`** pone a CERO la desviacion tipica de `normalize_inputs.buffer_observation_state`
        sin lanzar ningun error. `Normalize` divide entonces por `0 + 1e-8`, el estado normalizado
        sale del orden de 1e8, la red satura y `predict_action_chunk` devuelve exactamente ceros.
        En `cuda:0` los mismos pesos dan std minimo 5.075e-05 y acciones con std 0.299.

        El sintoma -- "la politica no hace nada" -- es indistinguible de un entrenamiento fallido,
        que es justo por lo que esto tiene que ser un error ruidoso y no una sorpresa en el
        simulador tres minutos despues.

        El rodeo es direccionar siempre la GPU como `cuda:0` y elegir cual con
        `CUDA_VISIBLE_DEVICES`.
        """
        import torch as _torch

        for nombre, buf in self.policy.normalize_inputs.named_parameters():
            if not nombre.endswith(".std"):
                continue
            minimo = float(buf.detach().abs().min())
            if minimo == 0.0:
                raise RuntimeError(
                    f"El buffer '{nombre}' llego con desviacion tipica 0 en {self.device}. "
                    "Los pesos estan bien; es el traslado a un indice de GPU distinto de 0 lo que "
                    "los corrompe. Relanza con CUDA_VISIBLE_DEVICES=<n> y --device cuda."
                )
        print("[act] buffers de normalizacion verificados en", self.device)

    @staticmethod
    def _buscar_embodiment_dir() -> pathlib.Path:
        import isaaclab_arena_gr00t

        p = pathlib.Path(isaaclab_arena_gr00t.__file__).parent / "embodiments" / "g1"
        assert p.exists(), f"no encuentro los YAML de juntas en {p}"
        return p

    @staticmethod
    def _leer_base_height(stats_json: str | None) -> float:
        if stats_json is None:
            raise ValueError(
                "Pasa --stats_json apuntando al meta/stats.json del dataset. La altura de pelvis "
                "se lee de ahi a proposito: escribirla a mano es como se acaba con el robot sentado."
            )
        s = json.loads(pathlib.Path(stats_json).expanduser().read_text())
        return float(s["teleop.base_height_command"]["mean"][0])

    # ---------------------------------------------------------------- protocolo

    def _build_protocol(self) -> ChunkingActionProtocol:
        proto = ChunkingActionProtocol(
            action_dim=ACTION_DIM,
            observation_keys=[CAM_KEY, STATE_KEY],
            action_chunk_length=self.horizon,
            action_horizon=self.horizon,
        )
        print(f"[act] protocolo = {proto.mode.value}, action_dim={ACTION_DIM}, horizonte={self.horizon}")
        return proto

    def set_task_description(self, task_description: str | None) -> dict[str, Any]:
        # ACT no esta condicionado por lenguaje; se acepta y se ignora para que el cliente sea
        # exactamente el mismo que con GR00T.
        self._task_description = task_description
        return {"status": "ok"}

    @torch.no_grad()
    def get_action(
        self, observation: dict[str, Any], options: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        anidada = self.unpack_observation(observation)
        rgb = np.asarray(anidada["camera_obs"]["robot_head_cam_rgb"])      # (N,H,W,C) uint8
        estado_sim = np.asarray(anidada["policy"]["robot_joint_pos"], dtype=np.float32)  # (N,43) orden sim

        # El preproceso tiene que coincidir con el del entrenamiento: LeRobot entrega (C,H,W)
        # float32 en [0,1]. Equivocarse aqui da una politica que emite la media del dataset, que a
        # simple vista es identico a "no ha aprendido".
        img = torch.from_numpy(rgb).to(self.device).permute(0, 3, 1, 2).float() / 255.0
        est = torch.from_numpy(estado_sim[:, self.perm]).to(self.device)   # sim -> politica

        lote = {"observation.images.ego_view": img, "observation.state": est}
        # ACT desnormaliza por dentro con los buffers del checkpoint: no tocar la normalizacion.
        chunk = self.policy.predict_action_chunk(lote)                    # (N, horizonte, 43) orden politica
        chunk_np = chunk.detach().float().cpu().numpy()

        n, h, _ = chunk_np.shape
        juntas_sim = np.empty((n, h, N_JOINTS), dtype=np.float32)
        juntas_sim[:, :, self.perm] = chunk_np                            # politica -> sim

        accion = np.zeros((n, h, ACTION_DIM), dtype=np.float32)
        accion[:, :, :N_JOINTS] = juntas_sim
        accion[:, :, IDX_NAV] = 0.0
        accion[:, :, IDX_BASE_H] = self.base_height
        accion[:, :, IDX_TORSO] = 0.0
        return {"action": accion}, {}

    def reset(self, env_ids: list[int] | None = None, reset_options: dict[str, Any] | None = None) -> dict[str, Any]:
        self.policy.reset()
        return {"status": "reset_success"}

    # ------------------------------------------------------------------- CLI

    @staticmethod
    def add_args_to_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
        g = parser.add_argument_group("ACT remote server", "Politica ACT de LeRobot servida por ZMQ.")
        g.add_argument("--checkpoint", type=str, required=True, help="directorio pretrained_model de ACT")
        g.add_argument("--device", type=str, default="cuda")
        g.add_argument("--stats_json", type=str, required=True, help="meta/stats.json del dataset")
        g.add_argument("--embodiment_dir", type=str, default=None,
                       help="directorio con los dos YAML de 43 DoF (por defecto, el de isaaclab_arena_gr00t)")
        return parser

    @staticmethod
    def from_args(args: argparse.Namespace) -> "ActRemoteServerSidePolicy":
        return ActRemoteServerSidePolicy(ActRemoteArgs.from_cli_args(args))
