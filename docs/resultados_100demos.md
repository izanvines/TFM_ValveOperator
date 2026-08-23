# ACT contra GR00T sobre 100 demostraciones

Primera comparación que significa algo. El ensayo del 19–20 de agosto usó 25 demos de una sola
disposición, sin agarre y con la misma condición inicial siempre: las dos políticas dieron 10/10
porque el problema era trivial. Esto es otra cosa.

**Fecha:** 2026-08-22 · **Dataset:** `valve_100` · **Evaluación:** 100 rollouts por política

---

## El dataset

| | |
|---|---|
| demostraciones | **100**, teleoperadas (sesiones 02 a 05, 25 cada una) |
| éxito al grabar | 100/100 |
| disposición | **50 frontal / 50 cenital**, sorteada en cada reset |
| jitter de posición | ±(4, 6, 3) cm |
| agarre | con el gatillo, mano cerrada el 46–57 % de los pasos |
| duración | 32.573 pasos = 11 min de demostración |
| fondo | oficina de Madrid (NuRec), aplicada por re-render |

`sesion_01` (25 demos empujando con la mano abierta) es validación de la tubería y **no entra
aquí**.

Que salga 50/50 exacto es casualidad afortunada, no diseño: las sesiones 02 y 03 se escoraron
hacia cenital (19/31) y las 04 y 05 hacia el otro lado (31/19). Se compensó solo.

## El entrenamiento

| | pasos | tiempo | pérdida |
|---|---|---|---|
| **GR00T N1.7** | 10.000 | 53 min (1 GPU) | 1,676 → **0,064** |
| **ACT** | 20.000 | 20 min | 7,18 → **0,169** |

Las dos pérdidas no son comparables entre sí —*flow matching* contra L1 sobre acciones— y por eso
van en paneles separados en la figura 1. Y ninguna de las dos demuestra nada por sí sola: son el
error de copiar al operador, no de abrir la válvula.

## Resultado

| política | éxito | IC 95 % | movió la válvula | ángulo medio |
|---|---|---|---|---|
| **GR00T** | **91 %** (91/100) | 84 – 95 % | 100 % | 176° |
| **ACT** | **83 %** (83/100) | 74 – 89 % | 100 % | 172° |

### La comparación está EMPAREJADA

Las dos evaluaciones corrieron con `--seed 42`, y comprobado sobre las poses iniciales grabadas:
**las 100 condiciones son idénticas**, con diferencia máxima de 0,000000 m. Cada política se
enfrentó exactamente a la misma válvula, en la misma posición, en el mismo orden.

Es una propiedad del diseño que conviene decir en la memoria: elimina la duda de si una de las
dos tuvo tiradas más fáciles por azar. Y obliga a usar el test emparejado, no el de dos
proporciones independientes.

|  | ACT acierta | ACT falla |
|---|---|---|
| **GR00T acierta** | 76 | **15** |
| **GR00T falla** | **7** | 2 |

Sólo los 22 casos discordantes llevan información: en 15 acierta GR00T y falla ACT, en 7 al revés.

```
McNemar exacto sobre 22 discordantes:  p = 0,134   ->  NO significativo
```

### La diferencia entre las dos NO es significativa

Ocho puntos con 100 tiradas **no permiten afirmar que GR00T sea mejor**, ni con el test
emparejado ni con el independiente (que daría p = 0,093, pero es el test equivocado aquí).
Escribir "GR00T supera a ACT" con estos datos sería una conclusión que el dato no sostiene.

Para resolverlo harían falta unos **140–160 rollouts por política** si las tasas reales son las
observadas. Es media hora más de máquina por política, y no requiere grabar nada.

Un detalle que sí es limpio: **sólo 2 de los 100 episodios los fallan las dos**, y los dos son
cenitales.

### Lo que SÍ es significativo: la disposición

| | frontal | cenital | Fisher |
|---|---|---|---|
| **GR00T** | 37/37 = **100 %** | 54/63 = **86 %** | p = 0,024 |
| **ACT** | 36/37 = **97 %** | 47/63 = **75 %** | p = 0,0045 |

**Las dos políticas son claramente peores con el volante hacia arriba**, y eso sí aguanta un test.
Es además consistente con todo lo demás que hemos medido de esa disposición:

- Es la que rompía el re-render en lazo abierto (8 de 14 cenitales dejaban de abrir la válvula
  contra 1 de 11 frontales), porque agarrar un radio desde arriba depende mucho más del contacto
  exacto que empujar de frente.
- Es la que hubo que acercar dos veces en las gafas antes de que resultara cómoda de operar.

O sea: **no es un artefacto de la política, es que la tarea es más difícil por ese lado.**

### El progreso parcial no discrimina

`revolute_joint_moved_rate` sale **100 % en las dos**. Nunca hay un rollout en el que el robot no
llegue a tocar la válvula: los fallos son siempre de *no completar media vuelta*, no de no
encontrarla. Se ve en la figura 3, donde la masa está pegada al umbral y la cola baja llega como
mucho a los 60°.

Eso hace que la métrica sea inútil **para esta comparación** —no separa nada—, pero es en sí un
resultado: las dos políticas han aprendido a aproximarse y agarrar, y lo que les falta es
completar el giro.

## Figuras

En `~/eval/figuras/`, en PNG a 300 ppp y PDF vectorial:

| | |
|---|---|
| `fig1_curvas_perdida` | convergencia de las dos, en paneles separados |
| `fig2_tasa_exito` | tasa de éxito con intervalos de Wilson |
| `fig3_distribucion_angulo` | hasta dónde llega el volante, con el umbral marcado |
| `fig4_exito_por_disposicion` | frontal contra cenital — **la figura con el resultado** |

Vídeos de 5 rollouts por política, tercera persona y con el fondo de oficina, en
`~/eval/videos/politicas/{gr00t,act}/`.

## Qué hacer con esto

1. **Subir a ~140 rollouts por política** para poder afirmar o descartar la diferencia entre las
   dos. Media hora de máquina, cero grabación.
2. **Grabar más cenitales.** El dataset está 50/50 y el resultado dice que esa mitad es la
   difícil. Un reparto 40/60 a favor de la cenital en las sesiones que quedan es defendible y
   ataca directamente el punto débil.
3. **Curva de eficiencia de datos** (25, 50, 100 demos). Es donde el VLA debería separarse del
   método clásico, y las sesiones ya están en ficheros separados, así que no hay que grabar nada.

## Aviso al leer la tasa de éxito

Las demostraciones acaban entre 180° y 220°, muy justas sobre el umbral, **porque el episodio
termina en cuanto se detecta el éxito y el operador nunca sigue girando**. La política copia eso:
aprende a parar justo al cruzar. Parte de los fallos son casi-éxitos por esa razón y no por no
saber hacer la tarea. Subir `--num_success_steps` en las sesiones que queden daría margen y
probablemente subiría las dos tasas.
