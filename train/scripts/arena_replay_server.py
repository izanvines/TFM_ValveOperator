# Copyright (c) 2026. TFM Universidad de Leon -- G1 abriendo valvulas de volante.
# SPDX-License-Identifier: Apache-2.0
"""Sirve las acciones grabadas de un episodio como si fueran una politica.

**Para que existe.** Las demostraciones se grabaron con el embodiment `g1_wbc_agile_pink`: 23
dimensiones, poses de muneca que Pink IK convierte en juntas. La columna `action` del dataset
LeRobot es `processed_actions`, o sea las **43 juntas de salida** de esa IK. Ninguna politica puede
emitir las 23 dimensiones originales porque en el repositorio no hay inversa 43 -> 23; la solucion
de upstream es evaluar con `g1_wbc_agile_joint` (50 dims = 43 juntas + 3 navegacion + 1 altura de
pelvis + 3 orientacion de torso).

Es decir: en evaluacion metemos la *salida* del controlador de cuerpo completo como su *entrada*.
Ese viaje de ida y vuelta no lo prueba nada en el repositorio. Si no gira la valvula, ninguna
politica entrenada sobre esa columna lo hara, y las 400 demostraciones definitivas necesitan otra
representacion de accion. Este servidor lo responde en 40 minutos y sin entrenar nada: es la cota
superior de todo lo que venga despues.

Corre en el host, dentro del venv de GR00T (trae numpy/pyarrow/yaml/zmq). El simulador se conecta
como cliente por ZMQ; el contenedor va en `network_mode: host`, asi que 127.0.0.1 es compartido.

    PYTHONPATH=~/TFM/IsaacLab-Arena:~/Desktop/VLA-HumanoidG1/train/scripts \
      ~/TFM/isaac-gr00t-standalone/.venv/bin/python -u \
      -m isaaclab_arena.remote_policy.remote_policy_server_runner \
      --policy_type arena_replay_server.ArenaReplayServerSidePolicy \
      --host 127.0.0.1 --port 5555 --timeout_ms 120000 \
      --dataset_path ~/datasets/isaaclab_arena/g1_valve/sesion_01/lerobot --episode_index 0
"""
from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import dataclass
from typing import Any

import numpy as np
import pyarrow.parquet as pq
import yaml

from isaaclab_arena.remote_policy.action_protocol import ChunkingActionProtocol
from isaaclab_arena.remote_policy.server_side_policy import ServerSidePolicy

# Disposicion de las 50 dimensiones, identica a `gr00t_core.build_gr00t_action_np`:
#   [0:43]  juntas en orden del SIMULADOR   [43:46] navigate_cmd
#   [46:47] base_height_cmd                 [47:50] torso_orientation_rpy_cmd
N_JOINTS = 43
IDX_NAV, IDX_BASE_H, IDX_TORSO = slice(43, 46), 46, slice(47, 50)
ACTION_DIM = 50


@dataclass
class ArenaReplayArgs:
    dataset_path: str
    episode_index: int = 0
    action_horizon: int = 40
    dump_obs_npy: str | None = None

    @classmethod
    def from_cli_args(cls, args: argparse.Namespace) -> "ArenaReplayArgs":
        return cls(
            dataset_path=args.dataset_path,
            episode_index=args.episode_index,
            action_horizon=args.action_horizon,
            dump_obs_npy=args.dump_obs_npy,
        )


class ArenaReplayServerSidePolicy(ServerSidePolicy):
    """Reproduce las acciones grabadas de un episodio, ignorando la observacion."""

    config_class = ArenaReplayArgs

    def __init__(self, config: ArenaReplayArgs) -> None:
        super().__init__(config)
        root = pathlib.Path(config.dataset_path).expanduser()
        info = json.loads((root / "meta" / "info.json").read_text())
        k = config.episode_index
        parquet = root / "data" / f"chunk-{k // info['chunks_size']:03d}" / f"episode_{k:06d}.parquet"

        acciones_politica = np.asarray(
            pq.read_table(parquet).column("action").to_pylist(), dtype=np.float32
        )  # (N, 43) en orden de la POLITICA (grupos GR00T)

        # La permutacion es pura: los dos YAML declaran los mismos 43 nombres en distinto orden.
        arena = pathlib.Path(__file__).resolve()
        emb = self._buscar_embodiment_dir()
        sim_idx = yaml.safe_load((emb / "43dof_joint_space.yaml").read_text())["joints"]
        grupos = yaml.safe_load((emb / "gr00t_43dof_joint_space.yaml").read_text())["joints"]
        policy_names = [n for g in grupos.values() for n in g]
        assert sorted(policy_names) == sorted(sim_idx.keys()), "los dos YAML no declaran los mismos nombres"
        perm = np.array([sim_idx[n] for n in policy_names])          # politica[j] = sim[perm[j]]
        assert len(set(perm.tolist())) == N_JOINTS, "la permutacion no es biyectiva"

        n = acciones_politica.shape[0]
        juntas_sim = np.empty((n, N_JOINTS), dtype=np.float32)
        juntas_sim[:, perm] = acciones_politica                      # invertimos la permutacion

        # La altura de pelvis NO se rellena con cero: un cero pide pelvis a 0 m y el robot se sienta
        # en el suelo. El valor real de la sesion sale de meta/stats.json.
        stats = json.loads((root / "meta" / "stats.json").read_text())
        base_h = float(stats["teleop.base_height_command"]["mean"][0])
        nav = np.asarray(stats["teleop.navigate_command"]["max"], dtype=np.float32)
        assert np.allclose(nav, 0.0), f"navigate_command no es cero en el dataset: {nav}"

        self.acciones = np.zeros((n, ACTION_DIM), dtype=np.float32)
        self.acciones[:, :N_JOINTS] = juntas_sim
        self.acciones[:, IDX_NAV] = 0.0
        self.acciones[:, IDX_BASE_H] = base_h
        self.acciones[:, IDX_TORSO] = 0.0

        self.horizon = config.action_horizon
        self.cursor = 0
        self.dump_obs_npy = config.dump_obs_npy
        self._dumped = False
        print(
            f"[replay] episodio {k} <- {parquet.name}: {n} pasos, "
            f"accion {self.acciones.shape}, base_height={base_h:.4f}"
        )

    @staticmethod
    def _buscar_embodiment_dir() -> pathlib.Path:
        import isaaclab_arena_gr00t

        p = pathlib.Path(isaaclab_arena_gr00t.__file__).parent / "embodiments" / "g1"
        assert p.exists(), f"no encuentro los YAML de juntas en {p}"
        return p

    # ---------------------------------------------------------------- protocolo

    def _build_protocol(self) -> ChunkingActionProtocol:
        proto = ChunkingActionProtocol(
            action_dim=ACTION_DIM,
            observation_keys=["camera_obs.robot_head_cam_rgb", "policy.robot_joint_pos"],
            action_chunk_length=self.horizon,
            action_horizon=self.horizon,
        )
        print(f"[replay] protocolo = {proto.mode.value}, action_dim={ACTION_DIM}, horizonte={self.horizon}")
        return proto

    def set_task_description(self, task_description: str | None) -> dict[str, Any]:
        self._task_description = task_description
        return {"status": "ok"}

    def get_action(
        self, observation: dict[str, Any], options: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        anidada = self.unpack_observation(observation)
        num_envs = int(np.asarray(anidada["policy"]["robot_joint_pos"]).shape[0])

        # El replay ignora la observacion, pero *recibe* exactamente la que vera la politica.
        # Guardar el primer fotograma es la unica forma barata de comprobar que la camara de
        # evaluacion (tiled, embodiment de juntas) coincide con la de grabacion (no tiled, pink).
        if self.dump_obs_npy and not self._dumped:
            rgb = np.asarray(anidada["camera_obs"]["robot_head_cam_rgb"])
            np.save(self.dump_obs_npy, rgb[0])
            print(f"[replay] fotograma de evaluacion guardado en {self.dump_obs_npy}: "
                  f"shape={rgb.shape} dtype={rgb.dtype} media={rgb[0].mean():.2f}")
            self._dumped = True

        i0 = self.cursor
        i1 = min(i0 + self.horizon, self.acciones.shape[0])
        trozo = self.acciones[i0:i1]
        if trozo.shape[0] < self.horizon:  # al final, repetir la ultima pose (quieto, no a cero)
            relleno = np.repeat(self.acciones[-1:], self.horizon - trozo.shape[0], axis=0)
            trozo = np.concatenate([trozo, relleno], axis=0) if trozo.size else relleno
        self.cursor = i1

        chunk = np.broadcast_to(trozo[None], (num_envs, self.horizon, ACTION_DIM)).astype(np.float32).copy()
        return {"action": chunk}, {"replay_cursor": int(self.cursor)}

    def reset(self, env_ids: list[int] | None = None, reset_options: dict[str, Any] | None = None) -> dict[str, Any]:
        self.cursor = 0
        return {"status": "reset_success"}

    # ------------------------------------------------------------------- CLI

    @staticmethod
    def add_args_to_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
        g = parser.add_argument_group("Arena replay server", "Reproduce acciones grabadas.")
        g.add_argument("--dataset_path", type=str, required=True, help="raiz del dataset LeRobot")
        g.add_argument("--episode_index", type=int, default=0)
        g.add_argument("--action_horizon", type=int, default=40)
        g.add_argument("--dump_obs_npy", type=str, default=None,
                       help="guarda el primer fotograma recibido: cierra la duda de la deriva visual")
        return parser

    @staticmethod
    def from_args(args: argparse.Namespace) -> "ArenaReplayServerSidePolicy":
        return ArenaReplayServerSidePolicy(ArenaReplayArgs.from_cli_args(args))
