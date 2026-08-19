#!/usr/bin/env python3
"""Audita un dataset GR00T-LeRobot contra el HDF5 del que salio.

Corre DENTRO del contenedor (`/isaac-sim/python.sh`), que es donde estan a la vez h5py, pyarrow y
ffprobe. El venv de GR00T no trae h5py y no merece la pena tocarlo.

    docker exec isaaclab_arena-latest bash -c 'cd /workspaces/isaaclab_arena && \
      /isaac-sim/python.sh /eval/arena_extras/verify_lerobot_dataset.py \
        --dataset /datasets/isaaclab_arena/g1_valve/sesion_01/lerobot \
        --hdf5    /datasets/isaaclab_arena/g1_valve/sesion_01.hdf5'

Por que existe: `convert_hdf5_to_lerobot.py` envuelve cada demo en `try/except ... continue` pero
calcula `total_episodes = len(trajectory_ids)` pase lo que pase. Una demo que reviente se salta en
silencio y el `info.json` sigue afirmando que estan todas. Ademas itera `list(f["data"].keys())`,
que en h5py sale en orden ALFABETICO, asi que `episode_000002` no es `demo_2` sino `demo_10`. Las
dos cosas son invisibles salvo que alguien las mida.
"""
import argparse
import json
import pathlib
import subprocess
import sys

import h5py
import numpy as np
import pyarrow.parquet as pq
import yaml

FALLOS = []
AVISOS = []


def check(nombre, ok, detalle=""):
    estado = "PASS" if ok else "FALLO"
    if not ok:
        FALLOS.append(f"{nombre}: {detalle}")
    print(f"  [{estado}] {nombre}" + (f" -- {detalle}" if detalle else ""))
    return ok


def aviso(texto):
    AVISOS.append(texto)
    print(f"  [aviso] {texto}")


def joint_orders(arena_root):
    """Devuelve (nombres en orden politica GR00T, nombre -> indice en orden simulador)."""
    emb = pathlib.Path(arena_root) / "isaaclab_arena_gr00t/embodiments/g1"
    sim_idx = yaml.safe_load((emb / "43dof_joint_space.yaml").read_text())["joints"]
    grupos = yaml.safe_load((emb / "gr00t_43dof_joint_space.yaml").read_text())["joints"]
    policy_names = [n for g in grupos.values() for n in g]
    return policy_names, sim_idx


def nb_frames(mp4):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(mp4)],
        capture_output=True, text=True,
    )
    try:
        return int(out.stdout.strip().rstrip(","))
    except ValueError:
        return -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--hdf5", required=True)
    ap.add_argument("--arena-root", default="/workspaces/isaaclab_arena")
    ap.add_argument("--png-out", default=None, help="donde escribir el fotograma 0 del episodio 0")
    args = ap.parse_args()

    root = pathlib.Path(args.dataset)
    info = json.loads((root / "meta" / "info.json").read_text())
    episodes = [json.loads(l) for l in (root / "meta" / "episodes.jsonl").read_text().splitlines() if l.strip()]
    tasks = [json.loads(l) for l in (root / "meta" / "tasks.jsonl").read_text().splitlines() if l.strip()]
    fps = info["fps"]

    print(f"\n=== 1. info.json contra el sistema de ficheros ===")
    parquets = sorted((root / "data").glob("chunk-*/episode_*.parquet"))
    mp4s = sorted((root / "videos").glob("chunk-*/*/episode_*.mp4"))
    check("numero de parquets == total_episodes", len(parquets) == info["total_episodes"],
          f"{len(parquets)} vs {info['total_episodes']}")
    check("numero de mp4 == total_videos", len(mp4s) == info["total_videos"],
          f"{len(mp4s)} vs {info['total_videos']}")
    check("episodes.jsonl == total_episodes", len(episodes) == info["total_episodes"],
          f"{len(episodes)} vs {info['total_episodes']}")
    check("tasks.jsonl tiene 1 tarea", len(tasks) == 1, f"{len(tasks)}")
    print(f"  tarea: {tasks[0]['task']!r}")

    print(f"\n=== 2. Longitudes: parquet vs episodes.jsonl vs mp4 ===")
    total_filas = 0
    for ep in episodes:
        k = ep["episode_index"]
        p = root / "data" / f"chunk-{k // info['chunks_size']:03d}" / f"episode_{k:06d}.parquet"
        t = pq.read_table(p)
        v = nb_frames(root / "videos" / f"chunk-{k // info['chunks_size']:03d}" /
                      "observation.images.ego_view" / f"episode_{k:06d}.mp4")
        total_filas += t.num_rows
        ok = (t.num_rows == ep["length"] == v)
        if not ok:
            check(f"episodio {k:02d}", False, f"parquet={t.num_rows} jsonl={ep['length']} mp4={v}")
    check("todas las longitudes cuadran (parquet == jsonl == mp4)", not FALLOS, "ver arriba")
    check("suma de filas == total_frames", total_filas == info["total_frames"],
          f"{total_filas} vs {info['total_frames']}")

    print(f"\n=== 3. Columnas de indice y tiempo ===")
    idx_global, malos_ts, malos_fi, malos_ei = [], [], [], []
    for ep in episodes:
        k = ep["episode_index"]
        p = root / "data" / f"chunk-{k // info['chunks_size']:03d}" / f"episode_{k:06d}.parquet"
        t = pq.read_table(p)
        idx_global.append(np.asarray(t.column("index").to_pylist()))
        fi = np.asarray(t.column("frame_index").to_pylist())
        ei = np.asarray(t.column("episode_index").to_pylist())
        ts = np.asarray(t.column("timestamp").to_pylist())
        if not np.array_equal(fi, np.arange(len(fi))):
            malos_fi.append(k)
        if not np.all(ei == k):
            malos_ei.append(k)
        if not np.allclose(ts, np.arange(len(ts)) / fps, atol=1e-9):
            malos_ts.append(k)
    idx_global = np.concatenate(idx_global)
    check("index global contiguo 0..N-1", np.array_equal(idx_global, np.arange(len(idx_global))),
          f"min={idx_global.min()} max={idx_global.max()} n={len(idx_global)}")
    check("frame_index reinicia en 0 por episodio", not malos_fi, f"episodios {malos_fi}")
    check("episode_index constante por fichero", not malos_ei, f"episodios {malos_ei}")
    check(f"timestamp == arange(N)/{fps}", not malos_ts, f"episodios {malos_ts}")

    print(f"\n=== 4. Procedencia: cada episodio contra su demo del HDF5 ===")
    policy_names, sim_idx = joint_orders(args.arena_root)
    check("gr00t_43dof y 43dof declaran los mismos 43 nombres",
          sorted(policy_names) == sorted(sim_idx.keys()) and len(policy_names) == 43,
          f"{len(policy_names)} nombres")
    perm = np.array([sim_idx[n] for n in policy_names])  # policy[j] = sim[perm[j]]

    with h5py.File(args.hdf5, "r") as f:
        claves = list(f["data"].keys())          # el conversor usa este orden tal cual
        print(f"  orden de iteracion del conversor (h5py, ALFABETICO):")
        mapeo = {i: c for i, c in enumerate(claves)}
        for i in [0, 1, 2, 3, 12, 18, 24]:
            if i < len(claves):
                print(f"     episode_{i:06d}  <-  {mapeo[i]}")
        alfabetico_no_numerico = any(int(mapeo[i].split("_")[1]) != i for i in mapeo)
        if alfabetico_no_numerico:
            aviso("el indice de episodio NO coincide con el numero de demo (orden alfabetico de h5py)")

        desajustes = []
        rng = np.random.default_rng(0)
        for ep in episodes:
            k = ep["episode_index"]
            p = root / "data" / f"chunk-{k // info['chunks_size']:03d}" / f"episode_{k:06d}.parquet"
            a_lerobot = np.array(pq.read_table(p).column("action").to_pylist(), dtype=np.float32)
            a_hdf5 = f["data"][mapeo[k]]["processed_actions"][:-1]   # el conversor tira el ultimo
            if a_hdf5.shape[0] != a_lerobot.shape[0]:
                desajustes.append((k, "longitud", a_hdf5.shape[0], a_lerobot.shape[0]))
                continue
            for t in rng.integers(0, a_lerobot.shape[0], size=min(5, a_lerobot.shape[0])):
                if not np.allclose(a_lerobot[t], a_hdf5[t][perm], atol=1e-6):
                    desajustes.append((k, f"fila {t}", None, None))
                    break
        check("action[k] == permutacion(processed_actions de su demo)", not desajustes,
              f"{desajustes[:3]}")

        print(f"\n=== 5. Recorrido de la valvula por demo ===")
        grados = []
        for i, c in enumerate(claves):
            jp = f["data"][c]["states"]["articulation"]["valve"]["joint_position"][:]
            grados.append((c, np.degrees(jp.max()), f["data"][c].attrs.get("success")))
        gr = np.array([g for _, g, _ in grados])
        print(f"  giro maximo: min={gr.min():.1f}  media={gr.mean():.1f}  max={gr.max():.1f} grados")
        print(f"  exito declarado en el HDF5: {sum(1 for _,_,s in grados if s)}/{len(grados)}")
        margen = gr.min() - 180.0
        print(f"  umbral de exito = 180 grados (openness 0.5). Margen de la peor demo: {margen:+.1f} grados")
        if margen < 10:
            aviso(f"el margen sobre el umbral es de solo {margen:+.1f} grados en la peor demo -- "
                  "una politica que se quede algo corta puntuara success_rate=0 con la valvula girando")

    print(f"\n=== 6. Estadisticas por dimension ===")
    A, S = [], []
    for ep in episodes:
        k = ep["episode_index"]
        p = root / "data" / f"chunk-{k // info['chunks_size']:03d}" / f"episode_{k:06d}.parquet"
        t = pq.read_table(p)
        A.append(np.array(t.column("action").to_pylist(), dtype=np.float32))
        S.append(np.array(t.column("observation.state").to_pylist(), dtype=np.float32))
    A, S = np.concatenate(A), np.concatenate(S)
    print(f"  action {A.shape}   observation.state {S.shape}")
    sd = A.std(0)
    muertas = np.where(sd < 1e-6)[0]
    print(f"  dimensiones de ACTION con std == 0: {len(muertas)} de 43")
    for i in muertas:
        print(f"     [{i:2d}] {policy_names[i]}")
    casi = np.where((sd >= 1e-6) & (sd < 1e-3))[0]
    if len(casi):
        print(f"  casi constantes (std < 1e-3): {len(casi)}")
        for i in casi:
            print(f"     [{i:2d}] {policy_names[i]}  std={sd[i]:.2e}")
    sds = S.std(0)
    print(f"  dimensiones de STATE con std == 0: {int((sds < 1e-6).sum())} de 43")
    if len(muertas):
        aviso(f"{len(muertas)} dimensiones de accion no llevan senal. GR00T las normaliza con "
              "range=max(max-min,1e-8) y recorte a [-1,1]: degenerado pero sin NaN")

    if args.png_out:
        k0 = episodes[0]["episode_index"]
        mp4 = root / "videos" / f"chunk-{k0 // info['chunks_size']:03d}" / \
            "observation.images.ego_view" / f"episode_{k0:06d}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4),
                        "-vframes", "1", args.png_out], check=False)
        print(f"\n  fotograma 0 del episodio {k0} escrito en {args.png_out}")

    print("\n" + "=" * 70)
    print(f"FALLOS: {len(FALLOS)}   AVISOS: {len(AVISOS)}")
    for x in FALLOS:
        print(f"  FALLO  {x}")
    for x in AVISOS:
        print(f"  aviso  {x}")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main())
