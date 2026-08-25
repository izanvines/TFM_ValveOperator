"""Diagramas de la memoria: cadena de trabajo, arquitectura, Gantt y matriz de riesgos.

Se ejecuta con el interprete del CONTENEDOR, que es el que tiene matplotlib:

    /isaac-sim/python.sh /eval/arena_extras/figuras_memoria.py --salida /eval/figuras/memoria

Son diagramas, no graficas de datos, pero comparten paleta y tipografia con las nueve figuras de
resultados para que la memoria se lea como un sistema. Se importan de `figuras_resultados.py` en
vez de reimplementarlas.

REGLA DE COLOR. Azul es GR00T y naranja es ACT en toda la memoria. Aqui solo se usan donde
efectivamente representan a una de las dos politicas (las ramas de entrenamiento y de servicio);
todo lo demas va en grises. Pintar de azul una caja que no es GR00T ensena al lector una
correspondencia falsa.

Salen en PDF vectorial porque van a pagina completa en un documento a 12 pt: un PNG a 300 ppp se
nota al ampliar y pesa diez veces mas.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from figuras_resultados import (  # noqa: E402
    AZUL, NARANJA, REJILLA, TINTA, TINTA_2, TINTA_3, _guarda, plt,
)
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

GRIS_CAJA = "#f2f1ee"
GRIS_BORDE = "#c9c8c4"
VERDE = "#3f7d58"    # solo para el camino critico del Gantt


def _caja(ax, x, y, an, al, titulo, lineas=(), color=GRIS_CAJA, borde=GRIS_BORDE, tcolor=TINTA):
    """Caja redondeada con un titulo en negrita y, opcionalmente, lineas de detalle debajo."""
    ax.add_patch(FancyBboxPatch(
        (x, y), an, al, boxstyle="round,pad=0,rounding_size=0.08",
        facecolor=color, edgecolor=borde, linewidth=1.2, zorder=2))
    cy = y + al / 2
    if lineas:
        cy = y + al - 0.30
    ax.text(x + an / 2, cy, titulo, ha="center", va="center", fontsize=9.5,
            fontweight="bold", color=tcolor, zorder=3)
    for i, ln in enumerate(lineas):
        ax.text(x + an / 2, y + al - 0.58 - i * 0.26, ln, ha="center", va="center",
                fontsize=8, color=TINTA_2, zorder=3)


def _flecha(ax, p0, p1, color=TINTA_3, estilo="-|>", curva=0.0, lw=1.4):
    ax.add_patch(FancyArrowPatch(
        p0, p1, arrowstyle=estilo, mutation_scale=12, linewidth=lw, color=color,
        connectionstyle=f"arc3,rad={curva}", shrinkA=2, shrinkB=2, zorder=1))


def _lienzo(ancho, alto, xlim, ylim):
    fig, ax = plt.subplots(figsize=(ancho, alto))
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.axis("off")
    return fig, ax


# --- Figura: la cadena de trabajo -------------------------------------------------------------
def figura_pipeline(salida):
    fig, ax = _lienzo(9.2, 4.6, (0, 10.4), (0, 5.0))

    _caja(ax, 0.1, 3.25, 2.0, 1.05, "Teleoperación",
          ["PICO 4 Ultra", "sobre escena diáfana"])
    _caja(ax, 2.5, 3.25, 2.0, 1.05, "Grabación",
          ["HDF5: estado,", "acción e imagen"])
    _caja(ax, 4.9, 3.25, 2.1, 1.05, "Re-render",
          ["fondo de oficina", "con estado forzado"])
    _caja(ax, 7.4, 3.25, 2.0, 1.05, "Conversión",
          ["formato LeRobot", "43 grados de libertad"])

    for x0, x1 in ((2.1, 2.5), (4.5, 4.9), (7.0, 7.4)):
        _flecha(ax, (x0, 3.77), (x1, 3.77))

    # El conjunto de datos convertido baja y alimenta a las dos vias. Las cajas de
    # entrenamiento van APILADAS, no en fila: en fila, la flecha de la de arriba hacia la
    # evaluacion cruza por encima de la otra y se lee como si pasara por ella.
    _flecha(ax, (8.4, 3.25), (8.4, 2.95))
    ax.plot([1.6, 8.4], [2.95, 2.95], color=TINTA_3, linewidth=1.4, zorder=1)

    _caja(ax, 0.6, 1.65, 3.5, 0.85, "Ajuste fino de GR00T N1.7",
          ["3140 M de parámetros"], color="#eaf1fb", borde=AZUL, tcolor=AZUL)
    _caja(ax, 0.6, 0.45, 3.5, 0.85, "Entrenamiento de ACT",
          ["51,7 M de parámetros"], color="#fdeee7", borde=NARANJA, tcolor=NARANJA)

    _flecha(ax, (1.6, 2.95), (1.6, 2.50), color=AZUL)
    # La rama de ACT baja POR FUERA de la caja de GR00T (x=0.30 frente a 0.60 del borde): si
    # pasa por detras, se lee como si el ajuste fino alimentara a ACT.
    ax.plot([0.30, 1.6], [2.95, 2.95], color=NARANJA, linewidth=1.4, zorder=1)
    ax.plot([0.30, 0.30], [2.95, 0.87], color=NARANJA, linewidth=1.4, zorder=1)
    _flecha(ax, (0.30, 0.87), (0.60, 0.87), color=NARANJA)

    _caja(ax, 6.2, 0.75, 3.6, 1.55, "Evaluación",
          ["mismo simulador,", "mismas condiciones iniciales,", "misma métrica de éxito"])
    _flecha(ax, (4.1, 2.07), (6.2, 1.80), color=AZUL)
    _flecha(ax, (4.1, 0.87), (6.2, 1.20), color=NARANJA)

    ax.text(0.1, 4.75, "De la teleoperación a la tasa de éxito", fontsize=12,
            fontweight="bold", color=TINTA, ha="left", va="center")
    ax.text(0.1, 0.10,
            "Las dos vías consumen la misma conversión y se evalúan sobre el mismo banco: "
            "cualquier diferencia procede del método.",
            fontsize=8.5, color=TINTA_2, ha="left", va="center")
    _guarda(fig, salida, "pipeline")


# --- Figura: arquitectura ---------------------------------------------------------------------
def figura_arquitectura(salida):
    fig, ax = _lienzo(9.2, 4.6, (0, 10.4), (0, 5.2))

    # Contenedor.
    ax.add_patch(FancyBboxPatch(
        (0.1, 0.55), 4.6, 3.75, boxstyle="round,pad=0,rounding_size=0.10",
        facecolor="white", edgecolor=TINTA_3, linewidth=1.4, linestyle=(0, (4, 2)), zorder=1))
    ax.text(0.32, 4.05, "Contenedor  ·  Python 3.12", fontsize=9, fontweight="bold",
            color=TINTA_2, ha="left", va="center")

    _caja(ax, 0.4, 3.10, 4.0, 0.72, "Isaac Sim  +  Isaac Lab Arena", ["tarea g1_valve"])
    _caja(ax, 0.4, 1.95, 4.0, 0.72, "Cliente de evaluación", ["policy_runner"])
    _caja(ax, 0.4, 0.90, 4.0, 0.85, "Volúmenes montados",
          ["/datasets   ·   /models   ·   /eval"])

    _flecha(ax, (2.4, 3.10), (2.4, 2.67), estilo="<|-|>")

    # Servidores.
    ax.add_patch(FancyBboxPatch(
        (5.7, 0.55), 4.6, 3.75, boxstyle="round,pad=0,rounding_size=0.10",
        facecolor="white", edgecolor=TINTA_3, linewidth=1.4, linestyle=(0, (4, 2)), zorder=1))
    ax.text(5.92, 4.05, "Anfitrión  ·  entornos independientes, Python 3.10",
            fontsize=9, fontweight="bold", color=TINTA_2, ha="left", va="center")

    _caja(ax, 6.0, 3.00, 4.0, 0.85, "Servidor de GR00T N1.7",
          ["entorno propio de GR00T"], color="#eaf1fb", borde=AZUL, tcolor=AZUL)
    _caja(ax, 6.0, 1.95, 4.0, 0.85, "Servidor de ACT",
          ["entorno propio de LeRobot"], color="#fdeee7", borde=NARANJA, tcolor=NARANJA)
    _caja(ax, 6.0, 0.90, 4.0, 0.85, "Servidor de reproducción",
          ["acciones grabadas: cota superior"])

    # El canal.
    ax.text(5.2, 3.95, "ZMQ", fontsize=9, fontweight="bold", color=TINTA_2,
            ha="center", va="center", rotation=90)
    for y, c in ((3.42, AZUL), (2.37, NARANJA), (1.32, TINTA_3)):
        _flecha(ax, (4.4, 2.31), (6.0, y), estilo="<|-|>", color=c, curva=0.10, lw=1.2)

    ax.text(0.1, 4.95, "Arquitectura: un cliente, tres servidores intercambiables",
            fontsize=12, fontweight="bold", color=TINTA, ha="left", va="center")
    ax.text(0.1, 0.22,
            "Las bibliotecas de aprendizaje fijan versiones incompatibles con las del simulador, "
            "así que viven en entornos separados.",
            fontsize=8.5, color=TINTA_2, ha="left", va="center")
    _guarda(fig, salida, "arquitectura")


# --- Figura: Gantt ----------------------------------------------------------------------------
TAREAS = [
    ("Análisis y arranque",            0,  2, False),
    ("Entorno de simulación",          1,  6, True),
    ("Cadena de datos",                4,  8, True),
    ("Captura de demostraciones",      7, 11, True),
    ("Entrenamiento de las políticas", 10, 13, True),
    ("Evaluación y análisis",          12, 15, True),
    ("Documentación y dictamen",       13, 16, False),
    ("Gestión y seguimiento",           0, 16, False),
]


def figura_gantt(salida):
    fig, ax = plt.subplots(figsize=(9.2, 3.6))
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(TINTA_3)
    ax.set_axisbelow(True)
    ax.xaxis.grid(True, color=REJILLA, linewidth=0.8)

    for i, (nombre, ini, fin, critica) in enumerate(TAREAS):
        y = len(TAREAS) - 1 - i
        ax.barh(y, fin - ini, left=ini, height=0.52,
                color=VERDE if critica else GRIS_CAJA,
                edgecolor=VERDE if critica else GRIS_BORDE, linewidth=1.1)
        ax.text(fin + 0.22, y, f"{fin - ini} sem.", va="center", ha="left",
                fontsize=8, color=TINTA_2)

    ax.set_yticks(range(len(TAREAS)))
    ax.set_yticklabels([t[0] for t in reversed(TAREAS)], fontsize=9)
    ax.set_xticks(range(0, 17, 2))
    ax.set_xlim(0, 18.2)
    ax.set_xlabel("semanas desde el inicio del proyecto")
    ax.set_ylim(-0.7, len(TAREAS) - 0.3)

    ax.barh(-0.1, 0, left=0, color=VERDE, label="camino crítico")
    ax.barh(-0.1, 0, left=0, color=GRIS_CAJA, edgecolor=GRIS_BORDE, label="holgura disponible")
    ax.legend(loc="upper right", frameon=False, fontsize=8.5, ncol=2,
          bbox_to_anchor=(1.0, 1.02))

    fig.suptitle("Planificación del proyecto", x=0.02, y=1.04, ha="left",
                 fontsize=12, fontweight="bold", color=TINTA)
    _guarda(fig, salida, "gantt")


# --- Figura: matriz de riesgos -----------------------------------------------------------------
# (etiqueta, probabilidad 1-5, impacto 1-5, texto)
RIESGOS = [
    ("R1", 5, 4, "Inestabilidad de la pila de realidad mixta"),
    ("R2", 4, 3, "Incompatibilidad entre versiones de bibliotecas"),
    ("R3", 3, 5, "Invalidación de datos ya capturados"),
    ("R4", 3, 4, "Indisponibilidad de la estación de trabajo"),
    ("R5", 3, 3, "Ampliación no controlada del alcance"),
    ("R6", 3, 4, "Pérdida de cambios sobre el marco de terceros"),
    ("R7", 2, 4, "Baja del operador de teleoperación"),
    ("R8", 3, 2, "Resultados no concluyentes"),
]


def figura_riesgos(salida):
    fig, ax = plt.subplots(figsize=(8.4, 4.6))

    # Bandas de nivel: el producto probabilidad x impacto, en tres tramos.
    for p in range(1, 6):
        for im in range(1, 6):
            v = p * im
            c = "#f4f3f0" if v <= 6 else ("#f7ead9" if v <= 12 else "#f5dcd4")
            ax.add_patch(plt.Rectangle((p - 0.5, im - 0.5), 1, 1, facecolor=c,
                                       edgecolor="white", linewidth=1.5, zorder=0))

    ocupadas = {}
    for etq, p, im, _ in RIESGOS:
        # Dos riesgos comparten celda: se separan para que ambos se lean.
        k = (p, im)
        n = ocupadas.get(k, 0)
        ocupadas[k] = n + 1
        dx = 0.0 if n == 0 else 0.24 * (1 if n % 2 else -1)
        ax.scatter([p + dx], [im], s=430, color=TINTA_2, zorder=3, edgecolors="white",
                   linewidths=1.6)
        ax.text(p + dx, im, etq, ha="center", va="center", fontsize=8.5,
                fontweight="bold", color="white", zorder=4)

    ax.set_xlim(0.5, 5.5)
    ax.set_ylim(0.5, 5.5)
    ax.set_xticks(range(1, 6))
    ax.set_yticks(range(1, 6))
    ax.set_xticklabels(["muy baja", "baja", "media", "alta", "muy alta"], fontsize=8.5)
    ax.set_yticklabels(["muy bajo", "bajo", "medio", "alto", "muy alto"], fontsize=8.5)
    ax.set_xlabel("probabilidad")
    ax.set_ylabel("impacto")
    for lado in ("top", "right", "left", "bottom"):
        ax.spines[lado].set_visible(False)
    ax.tick_params(length=0)

    leyenda = "\n".join(f"{e}  {t}" for e, _, _, t in RIESGOS)
    fig.text(1.005, 0.90, leyenda, fontsize=8.5, color=TINTA_2, va="top", ha="left",
             transform=ax.transAxes, linespacing=1.9)

    fig.suptitle("Matriz de riesgos", x=0.02, y=1.02, ha="left",
                 fontsize=12, fontweight="bold", color=TINTA)
    _guarda(fig, salida, "riesgos")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--salida", default="/eval/figuras/memoria")
    a = p.parse_args()
    os.makedirs(a.salida, exist_ok=True)
    figura_pipeline(a.salida)
    figura_arquitectura(a.salida)
    figura_gantt(a.salida)
    figura_riesgos(a.salida)


if __name__ == "__main__":
    main()
