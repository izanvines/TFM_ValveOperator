"""Figuras 8 y 9: los dos ejes de coste. Cuantos datos cuesta, y cuanto tarda en inferir.

Se ejecuta con el interprete del CONTENEDOR, el unico que tiene h5py y matplotlib a la vez:

    /isaac-sim/python.sh /eval/arena_extras/figuras_eficiencia.py \
        --resultados /eval/resultados --logs /eval/logs --salida /eval/figuras

Reutiliza paleta y helpers de `figuras_resultados.py`: azul GR00T, naranja ACT, siempre.

FIGURA 8 -- eficiencia en datos. Cada punto es un entrenamiento independiente sobre un
subconjunto ESTRATIFICADO (12F/13C y 25F/25C, sorteados con semilla fija), evaluado con
100 tiradas de semilla 42, que son las mismas condiciones iniciales en los tres puntos y en
las dos politicas. Lo unico que cambia entre puntos es la CANTIDAD de demostraciones.

  Aviso que hay que leer antes de interpretar la pendiente: cada punto es UN entrenamiento,
  asi que la variacion entre puntos mezcla el efecto de los datos con la varianza de semilla
  del entrenamiento. Con estas n, ninguna de las diferencias dentro de una misma politica es
  significativa (McNemar emparejado, p >= 0.11). La lectura defendible es que la curva es
  PLANA, no que suba o baje.

FIGURA 9 -- coste de inferencia. Milisegundos por chunk medidos en lazo cerrado dentro del
simulador con `latencia_wrapper.py`, no con un tensor sintetico. El cliente pide un chunk cada
40 pasos y el entorno corre a 50 Hz, asi que el presupuesto real son 40/50 = 0,8 s. Se descarta
la primera llamada de cada politica (485 ms GR00T, 198 ms ACT): es la compilacion de kernels.
"""
import argparse
import json
import os
import sys

import h5py
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from figuras_resultados import (  # noqa: E402
    AZUL, COLOR, NARANJA, REJILLA, TINTA, TINTA_2, TINTA_3, _guarda, _limpia, plt, wilson,
)
from matplotlib.ticker import PercentFormatter  # noqa: E402

PRESUPUESTO_MS = 800.0   # 40 pasos de chunk / 50 Hz

FICHEROS = {
    ("GR00T", 25): "gr00t_25demos.hdf5",
    ("GR00T", 50): "gr00t_50demos.hdf5",
    ("GR00T", 100): "gr00t_100rollouts.hdf5",
    ("ACT", 25): "act_25demos.hdf5",
    ("ACT", 50): "act_50demos.hdf5",
    ("ACT", 100): "act_100rollouts.hdf5",
}


def lee_rollouts(ruta):
    salida = []
    with h5py.File(ruta, "r") as f:
        d = f["data"]
        for k in sorted(d, key=lambda s: int(s.split("_")[-1])):
            g = d[k]
            q = np.array(g["initial_state"]["articulation"]["valve"]["root_pose"]).ravel()
            # frontal lleva una componente ~0.707 en el cuaternion; cenital tiene los cuatro a 0.5
            salida.append({
                "exito": bool(np.array(g["success"]).ravel()[0]),
                "disposicion": "frontal" if abs(abs(q[5]) - 0.70710678) < 0.05 else "cenital",
            })
    return salida


def _serie(ax, tamanos, datos, pol, filtro=None):
    """Punto + barra de Wilson por tamano de dataset. Devuelve las tasas para etiquetar."""
    xs, ps, lo, hi = [], [], [], []
    for n in tamanos:
        r = datos[(pol, n)]
        if filtro:
            r = [d for d in r if d["disposicion"] == filtro]
        k = sum(1 for d in r if d["exito"])
        p, a, b = wilson(k, len(r))
        xs.append(n); ps.append(p); lo.append(p - a); hi.append(b - p)
    # El intervalo va PRIMERO y en fino: si se dibuja encima de la linea la tapa.
    ax.errorbar(xs, ps, yerr=[lo, hi], fmt="none", ecolor=COLOR[pol], elinewidth=1.2,
                capsize=4, capthick=1.2, alpha=0.55, zorder=2)
    ax.plot(xs, ps, color=COLOR[pol], linewidth=2, marker="o", markersize=7,
            markerfacecolor="white", markeredgewidth=2, zorder=3, label=pol,
            solid_capstyle="round")
    return ps


def figura_curva(datos, salida):
    tamanos = [25, 50, 100]
    fig, ejes = plt.subplots(1, 2, figsize=(9, 3.6), sharey=True)
    paneles = [(None, "Todas las tiradas"), ("cenital", "Solo disposición cenital")]
    for ax, (filtro, titulo) in zip(ejes, paneles):
        _limpia(ax)
        for pol in ("GR00T", "ACT"):
            ps = _serie(ax, tamanos, datos, pol, filtro)
            # Etiqueta al final de la linea en vez de leyenda dentro del area de datos.
            ax.annotate(f"{pol}  {ps[-1]:.0%}", (tamanos[-1], ps[-1]),
                        xytext=(9, 0), textcoords="offset points", va="center",
                        color=COLOR[pol], fontsize=9, fontweight="bold")
        ax.set_xscale("log")
        ax.set_xticks(tamanos)
        ax.set_xticklabels([str(t) for t in tamanos])
        ax.minorticks_off()
        ax.set_xlim(21, 165)
        ax.set_ylim(0.55, 1.02)
        ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        ax.set_xlabel("demostraciones de entrenamiento")
        ax.set_title(titulo, color=TINTA, loc="left", fontweight="bold")
    ejes[0].set_ylabel("tasa de éxito")
    fig.subplots_adjust(wspace=0.12)
    _guarda(fig, salida, "fig8_curva_eficiencia")


def figura_latencia(medidas, salida):
    fig, ax = plt.subplots(figsize=(9, 2.5))
    _limpia(ax, rejilla_y=False)
    ax.set_axisbelow(True)
    ax.xaxis.grid(True, color=REJILLA, linewidth=0.8)
    ax.yaxis.grid(False)

    orden = ["GR00T", "ACT"]
    for y, pol in enumerate(orden):
        m = medidas[pol]
        med, p95 = float(np.median(m)), float(np.percentile(m, 95))
        # Las muestras de verdad, con transparencia: se ve la dispersion sin inventar una caja.
        ax.scatter(m, np.full(len(m), y) + np.random.default_rng(0).uniform(-0.09, 0.09, len(m)),
                   s=9, color=COLOR[pol], alpha=0.22, linewidths=0, zorder=2)
        ax.plot([m.min(), m.max()], [y, y], color=COLOR[pol], linewidth=1.6, alpha=0.7, zorder=3)
        ax.scatter([med], [y], s=95, color=COLOR[pol], zorder=4,
                   edgecolors="white", linewidths=1.6)
        # ACT cae pegado al borde izquierdo: centrar ahi su etiqueta la saca del area de ejes.
        num = (lambda v: f"{v:.1f}".replace(".", ",")) if med < 10 else (lambda v: f"{v:.0f}")
        ha, dx = ("left", -8) if med < 10 else ("center", 0)
        ax.annotate(f"mediana {num(med)} ms   ·   p95 {num(p95)} ms   ·   "
                    f"×{PRESUPUESTO_MS / med:.0f} de margen",
                    (med, y), xytext=(dx, 16), textcoords="offset points",
                    ha=ha, color=COLOR[pol], fontsize=9.5, fontweight="bold")

    ax.axvline(PRESUPUESTO_MS, color=TINTA_2, linewidth=1.4, linestyle=(0, (5, 3)), zorder=1)
    ax.axvspan(PRESUPUESTO_MS, 3000, color=TINTA_3, alpha=0.10, linewidth=0, zorder=0)
    ax.annotate("presupuesto 800 ms\n(40 pasos a 50 Hz)", (PRESUPUESTO_MS, 1.38),
                xytext=(-8, 0), textcoords="offset points", ha="right", va="center",
                color=TINTA_2, fontsize=8.5)

    ax.set_xscale("log")
    ax.set_xlim(3, 2200)
    ax.set_xticks([5, 10, 50, 100, 500, 800])
    ax.set_xticklabels(["5", "10", "50", "100", "500", "800"])
    ax.minorticks_off()
    ax.set_yticks(range(len(orden)))
    ax.set_yticklabels([f"{p}\n{'3,14 B' if p == 'GR00T' else '51,7 M'} par." for p in orden],
                       fontsize=9.5)
    ax.set_ylim(-0.5, 1.62)
    ax.invert_yaxis()
    ax.set_xlabel("milisegundos por chunk de acciones  (escala logarítmica)")
    _guarda(fig, salida, "fig9_latencia")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--resultados", default="/eval/resultados")
    p.add_argument("--logs", default="/eval/logs")
    p.add_argument("--salida", default="/eval/figuras")
    a = p.parse_args()

    datos = {}
    for clave, fich in FICHEROS.items():
        ruta = os.path.join(a.resultados, fich)
        if not os.path.isfile(ruta):
            print(f"FALTA {ruta}; no se puede dibujar la curva")
            return
        datos[clave] = lee_rollouts(ruta)
        print(f"{clave[0]} @{clave[1]}: {sum(d['exito'] for d in datos[clave])}/{len(datos[clave])}")

    medidas = {}
    for pol, fich in (("GR00T", "latencia_gr00t.jsonl"), ("ACT", "latencia_act.jsonl")):
        ruta = os.path.join(a.logs, fich)
        ms = [json.loads(l)["ms"] for l in open(ruta)]
        medidas[pol] = np.array(ms[1:])   # fuera el arranque en frio
        print(f"{pol}: {len(medidas[pol])} medidas, mediana {np.median(medidas[pol]):.1f} ms")

    os.makedirs(a.salida, exist_ok=True)
    figura_curva(datos, a.salida)
    figura_latencia(medidas, a.salida)


if __name__ == "__main__":
    main()
