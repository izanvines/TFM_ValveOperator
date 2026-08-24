#!/usr/bin/env python3
"""Extrae un subconjunto de N episodios de un dataset GR00T-LeRobot v2.1.

Para la curva de eficiencia de datos: entrenar con 25, 50 y 100 demos y ver si el VLA se
despega del metodo clasico cuando hay pocos datos. Las 100 ya estan convertidas, asi que los
puntos de 25 y 50 salen de aqui en vez de reconvertir desde el HDF5.

    ~/venvs/lerobot-act/bin/python subset_lerobot.py \
        --src   ~/datasets/isaaclab_arena/g1_valve/valve_100/lerobot \
        --dest  ~/datasets/isaaclab_arena/g1_valve/valve_25/lerobot \
        --n 25 --layouts ~/eval/logs/layouts_valve100.json --seed 0

POR QUE ESTRATIFICADO, y no "los primeros 25". El reparto de disposiciones por sesion es
11F/14C, 8F/17C, 16F/9C, 15F/10C: coger un prefijo mezclaria *menos datos* con *mas cenitales*,
y esta medido (Fisher p < 0.001) que la cenital es la dificil. La curva bajaria por el motivo
equivocado. Aqui se sortea la mitad de cada disposicion, asi que lo unico que cambia entre
puntos de la curva es la CANTIDAD.

POR QUE ANIDADOS. Se baraja una vez cada lista con la semilla y se toman prefijos, de modo que
los 25 son subconjunto de los 50 y estos de los 100. Cada punto de la curva *anade* datos en
vez de resortear, que es lo que hace que la curva se lea como "efecto de anadir demostraciones"
y no como ruido de muestreo.

LO QUE NO SE PUEDE ENLAZAR. El parquet lleva `episode_index` y el `index` global dentro de las
propias filas, asi que hay que reescribirlo renumerando: un enlace simbolico dejaria el
episodio 37 diciendo que es el 37 dentro de un dataset que solo tiene 25. Los mp4 si se
enlazan (son el 79 % del tamano y no llevan indices dentro).

NO se copia `stats.json`: las estadisticas de normalizacion se recalculan sobre el subconjunto
con `gr00t/data/stats.py`. Heredar las de las 100 seria filtrar informacion de datos que este
modelo no ha visto.
"""
import argparse
import json
import math
import os
import pathlib
import random
import shutil

import pandas as pd


def selecciona(layouts: list[str], n: int, semilla: int) -> list[int]:
    """Indices de episodio, estratificados por disposicion y anidados entre tamanos."""
    porclase: dict[str, list[int]] = {}
    for i, d in enumerate(layouts):
        porclase.setdefault(d, []).append(i)
    for clase in porclase:
        random.Random(semilla).shuffle(porclase[clase])

    clases = sorted(porclase)                      # ['C', 'F'] -> el impar cae en cenital
    cupo = {c: n // len(clases) for c in clases}
    for c in clases[: n % len(clases)]:
        cupo[c] += 1

    elegidos: list[int] = []
    for c in clases:
        if cupo[c] > len(porclase[c]):
            raise SystemExit(f"no hay {cupo[c]} episodios de disposicion {c}, solo {len(porclase[c])}")
        elegidos += porclase[c][: cupo[c]]
    return sorted(elegidos)                        # orden temporal en el dataset resultante


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dest", required=True)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--layouts", required=True, help="JSON con una lista de 'F'/'C' por episodio")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--video-key", default="observation.images.ego_view")
    a = ap.parse_args()

    src, dest = pathlib.Path(a.src), pathlib.Path(a.dest)
    layouts = json.loads(pathlib.Path(a.layouts).read_text())

    info = json.loads((src / "meta" / "info.json").read_text())
    episodios = [json.loads(l) for l in (src / "meta" / "episodes.jsonl").read_text().splitlines() if l.strip()]
    if len(layouts) != info["total_episodes"] or len(episodios) != info["total_episodes"]:
        raise SystemExit(f"descuadre: info={info['total_episodes']} layouts={len(layouts)} episodes.jsonl={len(episodios)}")

    elegidos = selecciona(layouts, a.n, a.seed)
    reparto = {c: sum(1 for i in elegidos if layouts[i] == c) for c in sorted(set(layouts))}
    print(f"elegidos {len(elegidos)} de {len(layouts)}  reparto={reparto}")
    print(f"indices: {elegidos}")

    if dest.exists():
        shutil.rmtree(dest)
    (dest / "meta").mkdir(parents=True)
    (dest / "data" / "chunk-000").mkdir(parents=True)
    (dest / "videos" / "chunk-000" / a.video_key).mkdir(parents=True)

    total_frames = 0
    nuevos_episodios = []
    for nuevo, viejo in enumerate(elegidos):
        # --- parquet: renumerar episode_index y el index global -----------------------------
        df = pd.read_parquet(src / "data" / "chunk-000" / f"episode_{viejo:06d}.parquet")
        df["episode_index"] = nuevo
        df["index"] = total_frames + df["frame_index"].to_numpy()
        df.to_parquet(dest / "data" / "chunk-000" / f"episode_{nuevo:06d}.parquet", index=False)

        # --- video: enlace simbolico, no lleva indices dentro --------------------------------
        # RELATIVO, no absoluto: el dataset se lee desde el host (entrenamiento) y desde dentro
        # del contenedor (verificador), donde el mismo arbol esta montado en /datasets. Un
        # enlace a /home/ivines/... apuntaria a la nada en el segundo caso.
        origen = (src / "videos" / "chunk-000" / a.video_key / f"episode_{viejo:06d}.mp4").resolve()
        enlace = dest / "videos" / "chunk-000" / a.video_key / f"episode_{nuevo:06d}.mp4"
        enlace.symlink_to(os.path.relpath(origen, start=enlace.parent))

        fila = dict(episodios[viejo])
        if fila["length"] != len(df):
            raise SystemExit(f"episodio {viejo}: episodes.jsonl dice {fila['length']} y el parquet tiene {len(df)}")
        fila["episode_index"] = nuevo
        nuevos_episodios.append(fila)
        total_frames += len(df)

    info["total_episodes"] = len(elegidos)
    info["total_frames"] = total_frames
    info["total_videos"] = len(elegidos)
    info["total_chunks"] = math.ceil(len(elegidos) / info["chunks_size"])
    info["splits"] = {"train": f"0:{len(elegidos)}"}
    (dest / "meta" / "info.json").write_text(json.dumps(info, indent=4))
    (dest / "meta" / "episodes.jsonl").write_text("".join(json.dumps(e) + "\n" for e in nuevos_episodios))

    # tasks.jsonl y modality.json se copian tal cual; stats.json NO (se recalcula por subconjunto).
    for nombre in ("tasks.jsonl", "modality.json", "relative_stats.json"):
        if (src / "meta" / nombre).exists():
            shutil.copy(src / "meta" / nombre, dest / "meta" / nombre)

    # Trazabilidad: de que episodios del original sale cada uno de estos.
    (dest / "meta" / "subset_provenance.json").write_text(json.dumps(
        {"src": str(src), "n": a.n, "seed": a.seed, "reparto": reparto,
         "origen_por_episodio": {str(n): v for n, v in enumerate(elegidos)}}, indent=2))

    print(f"escrito {dest}  ({len(elegidos)} episodios, {total_frames} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
