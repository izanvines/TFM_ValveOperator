#!/usr/bin/env python3
"""Construye una vista del dataset GR00T-LeRobot que LeRobot 0.3.3 pueda cargar tal cual.

**El problema.** `convert_hdf5_to_lerobot.py` escribe una estructura LeRobot v2.1 valida pero **no
calcula ninguna estadistica**, y a v2.1 LeRobot lee `meta/episodes_stats.jsonl` -- no `stats.json`,
que solo se consulta por debajo de v2.1 (`LeRobotDatasetMetadata.load_metadata`). Sin ese fichero
el dataset no se instancia, y aunque se instanciase las capas `Normalize`/`Unnormalize` de ACT se
construyen a partir de `dataset.meta.stats`.

Ademas el `info.json` declara columnas que a ACT le sobran: `dataset_to_policy_features` mapea
*cualquier* clave que empiece por `action` a `FeatureType.ACTION`, asi que dejar `action.eef_pose`
le daria a ACT dos acciones distintas.

**La solucion.** Una vista hermana, no una copia: `data/` y `videos/` van como enlaces simbolicos
(cero bytes duplicados, 15 MB de dataset se quedan en 15 MB) y solo `meta/` se reescribe. Asi GR00T
sigue leyendo `lerobot/` con su `modality.json` y su `stats.json`, y ACT lee `lerobot_act/`.

Las estadisticas se calculan con las funciones **de LeRobot**, no reimplementadas: hay dos reglas
que se incumplen a la primera y que `_assert_type_and_shape` solo denuncia a posteriori --
`count` con forma exactamente `(1,)`, y toda clave que contenga la subcadena `image` con
min/max/mean/std de forma exactamente `(3,1,1)`.

    ~/venvs/lerobot-act/bin/python make_lerobot_act_view.py \
        --src  ~/datasets/isaaclab_arena/g1_valve/sesion_01/lerobot \
        --dest ~/datasets/isaaclab_arena/g1_valve/sesion_01/lerobot_act
"""
import argparse
import json
import math
import pathlib
import shutil
import sys

import numpy as np
import pyarrow.parquet as pq

from lerobot.datasets.compute_stats import (
    aggregate_stats,
    auto_downsample_height_width,
    get_feature_stats,
    sample_indices,
)
from lerobot.datasets.utils import serialize_dict, write_episode_stats, write_info

# Columnas que se quitan del info.json para ACT. Las tres primeras confundirian el mapeo de
# caracteristicas; `teleop.*` y `next.*` los ignora `dataset_to_policy_features`, pero se quitan
# igualmente para que el info.json describa lo que ACT consume de verdad.
SOBRAN = [
    "observation.eef_pose",
    "action.eef_pose",
    "observation.img_state_delta",
    "teleop.base_height_command",
    "teleop.navigate_command",
    "teleop.torso_orientation_rpy_command",
    "next.reward",
    "next.done",
    "annotation.human.task_description",
]


def decodificar_muestras(mp4: pathlib.Path, n_frames: int) -> np.ndarray:
    """Muestrea fotogramas del video como LeRobot muestrea imagenes: (N, C, H, W) uint8."""
    from torchcodec.decoders import VideoDecoder

    dec = VideoDecoder(str(mp4))
    idx = sample_indices(n_frames)
    salida = None
    for i, j in enumerate(idx):
        img = dec[j].numpy()                       # (C, H, W) uint8
        img = auto_downsample_height_width(img)
        if salida is None:
            salida = np.empty((len(idx), *img.shape), dtype=np.uint8)
        salida[i] = img
    return salida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dest", required=True)
    ap.add_argument("--video-key", default="observation.images.ego_view")
    args = ap.parse_args()

    src = pathlib.Path(args.src).expanduser().resolve()
    dest = pathlib.Path(args.dest).expanduser()
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "meta").mkdir(parents=True)

    # data/ y videos/ por enlace simbolico: la vista no duplica ni un byte.
    for sub in ("data", "videos"):
        (dest / sub).symlink_to(src / sub, target_is_directory=True)
    print(f"enlazados {dest}/data y {dest}/videos -> {src}")

    info = json.loads((src / "meta" / "info.json").read_text())
    episodes = [json.loads(l) for l in (src / "meta" / "episodes.jsonl").read_text().splitlines() if l.strip()]

    # --- info.json podado ---
    quitadas = [k for k in SOBRAN if k in info["features"]]
    for k in quitadas:
        del info["features"][k]
    info["total_chunks"] = math.ceil(info["total_episodes"] / info["chunks_size"])
    info["splits"] = {"train": f"0:{info['total_episodes']}"}
    write_info(info, dest)
    print(f"info.json: quitadas {len(quitadas)} columnas -> {sorted(info['features'])}")

    shutil.copy(src / "meta" / "tasks.jsonl", dest / "meta" / "tasks.jsonl")
    shutil.copy(src / "meta" / "episodes.jsonl", dest / "meta" / "episodes.jsonl")

    # --- estadisticas por episodio ---
    features = info["features"]
    todas = []
    for ep in episodes:
        k = ep["episode_index"]
        chunk = k // info["chunks_size"]
        parquet = src / "data" / f"chunk-{chunk:03d}" / f"episode_{k:06d}.parquet"
        mp4 = src / "videos" / f"chunk-{chunk:03d}" / args.video_key / f"episode_{k:06d}.mp4"
        tabla = pq.read_table(parquet)

        stats = {}
        for clave, spec in features.items():
            if spec["dtype"] in ("image", "video"):
                arr = decodificar_muestras(mp4, ep["length"])
                s = get_feature_stats(arr, axis=(0, 2, 3), keepdims=True)
                stats[clave] = {
                    kk: vv if kk == "count" else np.squeeze(vv / 255.0, axis=0) for kk, vv in s.items()
                }
                continue
            col = tabla.column(clave).to_pylist()
            arr = np.asarray(col, dtype=np.float64 if "float" in spec["dtype"] else np.int64)
            if arr.ndim == 1:                       # escalar por fila -> keepdims para forma (1,)
                stats[clave] = get_feature_stats(arr, axis=0, keepdims=True)
            else:
                stats[clave] = get_feature_stats(arr, axis=0, keepdims=False)

        write_episode_stats(k, stats, dest)  # write_episode_stats ya serializa por dentro
        todas.append(stats)
        print(f"  episodio {k:02d}: {ep['length']:4d} filas, {stats[args.video_key]['count'][0]:3d} "
              f"fotogramas muestreados")

    # `stats.json` no se lee a v2.1, pero se escribe para que el directorio se describa a si mismo
    # y para que una version de LeRobot que baje de version siga funcionando.
    agregado = aggregate_stats(todas)
    (dest / "meta" / "stats.json").write_text(json.dumps(serialize_dict(agregado), indent=4) + "\n")
    print(f"\nescrito {dest}/meta/  ({len(todas)} episodios)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
