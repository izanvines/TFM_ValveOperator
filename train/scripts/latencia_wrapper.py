"""Envoltorios que cronometran la inferencia de las politicas servidas por ZMQ.

Mide **latencia en lazo**: el tiempo que tarda el servidor en devolver un chunk de acciones con
las observaciones reales del simulador, no con un tensor sintetico.

POR QUE IMPORTA. El cliente (`ActionChunkingClientSidePolicy`) pide un chunk nuevo cada 40 pasos,
y a 50 Hz eso son **0,8 s de tiempo de robot**. Si la inferencia no cabe en ese presupuesto el
robot se queda esperando, y en un despliegue real eso pesa tanto como la tasa de exito. Es el eje
donde 3,14 B de parametros contra 51,7 M tiene que notarse.

POR QUE UN ENVOLTORIO Y NO UN PARCHE. `policy_runner.py --policy_type` acepta cualquier ruta de
importacion con puntos, asi que se puede servir una subclase sin tocar una sola linea de Arena --
que esta lleno de modificaciones locales sin commitear y donde cada cambio es una deuda.

    # servidor de GR00T (venv isaac-gr00t-standalone)
    LATENCIA_OUT=/eval/logs/latencia_gr00t.jsonl python -m \
      isaaclab_arena.remote_policy.remote_policy_server_runner \
      --policy_type latencia_wrapper.Gr00tCronometrado ...

DOS TRAMPAS AL CRONOMETRAR EN GPU:

1. `torch.cuda.synchronize()` antes y despues. Sin el se mide el tiempo de *encolar* los kernels,
   no el de ejecutarlos, y sale una latencia absurdamente baja (unidades de ms para un modelo de
   3 B, que es imposible).
2. La primera llamada se descarta. Incluye la seleccion de algoritmos de cuDNN y la reserva del
   pool de memoria; mezclarla con las demas envenena la mediana.

Las clases se definen segun que base se pueda importar: cada servidor vive en un venv distinto y
solo uno de los dos imports funciona en cada uno. Eso es deliberado, no una importacion fallida.
"""
from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Any

import torch


def _cronometrado(base):
    """Devuelve una subclase de `base` que mide cada `get_action`."""

    class Cronometrado(base):  # type: ignore[misc, valid-type]
        def __init__(self, config) -> None:
            super().__init__(config)
            self._t: list[float] = []
            destino = os.environ.get("LATENCIA_OUT", "/tmp/latencia.jsonl")
            self._salida = pathlib.Path(destino)
            self._salida.parent.mkdir(parents=True, exist_ok=True)
            self._salida.write_text("")
            print(f"[latencia] midiendo {base.__name__} -> {self._salida}", flush=True)

        def get_action(self, observation: dict[str, Any], options: dict[str, Any] | None = None):
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            t0 = time.perf_counter()
            salida = super().get_action(observation, options)
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            ms = (time.perf_counter() - t0) * 1000.0

            self._t.append(ms)
            with self._salida.open("a") as fh:
                fh.write(json.dumps({"n": len(self._t), "ms": round(ms, 3)}) + "\n")
            # La primera llamada es el calentamiento y no entra en el resumen.
            utiles = self._t[1:]
            if utiles and len(self._t) % 25 == 0:
                orden = sorted(utiles)
                mediana = orden[len(orden) // 2]
                print(f"[latencia] n={len(utiles)} mediana={mediana:.1f} ms "
                      f"min={orden[0]:.1f} max={orden[-1]:.1f}", flush=True)
            return salida

        # `from_args` es un @staticmethod en las dos bases y devuelve la clase base a pelo, asi
        # que sin este override el runner instanciaria la base y no se mediria nada.
        @classmethod
        def from_args(cls, args):
            return cls(cls.config_class.from_cli_args(args))

    Cronometrado.__name__ = f"{base.__name__}Cronometrado"
    return Cronometrado


try:  # venv de GR00T
    from isaaclab_arena_gr00t.policy.gr00t_remote_policy import Gr00tRemoteServerSidePolicy

    Gr00tCronometrado = _cronometrado(Gr00tRemoteServerSidePolicy)
except Exception:  # pragma: no cover - depende del venv
    pass

try:  # venv de LeRobot/ACT
    from act_remote_policy import ActRemoteServerSidePolicy

    ActCronometrado = _cronometrado(ActRemoteServerSidePolicy)
except Exception:  # pragma: no cover - depende del venv
    pass
