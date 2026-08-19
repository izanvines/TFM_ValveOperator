#!/usr/bin/env python3
"""Compara los pesos de un checkpoint contra el modelo del que se partio.

**Por que hace falta.** `gr00t/experiment/experiment.py` llama a
``trainer.train(resume_from_checkpoint=True)`` sin condiciones, y `Gr00tTrainer.train` lo resuelve
con `get_last_checkpoint(output_dir)`. Si en el directorio de salida queda un checkpoint viejo cuyo
`global_step` ya sea `max_steps`, HuggingFace Trainer ejecuta **cero pasos** y `save_model()`
guarda los pesos de antes. El resultado es un checkpoint de aspecto impecable -- con su
`config.json`, su `trainer_state.json` y su curva de perdida -- que nunca vio tus datos.

Comparar los tensores es la unica comprobacion que no se puede enganar. Se espera:

  * backbone (Cosmos-Reason2 / vision-language): `max|delta| == 0`. Va congelado
    (`tune_llm=False`, `tune_visual=False`).
  * proyector y cabeza de difusion: `max|delta|` claramente distinto de cero. Son lo que se entrena.

Si el grupo entrenable tambien sale a cero, no ha pasado nada, por muy bonito que sea el log.

    ~/TFM/isaac-gr00t-standalone/.venv/bin/python compare_checkpoint_weights.py \
        --base  ~/models/isaaclab_arena/static_apple_tutorial/gn1x_tuned_static_apple \
        --tuned ~/models/isaaclab_arena/g1_valve/gr00t_n17_valve_dryrun/checkpoint-1000
"""
import argparse
import json
import pathlib
import sys

import numpy as np
from safetensors import safe_open

# Clasificacion por prefijo del nombre del tensor. Lo que no encaje va a "otros".
CONGELADOS = ("backbone", "model.backbone", "vlm", "language_model", "vision")
ENTRENABLES = ("action_head", "state_encoder", "projector", "diffusion", "model.action_head")


def cargar_indice(root: pathlib.Path) -> dict[str, pathlib.Path]:
    """nombre de tensor -> fichero safetensors que lo contiene."""
    idx = root / "model.safetensors.index.json"
    if idx.exists():
        mapa = json.loads(idx.read_text())["weight_map"]
        return {k: root / v for k, v in mapa.items()}
    unico = root / "model.safetensors"
    if unico.exists():
        with safe_open(unico, framework="np") as f:
            return {k: unico for k in f.keys()}
    raise FileNotFoundError(f"ni index.json ni model.safetensors en {root}")


def grupo(nombre: str) -> str:
    n = nombre.lower()
    if any(p in n for p in ENTRENABLES):
        return "entrenable"
    if any(p in n for p in CONGELADOS):
        return "congelado"
    return "otros"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="checkpoint de partida")
    ap.add_argument("--tuned", required=True, help="checkpoint resultante")
    ap.add_argument("--max-tensors", type=int, default=0, help="0 = todos")
    args = ap.parse_args()

    base_root, tuned_root = pathlib.Path(args.base), pathlib.Path(args.tuned)
    base_idx, tuned_idx = cargar_indice(base_root), cargar_indice(tuned_root)

    comunes = sorted(set(base_idx) & set(tuned_idx))
    solo_base = sorted(set(base_idx) - set(tuned_idx))
    solo_tuned = sorted(set(tuned_idx) - set(base_idx))
    print(f"tensores: {len(comunes)} comunes, {len(solo_base)} solo en base, {len(solo_tuned)} solo en tuned")
    for n in solo_tuned[:5]:
        print(f"  nuevo en tuned: {n}")
    if args.max_tensors:
        comunes = comunes[: args.max_tensors]

    cache: dict[pathlib.Path, object] = {}

    def leer(fichero: pathlib.Path, nombre: str):
        if fichero not in cache:
            cache[fichero] = safe_open(fichero, framework="np")
        return cache[fichero].get_tensor(nombre)

    resumen: dict[str, list[float]] = {"congelado": [], "entrenable": [], "otros": []}
    peores: dict[str, tuple[float, str]] = {k: (0.0, "") for k in resumen}

    for n in comunes:
        try:
            a = leer(base_idx[n], n).astype(np.float32)
            b = leer(tuned_idx[n], n).astype(np.float32)
        except Exception as e:  # dtype exotico, tensor ausente
            print(f"  (saltado {n}: {type(e).__name__})")
            continue
        if a.shape != b.shape:
            print(f"  FORMA DISTINTA {n}: {a.shape} vs {b.shape}")
            continue
        d = float(np.abs(a - b).max())
        g = grupo(n)
        resumen[g].append(d)
        if d > peores[g][0]:
            peores[g] = (d, n)

    print()
    print(f"{'grupo':12s} {'tensores':>9s} {'max|delta|':>12s} {'media max|d|':>13s} {'% con cambio':>13s}")
    for g, ds in resumen.items():
        if not ds:
            continue
        arr = np.array(ds)
        pct = 100.0 * float((arr > 0).mean())
        print(f"{g:12s} {len(ds):9d} {arr.max():12.3e} {arr.mean():13.3e} {pct:12.1f}%")
        print(f"             peor: {peores[g][1]}")

    print()
    ent = np.array(resumen["entrenable"]) if resumen["entrenable"] else np.array([0.0])
    con = np.array(resumen["congelado"]) if resumen["congelado"] else np.array([0.0])
    if ent.max() == 0.0:
        print("VEREDICTO: los pesos entrenables NO han cambiado. El entrenamiento no hizo nada.")
        print("           Mira si el log dice 'Resuming from checkpoint' y usa un --output-dir nuevo.")
        return 1
    print(f"VEREDICTO: entrenables cambian (max {ent.max():.3e}), congelados max {con.max():.3e}. Ha entrenado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
