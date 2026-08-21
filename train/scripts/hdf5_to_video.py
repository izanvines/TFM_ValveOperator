# Saca un mp4 de la CAMARA DEL ROBOT directamente del HDF5, sin arrancar Isaac Sim.
#
# Por que no reutilizar `sim/scripts/record_robotcam_video.py`: aquel construye el entorno y
# renderiza de nuevo, o sea que ensena lo que la simulacion *produciria*. Esto ensena lo que el
# fichero *contiene*, que es lo que va a ver la politica. Cuando lo que quieres es comprobar un
# dataset ya escrito, la diferencia importa: un fallo en la escritura del HDF5 seria invisible
# con el otro metodo.
#
#   python3 hdf5_to_video.py <fichero.hdf5> --demos demo_0 demo_5 --outdir videos/
#   python3 hdf5_to_video.py <fichero.hdf5> --n 3          # las 3 primeras
import argparse
import os
import subprocess

import h5py
import numpy as np

p = argparse.ArgumentParser()
p.add_argument("hdf5")
p.add_argument("--demos", nargs="+", default=[])
p.add_argument("--n", type=int, default=0, help="las N primeras demos si no se dan nombres")
p.add_argument("--outdir", default="videos")
p.add_argument("--fps", type=int, default=50)
p.add_argument("--clave", default="camera_obs/robot_head_cam_rgb")
a = p.parse_args()

os.makedirs(a.outdir, exist_ok=True)
f = h5py.File(a.hdf5, "r")
d = f["data"]
nombres = a.demos or sorted(d, key=lambda s: int(s.split("_")[1]))[: (a.n or 1)]

base = os.path.splitext(os.path.basename(a.hdf5))[0]
for nombre in nombres:
    im = d[nombre][a.clave]
    n, alto, ancho, _ = im.shape
    salida = os.path.join(a.outdir, f"{base}_{nombre}.mp4")
    # Se escribe por trozos: 500 frames de 480x640x3 son 440 MB, y un episodio entero en RAM
    # no aporta nada.
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{ancho}x{alto}", "-r", str(a.fps),
        "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
        salida,
    ]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    medias = []
    for i in range(0, n, 64):
        trozo = np.asarray(im[i : i + 64], dtype=np.uint8)
        medias.append(trozo.mean())
        pr.stdin.write(trozo.tobytes())
    pr.stdin.close()
    if pr.wait() != 0:
        raise SystemExit(f"ffmpeg fallo en {nombre}")
    mb = os.path.getsize(salida) / 1e6
    print(f"{salida}  {n} frames  {n / a.fps:.1f} s  media {np.mean(medias):.1f}  {mb:.1f} MB")
