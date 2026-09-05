# Aprendizaje por imitación en la apertura de válvulas con un humanoide Unitree G1

**Modelos visión-lenguaje-acción frente a políticas clásicas.** Trabajo de Fin de Máster, Máster en
Robótica e Inteligencia Artificial, Universidad de León, 2026. Autor: Izan Viñes Castaño. Tutor:
Francisco Javier Rodríguez Lera.

Repositorio: <https://github.com/izanvines/TFM_ValveOperator>. Es el entregable del TFM: la tarea de simulación, el *pipeline* completo de
aprendizaje por imitación —teleoperación en realidad mixta, grabación, fondo fotorrealista,
conversión, entrenamiento y evaluación—, los guiones que ejecutaron los experimentos, las figuras y
la memoria. Los conjuntos de datos y los puntos de control no están (ver abajo); todo lo demás sí.

## El trabajo en un párrafo

Se construye un banco de comparación sobre Isaac Lab Arena en el que un Unitree G1 abre una válvula
de volante procedente de un modelo CAD real, en dos disposiciones (frontal y cenital) sorteadas en
cada reinicio. Se graban **100 demostraciones** teleoperadas con unas PICO 4 Ultra, se les aplica
después un fondo fotorrealista de una oficina real reconstruida por *Gaussian Splatting*, y el mismo
conjunto de datos alimenta dos políticas: el ajuste fino del modelo fundacional **GR00T N1.7**
(3140 M de parámetros) y una **ACT** entrenada desde cero (51,7 M). Ambas se evalúan con el mismo
cliente, en el mismo simulador y sobre condiciones iniciales idénticas.

| | GR00T N1.7 | ACT |
|---|---|---|
| Éxito sobre 200 tiradas emparejadas | **92 %** (185/200) | **86 %** (172/200) |
| Disposición frontal / cenital | 84/84 · 101/116 | 83/84 · 89/116 |
| McNemar exacto (37 discordantes) | *p* = 0,047 — frágil: un episodio de margen | |
| Éxito con 25 / 50 / 100 demostraciones | 93 / 91 / 91 % | 84 / 91 / 83 % |
| Latencia por bloque de 40 acciones (mediana) | 53 ms | 5,2 ms |

La lectura defendible: el modelo fundacional va por delante por un margen pequeño y difícil de
acreditar; la variable que domina el resultado es la disposición de la válvula (*p* < 0,001 para
las dos políticas), y la curva de eficiencia en datos es plana, así que grabar más demostraciones
del mismo tipo no arregla el 8–15 % de fallo restante.

## Organización

| Ruta | Contenido |
|---|---|
| [`LAUNCH.md`](LAUNCH.md) | Simular, teleoperar, grabar y aplicar el fondo: comandos verificados y tabla de fallos |
| [`TRAIN.md`](TRAIN.md) | Del HDF5 grabado a la política evaluada, para GR00T y para ACT |
| [`CLAUDE.md`](CLAUDE.md) | Cuaderno de bitácora: estado, decisiones con fecha, trampas conocidas |
| [`sim/`](sim/README.md) | La tarea `g1_valve`: entorno, válvula, parches sobre Arena, guiones de medida y ejecución |
| [`train/`](train/README.md) | Reproducción con fondo, verificación de datos, servidores de política, subconjuntos, latencia, figuras |
| [`reconstruction/`](reconstruction/README.md) | La reconstrucción de la oficina con fVDB y COLMAP |
| [`docs/TFM_ValveOperator.pdf`](docs/TFM_ValveOperator.pdf) | La memoria del TFM |
| [`docs/figuras/`](docs/figuras/) | Las figuras de resultados, en PDF y PNG |
| [`docs/resultados_100demos.md`](docs/resultados_100demos.md) | El análisis completo de los resultados |
| [`docs/notas/`](docs/notas/README.md) | Las notas de trabajo fechadas, de julio a agosto |
| [`videos/`](videos/) | Cada política abriendo la válvula |

## Reproducir

1. **Simulación**: un *checkout* de [Isaac Lab Arena](https://github.com/isaac-sim/IsaacLab-Arena)
   en el commit exacto que indica `sim/README.md` (§ Versiones exactas), con los parches de
   `sim/patches/` y los ficheros de `sim/` (`sim/sync.sh push` los copia y dice cómo aplicar los
   parches). Todo corre dentro del contenedor de Isaac Sim 6.0.
2. **Grabar**: `LAUNCH.md`, modos B y C. Hace falta un visor PICO 4 Ultra y CloudXR.
3. **Fondo**: `LAUNCH.md`, modo D, con el activo de `reconstruction/`.
4. **Entrenar y evaluar**: `TRAIN.md`. GR00T y ACT viven en dos entornos de Python distintos del
   simulador; la cadena completa de las 100 demostraciones está en `sim/scripts/pipeline_valve_100.sh`,
   `train_valve_100.sh`, `eval_valve_100.sh` y `noche_final.sh`, reanudables.

Hardware con el que se hizo: una estación con dos RTX PRO 6000 Blackwell (96 GB), Ubuntu 24.04.

## Lo que no está en el repositorio

Los conjuntos de datos (17,5 GB el HDF5 de 100 demostraciones; 100 MB en formato LeRobot), los
puntos de control (12 GB GR00T, 198 MB ACT), los ficheros de resultados de las tiradas y el activo
de la oficina (253 MB). Todos se regeneran con los guiones de aquí a partir de las demostraciones
grabadas.

## Créditos

El modelo CAD de la válvula es de un compañero de laboratorio (`sim/assets/valve_rig_PROVENANCE.md`).
El trabajo se apoya en Isaac Lab Arena, Isaac-GR00T y LeRobot; la reconstrucción, en fVDB y COLMAP.
Se empleó un asistente de programación con IA, con el alcance que declara la memoria.

## Cita

```bibtex
@mastersthesis{vines2026valvula,
  title  = {Aprendizaje por imitación en la apertura de válvulas con un humanoide Unitree G1:
            modelos visión-lenguaje-acción frente a políticas clásicas},
  author = {Viñes Castaño, Izan},
  school = {Universidad de León},
  year   = {2026}
}
```

## Licencia

Apache License 2.0 — ver [`LICENSE`](LICENSE). Copyright 2026 Izan Viñes Castaño. Los marcos de
terceros sobre los que se apoya (Isaac Lab Arena, Isaac-GR00T, LeRobot, fVDB, COLMAP) conservan sus
propias licencias; los parches de `sim/patches/` modifican ficheros de Isaac Lab Arena, que es
Apache-2.0. Las direcciones de red de la estación de trabajo se han sustituido por marcadores
(`<IP_ESTACION>`, `<SUBRED_LAN>`, `<ESTACION>`) en la documentación y los guiones.
