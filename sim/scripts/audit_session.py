# Resumen por demo de una sesion de `record_demos.py`. h5py puro, no arranca Isaac Sim.
# Pensado para revisar una tanda entera de un vistazo antes de dar por buena la sesion.
import sys

import h5py
import numpy as np

ruta = sys.argv[1]
f = h5py.File(ruta, "r")
data = f["data"]
demos = sorted(data.keys(), key=lambda s: int(s.split("_")[-1]))

print(f"FICHERO : {ruta}")
print(f"DEMOS   : {len(demos)}")
print()
cab = f"{'demo':>6} {'pasos':>6} {'seg':>6} {'exito':>6} {'grados':>7} {'apert':>6} {'agarre%':>8} {'img_neg':>8} {'cam_med':>8}"
print(cab)
print("-" * len(cab))

tot_pasos, exitos, grados, agarres, negros_tot = [], 0, [], [], 0
for n in demos:
    d = data[n]
    a = d["actions"][...]
    v = d["states/articulation/valve/joint_position"][...]
    cam = d["camera_obs/robot_head_cam_rgb"]
    ok = bool(d.attrs.get("success", False))
    deg = float(np.degrees(v.max()))
    apert = deg / 360.0
    mano = (np.abs(a[:, 0]) > 0.05) | (np.abs(a[:, 1]) > 0.05)
    pct = 100.0 * mano.sum() / len(a)
    # muestreo de fotogramas para no cargar 300x480x640x3 por demo
    idx = np.linspace(0, cam.shape[0] - 1, min(30, cam.shape[0])).astype(int)
    muestra = cam[idx]
    negros = int((muestra.reshape(len(idx), -1).max(axis=1) == 0).sum())
    media = float(muestra.mean())

    print(f"{n.split('_')[-1]:>6} {len(a):>6} {len(a)*0.02:>6.1f} {str(ok):>6} "
          f"{deg:>7.1f} {apert:>6.3f} {pct:>7.0f}% {negros:>8} {media:>8.1f}")
    tot_pasos.append(len(a)); exitos += ok; grados.append(deg); agarres.append(pct); negros_tot += negros

print("-" * len(cab))
p, g, ag = np.array(tot_pasos), np.array(grados), np.array(agarres)
print(f"\nRESUMEN")
print(f"  demos                : {len(demos)}   exitos: {exitos}/{len(demos)}")
print(f"  pasos    : media {p.mean():6.1f}  min {p.min():4d}  max {p.max():4d}  (= {p.sum()*0.02:.0f} s de datos)")
print(f"  giro     : media {g.mean():6.1f} deg  min {g.min():.1f}  max {g.max():.1f}")
print(f"  agarre   : media {ag.mean():6.1f}%  min {ag.min():.0f}%  max {ag.max():.0f}%")
print(f"  fotogramas negros en el muestreo: {negros_tot}")

flojas = [demos[i] for i in range(len(demos)) if grados[i] < 185]
if flojas:
    print(f"\n  AVISO: demos que apenas pasan el umbral (<185 deg): {flojas}")
sin_agarre = [demos[i] for i in range(len(demos)) if agarres[i] < 10]
if sin_agarre:
    print(f"  AVISO: demos casi sin agarre (<10% de pasos): {sin_agarre}")

# dims constantes en TODA la sesion
todas = np.concatenate([data[n]["actions"][...] for n in demos])
const = [i for i in range(todas.shape[1]) if todas[:, i].std() == 0]
print(f"\n  dims constantes en toda la sesion: {const}")
print(f"  (16,17,18 locomocion y 20,21,22 torso son intencionadas)")
f.close()
