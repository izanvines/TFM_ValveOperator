#!/usr/bin/env python3
"""Corrige los dos restos de plantilla que deja `convert_hdf5_to_lerobot.py` en `meta/info.json`.

El conversor calcula ``total_chunks = len(trajectory_ids) // chunks_size``, que con 25 episodios y
``chunks_size: 1000`` da **0** aunque exista `data/chunk-000/`. Y copia ``splits`` tal cual de la
plantilla `isaaclab_arena_gr00t/embodiments/g1/info.json`, donde vale ``{"train": "0:100"}``.

Ninguno de los dos se lee en la ruta de carga -- GR00T usa `chunks_size` y LeRobot v2.1 tambien --
asi que esto es higiene, no una correccion funcional. Se arregla porque el `info.json` acaba en la
memoria del TFM y un dataset que se contradice a si mismo no es citable.

Idempotente: se puede lanzar las veces que haga falta.
"""
import argparse
import json
import math
import pathlib
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset_root", help="directorio que contiene meta/, data/ y videos/")
    ap.add_argument("--dry-run", action="store_true", help="ensena los cambios sin escribir")
    args = ap.parse_args()

    root = pathlib.Path(args.dataset_root)
    info_path = root / "meta" / "info.json"
    if not info_path.exists():
        print(f"ERROR: no existe {info_path}", file=sys.stderr)
        return 1

    info = json.loads(info_path.read_text())
    total_episodes = info["total_episodes"]
    chunks_size = info["chunks_size"]

    cambios = {}
    esperado_chunks = math.ceil(total_episodes / chunks_size)
    if info.get("total_chunks") != esperado_chunks:
        cambios["total_chunks"] = (info.get("total_chunks"), esperado_chunks)
        info["total_chunks"] = esperado_chunks

    esperado_splits = {"train": f"0:{total_episodes}"}
    if info.get("splits") != esperado_splits:
        cambios["splits"] = (info.get("splits"), esperado_splits)
        info["splits"] = esperado_splits

    # Coherencia: la suma de longitudes de episodes.jsonl tiene que dar total_frames.
    episodes_path = root / "meta" / "episodes.jsonl"
    suma = sum(json.loads(l)["length"] for l in episodes_path.read_text().splitlines() if l.strip())
    n_eps = sum(1 for l in episodes_path.read_text().splitlines() if l.strip())
    print(f"episodios en episodes.jsonl : {n_eps}  (info.json dice {total_episodes})")
    print(f"suma de longitudes          : {suma}  (info.json dice {info['total_frames']})")
    if n_eps != total_episodes or suma != info["total_frames"]:
        print("AVISO: info.json no cuadra con episodes.jsonl.", file=sys.stderr)
        print("       El conversor cuenta total_episodes = len(claves del HDF5) aunque alguna demo", file=sys.stderr)
        print("       reviente y se salte -- comprueba el log de conversion.", file=sys.stderr)

    if not cambios:
        print("Nada que corregir.")
        return 0

    for k, (antes, despues) in cambios.items():
        print(f"{k}: {antes!r} -> {despues!r}")

    if args.dry_run:
        print("(--dry-run: no se ha escrito nada)")
        return 0

    info_path.write_text(json.dumps(info, indent=4) + "\n")
    print(f"Escrito {info_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
