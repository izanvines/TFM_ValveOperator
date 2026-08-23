"""Figuras de resultados para la memoria: ACT contra GR00T en `g1_valve`.

Se ejecuta con el interprete del CONTENEDOR (`/isaac-sim/python.sh`), que es el unico que tiene
matplotlib y h5py a la vez.

    /isaac-sim/python.sh /eval/arena_extras/figuras_resultados.py \
        --gr00t /tmp/isaaclab/logs/dataset_A_rank0.hdf5 \
        --act   /tmp/isaaclab/logs/dataset_B_rank0.hdf5 \
        --salida /eval/figuras

QUE MIDE CADA COSA, porque la nomenclatura confunde:

  `success`               por episodio, booleano: la valvula supero media vuelta y lo mantuvo.
  `revolute_joint_state`  por PASO, la apertura normalizada 0..1 sobre los limites del joint
                          (0-360 grados), asi que grados = apertura * 360 y el umbral de exito
                          (apertura > 0.5) son 180 grados.
  `initial_state/articulation/valve/root_pose`  pos(3) + quat(4). El cuaternion distingue la
                          disposicion: frontal lleva z ~ 0.707, cenital los cuatro a 0.5.

SOBRE LA GRAFICA DE PERDIDA. En aprendizaje por imitacion no existe la curva de recompensa del
RL. La perdida es un error de regresion contra las acciones del operador: que baje significa que
la red copia bien las demostraciones, **no** que el robot abra la valvula. Una politica puede
tener una perdida excelente y 0 % de exito si aprende la media de las demostraciones. La
evidencia de aprendizaje aqui es la tasa de exito en simulacion; la perdida solo dice que la
optimizacion convergio. El pie de la figura 1 lo deja escrito.
"""

import argparse
import json
import math
import os
import re

import h5py
import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402

# --- Paleta ---------------------------------------------------------------------------------
# Slots 1 y 2 del tema categorico de referencia. Validados con `validate_palette.js`:
# separacion ΔE 24.7 con protanopia y 33.6 en vision normal, ambos muy por encima del minimo.
# No cambiar por gusto: un par de hues que "se ven bien" puede ser indistinguible para un 8 % de
# los lectores varones.
AZUL = "#2a78d6"    # GR00T
NARANJA = "#eb6834"  # ACT
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TINTA_3 = "#8a8985"
REJILLA = "#e3e2df"

COLOR = {"GR00T": AZUL, "ACT": NARANJA}

plt.rcParams.update({
    "figure.dpi": 120,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "axes.edgecolor": TINTA_3,
    "axes.labelcolor": TINTA_2,
    "text.color": TINTA,
    "xtick.color": TINTA_2,
    "ytick.color": TINTA_2,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "legend.frameon": False,
})


def _limpia(ax, rejilla_y=True):
    """Ejes recesivos: sin marco superior/derecho y rejilla solo en el eje del valor."""
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    ax.spines["left"].set_color(TINTA_3)
    ax.spines["bottom"].set_color(TINTA_3)
    if rejilla_y:
        ax.set_axisbelow(True)
        ax.yaxis.grid(True, color=REJILLA, linewidth=0.8)
        ax.xaxis.grid(False)


def wilson(exitos: int, n: int, z: float = 1.96):
    """Intervalo de confianza de Wilson al 95 %.

    No se usa el intervalo normal (p +- z*sqrt(p(1-p)/n)) porque con proporciones cercanas a 0
    o a 1 -- justo donde van a caer estos resultados -- se sale del [0,1] y da limites absurdos.
    Wilson esta siempre dentro y se comporta bien con n moderado.
    """
    if n == 0:
        return 0.0, 0.0, 0.0
    p = exitos / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    margen = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, centro - margen), min(1.0, centro + margen)


def lee_rollouts(ruta):
    """Devuelve una lista de dicts, uno por rollout."""
    salida = []
    with h5py.File(ruta, "r") as f:
        datos = f["data"]
        for k in sorted(datos, key=lambda s: int(s.split("_")[-1])):
            g = datos[k]
            exito = bool(np.array(g["success"]).ravel()[0]) if "success" in g else bool(
                g.attrs.get("success", False))
            apertura = np.array(g["revolute_joint_state"]).ravel() if "revolute_joint_state" in g else np.array([0.0])
            disp = "desconocida"
            try:
                q = np.array(g["initial_state"]["articulation"]["valve"]["root_pose"]).ravel()[3:7]
                disp = "frontal" if abs(abs(q[2]) - 0.70710678) < 0.05 else "cenital"
            except Exception:
                pass
            salida.append({
                "episodio": k,
                "exito": exito,
                "grados": float(np.abs(apertura).max() * 360.0),
                "movio": float(np.abs(apertura).max()) > 0.05,
                "disposicion": disp,
                "pasos": int(apertura.shape[0]),
            })
    return salida


# --- Figura 1: curvas de perdida --------------------------------------------------------------
def curva_gr00t(directorio):
    if not directorio or not os.path.isdir(directorio):
        return None, None
    candidatos = [os.path.join(directorio, "trainer_state.json")]
    candidatos += [os.path.join(directorio, d, "trainer_state.json")
                   for d in sorted(os.listdir(directorio)) if d.startswith("checkpoint-")]
    for cand in candidatos:
        if os.path.isfile(cand):
            with open(cand) as fh:
                hist = json.load(fh).get("log_history", [])
            pasos = [h["step"] for h in hist if "loss" in h]
            perdidas = [h["loss"] for h in hist if "loss" in h]
            if pasos:
                return pasos, perdidas
    return None, None


def curva_act(log):
    """LeRobot no escribe historico a disco con wandb desactivado: se saca del registro."""
    if not os.path.isfile(log):
        return None, None
    pasos, perdidas = [], []
    patron = re.compile(r"step:\s*([\d.]+)([KM]?).*?loss:\s*([\d.]+)")
    for linea in open(log, errors="ignore"):
        m = patron.search(linea)
        if m:
            n = float(m.group(1)) * {"": 1, "K": 1e3, "M": 1e6}[m.group(2)]
            pasos.append(n)
            perdidas.append(float(m.group(3)))
    return (pasos, perdidas) if pasos else (None, None)


def figura_perdida(dir_gr00t, log_act, salida):
    pg, lg = curva_gr00t(dir_gr00t)
    pa, la = curva_act(log_act)
    if not pg and not pa:
        print("figura 1: sin curvas de perdida, salto")
        return
    # Paneles separados y NO dos ejes en la misma grafica: las dos perdidas miden cosas
    # distintas (flow matching contra L1 sobre acciones) y superponerlas invita a compararlas,
    # que es justo lo que no se puede hacer.
    fig, ejes = plt.subplots(1, 2, figsize=(9, 3.4))
    for ax, (nombre, x, y) in zip(ejes, [("GR00T", pg, lg), ("ACT", pa, la)]):
        _limpia(ax)
        if x:
            ax.plot(x, y, color=COLOR[nombre], linewidth=2, solid_capstyle="round")
            ax.set_title(nombre, color=TINTA, loc="left", fontweight="bold")
            ax.set_xlabel("paso de entrenamiento")
            ax.set_ylabel("pérdida")
            ax.text(0.97, 0.93, f"final {y[-1]:.4f}", transform=ax.transAxes,
                    ha="right", va="top", color=TINTA_2, fontsize=9)
        else:
            ax.set_title(f"{nombre} — sin datos", color=TINTA_3, loc="left")
            ax.set_xticks([]); ax.set_yticks([])
    # `bbox="tight"` recorta al contenido, asi que el titulo general y el pie hay que
    # separarlos a mano o pisan el titulo del panel y las etiquetas del eje.
    fig.suptitle("Convergencia del entrenamiento", x=0.09, y=1.10, ha="left", fontsize=12,
                 fontweight="bold", color=TINTA)
    fig.subplots_adjust(wspace=0.28)
    fig.text(0.09, -0.20,
             "La pérdida es un error de regresión contra las acciones del operador: que baje "
             "significa que la red copia bien\nlas demostraciones, no que el robot abra la "
             "válvula. La evidencia de aprendizaje es la tasa de éxito (figura 2).",
             ha="left", fontsize=8.5, color=TINTA_2)
    _guarda(fig, salida, "fig1_curvas_perdida")


# --- Figura 2: tasa de exito ------------------------------------------------------------------
def _barras_agrupadas(ax, grupos, nombres, valores, errores, etiquetas_n=None):
    """Barras agrupadas donde el COLOR siempre significa politica, nunca metrica.

    Es deliberado: si el color codificara la metrica, la muestra de la leyenda no coincidiria
    con el color de las barras de una de las dos politicas y el lector tendria que adivinar.
    La metrica va en el eje x, que es la dimension que si se puede etiquetar con palabras.
    """
    x = np.arange(len(grupos))
    ancho = 0.32 if len(nombres) == 2 else 0.5
    for i, n in enumerate(nombres):
        pos = x + (i - (len(nombres) - 1) / 2) * (ancho + 0.03)
        ax.bar(pos, valores[n], ancho, color=COLOR[n], edgecolor="none", zorder=3, label=n)
        ax.errorbar(pos, valores[n], yerr=errores[n], fmt="none", ecolor=TINTA_2,
                    elinewidth=1.2, capsize=4, zorder=4)
        for j, (xp, h) in enumerate(zip(pos, valores[n])):
            # Por encima del extremo de la barra de error, no de la barra: con intervalos
            # anchos la etiqueta caia justo encima del bigote y se leian mal las dos cosas.
            ax.text(xp, h + errores[n][1][j] + 0.025, f"{h:.0%}", ha="center", va="bottom",
                    color=TINTA, fontsize=9.5, fontweight="bold")
            if etiquetas_n:
                ax.text(xp, 0.02, f"n={etiquetas_n[n][j]}", ha="center", va="bottom",
                        color="white", fontsize=8)
    ax.set_xticks(x)
    ax.set_ylim(0, 1.15)
    # Sin este limite las barras salen desproporcionadamente anchas cuando hay pocos grupos.
    ax.set_xlim(-0.65, len(grupos) - 0.35)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))


def figura_exito(datos, salida):
    nombres = list(datos)
    grupos = [("exito", "exito"), ("movio", "movio")]
    valores, errores = {}, {}
    for n in nombres:
        valores[n], errores[n] = [], [[], []]
        for _, clave in grupos:
            k = sum(1 for d in datos[n] if d[clave])
            p, lo, hi = wilson(k, len(datos[n]))
            valores[n].append(p)
            errores[n][0].append(max(0.0, p - lo))
            errores[n][1].append(max(0.0, hi - p))

    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    _limpia(ax)
    _barras_agrupadas(ax, grupos, nombres, valores, errores)
    ax.set_xticklabels(["éxito", "movió la válvula"], color=TINTA)
    ax.set_ylabel("proporción de rollouts")
    ax.set_title("Tasa de éxito en simulación", loc="left", fontsize=12,
                 fontweight="bold", color=TINTA, pad=28)
    # Leyenda FUERA del area de dibujo: dentro pisaba las etiquetas de valor.
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.01), ncol=len(nombres))
    n_txt = " · ".join(f"{n}: n={len(datos[n])}" for n in nombres)
    pie = (n_txt + ". Barras de error: intervalo de Wilson al 95 %. «Movió la válvula» es la "
           "métrica de progreso" + "\n" + "parcial (revolute_joint_moved_rate): distingue no "
           "llegar a tocarla de girarla sin completar media vuelta.")
    fig.text(0.02, -0.04, pie, ha="left", fontsize=8.5, color=TINTA_2)
    _guarda(fig, salida, "fig2_tasa_exito")


# --- Figura 3: distribucion del angulo final ---------------------------------------------------
def figura_angulos(datos, salida):
    nombres = list(datos)
    fig, ejes = plt.subplots(len(nombres), 1, figsize=(7.2, 2.3 * len(nombres)), sharex=True)
    if len(nombres) == 1:
        ejes = [ejes]
    bordes = np.arange(0, 380, 15)
    for i, (ax, n) in enumerate(zip(ejes, nombres)):
        _limpia(ax)
        g = [d["grados"] for d in datos[n]]
        ax.hist(g, bins=bordes, color=COLOR[n], edgecolor="white", linewidth=0.8, zorder=3)
        ax.axvline(180, color=TINTA_2, linewidth=1.5, linestyle=(0, (4, 3)), zorder=4)
        ax.set_ylabel("rollouts")
        ax.set_title(n, loc="left", color=TINTA, fontweight="bold")
        # Solo en el panel de arriba: repetir la anotacion en cada panel la convierte en ruido,
        # y encima cae sobre las barras cuando la distribucion se concentra junto al umbral.
        if i == 0:
            ax.annotate("umbral de éxito · 180° = media vuelta",
                        xy=(180, 1.0), xycoords=("data", "axes fraction"),
                        xytext=(6, 6), textcoords="offset points",
                        color=TINTA_2, fontsize=8.5, ha="left", va="bottom")
    ejes[-1].set_xlabel("ángulo final del volante (grados)")
    fig.suptitle("Hasta dónde llega el volante en cada rollout", x=0.06, ha="left",
                 fontsize=12, fontweight="bold", color=TINTA)
    fig.text(0.06, -0.10,
             "Un fallo a 170° y un fallo a 10° cuentan igual en la tasa de éxito y no son lo "
             "mismo: el primero es\nuna política que casi resuelve la tarea, el segundo una que "
             "no la ha aprendido.",
             ha="left", fontsize=8.5, color=TINTA_2)
    _guarda(fig, salida, "fig3_distribucion_angulo")


# --- Figura 4: exito por disposicion ------------------------------------------------------------
def figura_disposicion(datos, salida):
    disposiciones = ["frontal", "cenital"]
    if not any(d["disposicion"] in disposiciones for r in datos.values() for d in r):
        print("figura 4: no hay disposicion registrada, salto")
        return
    nombres = list(datos)
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    _limpia(ax)
    x = np.arange(len(disposiciones))
    ancho = 0.34
    for i, n in enumerate(nombres):
        alturas, err, etiquetas_n = [], [[], []], []
        for disp in disposiciones:
            sub = [d for d in datos[n] if d["disposicion"] == disp]
            k = sum(1 for d in sub if d["exito"])
            p, lo, hi = wilson(k, len(sub))
            alturas.append(p)
            err[0].append(max(0.0, p - lo))
            err[1].append(max(0.0, hi - p))
            etiquetas_n.append(len(sub))
        pos = x + (i - (len(nombres) - 1) / 2) * (ancho + 0.02)
        ax.bar(pos, alturas, ancho, color=COLOR[n], edgecolor="none", zorder=3, label=n)
        ax.errorbar(pos, alturas, yerr=err, fmt="none", ecolor=TINTA_2, elinewidth=1.2,
                    capsize=4, zorder=4)
        for j, (xp, h, nn) in enumerate(zip(pos, alturas, etiquetas_n)):
            ax.text(xp, h + err[1][j] + 0.025, f"{h:.0%}", ha="center", va="bottom",
                    color=TINTA, fontsize=9.5, fontweight="bold")
            ax.text(xp, 0.02, f"n={nn}", ha="center", va="bottom", color="white", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(["frontal\n(volante de frente)", "cenital\n(volante hacia arriba)"],
                       color=TINTA)
    ax.set_ylim(0, 1.12)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_ylabel("tasa de éxito")
    ax.set_title("¿Generaliza a las dos disposiciones?", loc="left", fontsize=12,
                 fontweight="bold", color=TINTA, pad=14)
    ax.legend(loc="upper right", ncol=2)
    fig.text(0.02, -0.04,
             "La disposición se sortea 50/50 en cada reset, igual que durante la grabación. "
             "Una diferencia grande\nentre las dos columnas dice qué hay que grabar más, no que "
             "la política sea mala.",
             ha="left", fontsize=8.5, color=TINTA_2)
    _guarda(fig, salida, "fig4_exito_por_disposicion")


def _guarda(fig, salida, nombre):
    os.makedirs(salida, exist_ok=True)
    for ext in ("png", "pdf"):     # PDF vectorial para insertar en la memoria sin pixelar
        fig.savefig(os.path.join(salida, f"{nombre}.{ext}"))
    plt.close(fig)
    print(f"  escrito {nombre}.png / .pdf")


def tabla(datos, salida):
    lineas = ["| política | n | éxito | IC 95 % | movió la válvula | ángulo medio | frontal | cenital |",
              "|---|---|---|---|---|---|---|---|"]
    for n, r in datos.items():
        k = sum(1 for d in r if d["exito"])
        p, lo, hi = wilson(k, len(r))
        movio = sum(1 for d in r if d["movio"]) / len(r)
        ang = np.mean([d["grados"] for d in r])
        celdas = []
        for disp in ("frontal", "cenital"):
            sub = [d for d in r if d["disposicion"] == disp]
            celdas.append(f"{sum(1 for d in sub if d['exito'])}/{len(sub)}" if sub else "—")
        lineas.append(f"| {n} | {len(r)} | **{p:.0%}** ({k}/{len(r)}) | {lo:.0%}–{hi:.0%} | "
                      f"{movio:.0%} | {ang:.0f}° | {celdas[0]} | {celdas[1]} |")
    texto = "\n".join(lineas)
    with open(os.path.join(salida, "resultados.md"), "w") as fh:
        fh.write("# Resultados: ACT contra GR00T en `g1_valve`\n\n" + texto + "\n")
    print("\n" + texto + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--gr00t", help="HDF5 de metricas de la evaluacion de GR00T")
    p.add_argument("--act", help="HDF5 de metricas de la evaluacion de ACT")
    p.add_argument("--dir_gr00t", default="", help="directorio de salida del fine-tune de GR00T")
    p.add_argument("--log_act", default="", help="registro de entrenamiento de ACT")
    p.add_argument("--salida", default="/eval/figuras")
    a = p.parse_args()

    datos = {}
    for nombre, ruta in (("GR00T", a.gr00t), ("ACT", a.act)):
        if ruta and os.path.isfile(ruta):
            datos[nombre] = lee_rollouts(ruta)
            print(f"{nombre}: {len(datos[nombre])} rollouts leidos de {ruta}")
        else:
            print(f"{nombre}: sin HDF5 de metricas, se omite")

    os.makedirs(a.salida, exist_ok=True)
    if a.dir_gr00t or a.log_act:
        figura_perdida(a.dir_gr00t, a.log_act, a.salida)
    if datos:
        figura_exito(datos, a.salida)
        figura_angulos(datos, a.salida)
        figura_disposicion(datos, a.salida)
        tabla(datos, a.salida)
    else:
        print("sin datos de evaluacion: solo se ha intentado la figura de perdida")


if __name__ == "__main__":
    main()
