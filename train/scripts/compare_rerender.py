#!/usr/bin/env python3
"""Compara un HDF5 re-renderizado contra el original del que salio.

Corre dentro del contenedor (`/isaac-sim/python.sh`), que es donde esta h5py.

**Que se espera y que no.** El re-renderizado NO es una copia bit a bit del original, y no tiene por
que serlo: se reproducen las acciones crudas de 23 dims y Pink IK vuelve a resolver los objetivos de
junta a partir del estado actual del robot, asi que una desviacion minima al principio se propaga.
Lo que importa es otra cosa:

  1. que cada episodio tenga el MISMO numero de pasos que el original (si no, la reproduccion se
     cortó o se alargó);
  2. que la valvula siga cruzando el umbral de exito (180 grados);
  3. que las imagenes hayan cambiado (si no, el fondo no se esta renderizando);
  4. que el fichero sea internamente coherente -- y lo es por construccion, porque es una rodadura
     real grabada por los mismos recorders.

El punto 2 es el que puede morder: las demos originales llegan a 181-232 grados, o sea con hasta
menos de un grado de margen. Una desviacion de 10 grados en la reproduccion tumba las que iban
justas.
"""
import argparse
import sys

import h5py
import numpy as np

UMBRAL_GRADOS = 180.0


def grados(demo) -> float:
    return float(np.degrees(demo["states"]["articulation"]["valve"]["joint_position"][:].max()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="HDF5 original")
    ap.add_argument("--dst", required=True, help="HDF5 re-renderizado")
    args = ap.parse_args()

    src = h5py.File(args.src, "r")
    dst = h5py.File(args.dst, "r")
    claves = sorted(dst["data"].keys(), key=lambda k: int(k.split("_")[1]))

    print(f"demos: {len(src['data'])} en el original, {len(dst['data'])} en el re-renderizado\n")
    print(f"{'demo':<9}{'pasos':>7}{'=':>3}{'grados_src':>12}{'grados_dst':>12}{'delta':>9}{'exito':>8}{'max|dAcc|':>11}")

    fallos, desajustes, deltas, ausentes = [], [], [], []
    for k in claves:
        if k not in src["data"]:
            ausentes.append(k)
            continue
        s, d = src["data"][k], dst["data"][k]
        ns, nd = s["processed_actions"].shape[0], d["processed_actions"].shape[0]
        gs, gd = grados(s), grados(d)
        n = min(ns, nd)
        dacc = float(np.abs(s["processed_actions"][:n] - d["processed_actions"][:n]).max())
        ok_pasos = ns == nd
        ok_exito = gd >= UMBRAL_GRADOS
        if not ok_pasos:
            desajustes.append(k)
        if not ok_exito:
            fallos.append((k, gd))
        deltas.append(gd - gs)
        print(f"{k:<9}{nd:>7}{'si' if ok_pasos else 'NO':>3}{gs:>12.1f}{gd:>12.1f}"
              f"{gd - gs:>+9.1f}{'si' if ok_exito else 'NO':>8}{dacc:>11.2e}")

    print()
    if ausentes:
        print(f"AVISO: demos en el re-renderizado sin equivalente en el original: {ausentes}")
    if desajustes:
        print(f"FALLO: numero de pasos distinto en {desajustes}")
    dl = np.array(deltas)
    print(f"desviacion del giro: media {dl.mean():+.1f}  min {dl.min():+.1f}  max {dl.max():+.1f} grados")
    print(f"episodios que siguen cruzando los {UMBRAL_GRADOS:.0f} grados: {len(claves) - len(fallos)}/{len(claves)}")
    if fallos:
        print("PERDIDOS (por debajo del umbral):")
        for k, g in fallos:
            print(f"   {k}: {g:.1f} grados")

    # camara: si no cambia, el fondo no se esta renderizando
    k0 = claves[0]
    ms = float(src["data"][k0]["camera_obs"]["robot_head_cam_rgb"][0].mean())
    md = float(dst["data"][k0]["camera_obs"]["robot_head_cam_rgb"][0].mean())
    print(f"\ncamara, fotograma 0 de {k0}: original {ms:.2f} -> re-renderizado {md:.2f}"
          f"  ({'CAMBIA' if abs(md - ms) > 1.0 else 'NO CAMBIA -- el fondo no se esta renderizando'})")

    return 1 if (desajustes or ausentes) else 0


if __name__ == "__main__":
    sys.exit(main())
