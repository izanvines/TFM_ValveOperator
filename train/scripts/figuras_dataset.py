"""Figuras del capitulo de dataset: que hay dentro de las 100 demostraciones.

Se ejecuta con el interprete del CONTENEDOR, que es el que tiene h5py y matplotlib a la vez:

    /isaac-sim/python.sh /eval/arena_extras/figuras_dataset.py \
        --hdf5 /datasets/isaaclab_arena/g1_valve/valve_100.hdf5 --salida /eval/figuras

Reutiliza paleta y helpers de `figuras_resultados.py` para que las nueve figuras de la memoria
se lean como un sistema y no como nueve graficas sueltas.

UNA REGLA DE COLOR QUE NO SE PUEDE ROMPER. En las figuras de resultados el azul es GR00T y el
naranja es ACT, siempre. Aqui no hay politicas, asi que **no se usa ninguno de los dos**: la
disposicion de la valvula va en dos grises. Si el lector ha aprendido que azul = GR00T, pintar
"frontal" de azul le hace leer mal la figura antes de llegar al pie.
"""
import argparse
import os
import sys

import h5py
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from figuras_resultados import (  # noqa: E402
    REJILLA, TINTA, TINTA_2, TINTA_3, _guarda, _limpia, plt,
)

GRIS_FUERTE = "#52514e"   # cenital, la dificil
GRIS_SUAVE = "#b8b7b4"    # frontal

# Del layout de 23 dims de `g1_decoupled_wbc_pink_action.py`.
NOMBRES_ACCION = (
    ["mano izq.", "mano der."]
    + [f"brazo izq. pos {e}" for e in "xyz"]
    + [f"brazo izq. quat {e}" for e in "xyzw"]
    + [f"brazo der. pos {e}" for e in "xyz"]
    + [f"brazo der. quat {e}" for e in "xyzw"]
    + [f"navegación {e}" for e in "xyω"]
    + ["altura pelvis"]
    + [f"torso {e}" for e in ("roll", "pitch", "yaw")]
)
SESIONES = [("sesión 02", 0, 25), ("sesión 03", 25, 50), ("sesión 04", 50, 75), ("sesión 05", 75, 100)]


def lee(ruta):
    """Disposicion, duracion en pasos y acciones de cada demostracion."""
    disp, pasos, acciones = [], [], []
    with h5py.File(ruta, "r") as f:
        d = f["data"]
        for k in sorted(d.keys(), key=lambda x: int(x.split("_")[-1])):
            q = np.array(d[k]["initial_state"]["articulation"]["valve"]["root_pose"]).ravel()[3:7]
            # frontal lleva una componente ~0.707; cenital tiene los cuatro a 0.5.
            disp.append("frontal" if abs(abs(q[3]) - 0.707) < 0.05 or abs(abs(q[2]) - 0.707) < 0.05
                        else "cenital")
            a = np.array(d[k]["actions"])
            acciones.append(a)
            pasos.append(len(a))
    return disp, np.array(pasos), acciones


def figura_reparto(disp, salida):
    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    _limpia(ax)
    etiquetas, frontales, cenitales = [], [], []
    for nombre, ini, fin in SESIONES:
        trozo = disp[ini:fin]
        etiquetas.append(nombre)
        frontales.append(trozo.count("frontal"))
        cenitales.append(trozo.count("cenital"))
    etiquetas.append("total")
    frontales.append(sum(frontales))
    cenitales.append(sum(cenitales))

    x = np.arange(len(etiquetas))
    ax.bar(x, frontales, 0.62, color=GRIS_SUAVE, edgecolor="none", zorder=3, label="frontal")
    ax.bar(x, cenitales, 0.62, bottom=frontales, color=GRIS_FUERTE, edgecolor="none", zorder=3,
           label="cenital")
    for xi, (fr, ce) in enumerate(zip(frontales, cenitales)):
        ax.text(xi, fr / 2, str(fr), ha="center", va="center", color=TINTA, fontsize=9)
        ax.text(xi, fr + ce / 2, str(ce), ha="center", va="center", color="white", fontsize=9)
    ax.axvline(len(SESIONES) - 0.5, color=TINTA_3, linewidth=0.8, linestyle=(0, (4, 3)))
    ax.set_xticks(x)
    ax.set_xticklabels(etiquetas, color=TINTA)
    ax.set_ylabel("demostraciones")
    ax.set_title("Disposición de la válvula en el dataset", loc="left", fontsize=12,
                 fontweight="bold", color=TINTA, pad=24)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.01), ncol=2)
    fig.text(0.02, -0.06,
             "La disposición se sortea al 50 % en cada reset; nadie forzó el equilibrio. Las "
             "sesiones 02-03 salieron\ncargadas de cenitales y las 04-05 al revés, y el total "
             "quedó en 50/50 por casualidad.",
             ha="left", fontsize=8.5, color=TINTA_2)
    _guarda(fig, salida, "fig5_reparto_disposiciones")


def figura_duracion(pasos, salida):
    seg = pasos / 50.0                       # 50 Hz: decimation 4 x dt 0.005
    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    _limpia(ax)
    ax.hist(seg, bins=np.arange(0, max(seg) + 1.0, 0.5), color=GRIS_FUERTE, edgecolor="white",
            linewidth=0.6, zorder=3)
    med = float(np.median(seg))
    ax.axvline(med, color=TINTA, linewidth=1.4, zorder=4)
    ax.text(med, ax.get_ylim()[1] * 0.94, f"  mediana {med:.1f} s", color=TINTA, fontsize=9,
            fontweight="bold", va="top")
    ax.set_xlabel("duración de la demostración (s)")
    ax.set_ylabel("demostraciones")
    ax.set_title("Cuánto dura abrir la válvula", loc="left", fontsize=12, fontweight="bold",
                 color=TINTA, pad=14)
    fig.text(0.02, -0.08,
             f"n = {len(seg)} demostraciones, {seg.sum() / 60:.0f} min en total. El episodio se "
             "corta solo al detectar el éxito,\nasí que esto mide la tarea, no el presupuesto de "
             "30 s con el que se grabó.",
             ha="left", fontsize=8.5, color=TINTA_2)
    _guarda(fig, salida, "fig6_duracion_episodios")


def figura_std_acciones(acciones, salida):
    todas = np.concatenate(acciones, axis=0)          # (pasos totales, 23)
    std = todas.std(axis=0)
    cero = std <= 1e-9

    fig, ax = plt.subplots(figsize=(6.6, 6.2))
    _limpia(ax, rejilla_y=False)
    ax.set_axisbelow(True)
    ax.xaxis.grid(True, color=REJILLA, linewidth=0.8)
    y = np.arange(len(std))[::-1]                      # dim 0 arriba

    # Las dims muertas se marcan con una banda rayada: una barra de longitud cero es invisible,
    # y justo esas son las que hay que ver.
    for yi, muerta in zip(y, cero):
        if muerta:
            ax.axhspan(yi - 0.45, yi + 0.45, facecolor=REJILLA, edgecolor=TINTA_3,
                       linewidth=0.6, hatch="///", zorder=1)
    ax.barh(y, std, 0.62, color=GRIS_FUERTE, edgecolor="none", zorder=3)
    for yi, v, muerta in zip(y, std, cero):
        if muerta:
            ax.text(max(std) * 0.012, yi, "std = 0", va="center", ha="left", fontsize=8.5,
                    fontweight="bold", color=TINTA, zorder=4)
        else:
            # `altura pelvis` vale ~1e-4: con tres decimales salia "0.000", indistinguible de
            # una dim muerta pero sin la banda rayada. Se cambia a notacion cientifica.
            txt = f"{v:.3f}" if v >= 5e-4 else f"{v:.1e}"
            ax.text(v + max(std) * 0.012, yi, txt, va="center", ha="left", fontsize=8,
                    color=TINTA_2, zorder=4)
    ax.set_yticks(y)
    ax.set_yticklabels(NOMBRES_ACCION, color=TINTA, fontsize=8.5)
    ax.set_xlim(0, max(std) * 1.22)
    ax.set_xlabel("desviación típica sobre las 100 demostraciones")
    # El numero va calculado, no escrito: con `sesion_01` (empujar) eran 8 porque las manos no
    # se movian, y con el dataset definitivo (agarre) son 6. Un titulo a mano se queda viejo.
    ax.set_title(f"Las {len(std)} dimensiones de la acción, y las {int(cero.sum())} que no se mueven",
                 loc="left", fontsize=12, fontweight="bold", color=TINTA, pad=14)
    fig.text(0.02, -0.05,
             f"{int(cero.sum())} de {len(std)} dimensiones tienen desviación típica exactamente "
             "cero. La normalización divide por ese\nvalor: o da división por cero, o un épsilon "
             "que amplifica el ruido hasta hacerlo señal.",
             ha="left", fontsize=8.5, color=TINTA_2)
    _guarda(fig, salida, "fig7_std_espacio_accion")
    return std, cero


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hdf5", default="/datasets/isaaclab_arena/g1_valve/valve_100.hdf5")
    p.add_argument("--salida", default="/eval/figuras")
    a = p.parse_args()

    disp, pasos, acciones = lee(a.hdf5)
    print(f"{len(disp)} demostraciones  reparto={ {d: disp.count(d) for d in sorted(set(disp))} }")
    print(f"duracion: mediana {np.median(pasos) / 50:.1f} s  min {pasos.min() / 50:.1f}  "
          f"max {pasos.max() / 50:.1f}  total {pasos.sum() / 50 / 60:.1f} min")

    os.makedirs(a.salida, exist_ok=True)
    figura_reparto(disp, a.salida)
    figura_duracion(pasos, a.salida)
    std, cero = figura_std_acciones(acciones, a.salida)
    print("dims con std = 0:", [NOMBRES_ACCION[i] for i in np.flatnonzero(cero)])


if __name__ == "__main__":
    main()
