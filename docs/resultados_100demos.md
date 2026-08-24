# ACT contra GR00T sobre 100 demostraciones

Primera comparación que significa algo. El ensayo del 19–20 de agosto usó 25 demos de una sola
disposición, sin agarre y con la misma condición inicial siempre: las dos políticas dieron 10/10
porque el problema era trivial. Esto es otra cosa.

**Fecha:** 2026-08-22, ampliado el 2026-08-24 · **Dataset:** `valve_100` ·
**Evaluación:** **200 rollouts por política**

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

| | parámetros | pasos | tiempo | pérdida |
|---|---|---|---|---|
| **GR00T N1.7** | 3,14 B | 10.000 | 53 min (1 GPU) | 1,676 → **0,064** |
| **ACT** | 51,7 M | 20.000 | 20 min | 7,18 → **0,169** |

Las dos pérdidas no son comparables entre sí —*flow matching* contra L1 sobre acciones— y por eso
van en paneles separados en la figura 1. Y ninguna de las dos demuestra nada por sí sola: son el
error de copiar al operador, no de abrir la válvula.

El coste sí es comparable, y conviene decirlo: GR00T es **61× más grande** (12,6 GB de pesos
contra 198 MB) y 2,6× más lento de entrenar.

## Resultado

Dos tandas de 100 rollouts por política, con semillas distintas (42 y 7), agrupadas:

| política | n | éxito | IC 95 % | movió la válvula | ángulo medio |
|---|---|---|---|---|---|
| **GR00T** | 200 | **92 %** (185/200) | 88 – 95 % | 100 % | 177° |
| **ACT** | 200 | **86 %** (172/200) | 81 – 90 % | 100 % | 173° |

Por tanda: GR00T 91 y 94, ACT 83 y 89. El orden se mantiene en las dos.

### La comparación está EMPAREJADA

Dentro de cada tanda las dos evaluaciones corrieron con la misma semilla, y comprobado sobre las
poses iniciales grabadas: **las condiciones son idénticas, con diferencia máxima de
0,000000000 m**. Cada política se enfrentó exactamente a la misma válvula, en la misma posición,
en el mismo orden. Las dos tandas entre sí sí son sorteos distintos, que es lo que permite
agruparlas.

Es una propiedad del diseño que conviene decir en la memoria: elimina la duda de si una de las
dos tuvo tiradas más fáciles por azar. Y obliga a usar el test emparejado, no el de dos
proporciones independientes.

|  | ACT acierta | ACT falla |
|---|---|---|
| **GR00T acierta** | 160 | **25** |
| **GR00T falla** | **12** | 3 |

Sólo los 37 casos discordantes llevan información: en 25 acierta GR00T y falla ACT, en 12 al
revés.

```
McNemar exacto sobre 37 discordantes:  p = 0,047
```

### Cruza el 0,05, pero por un episodio — no lo escribas como un resultado firme

El valor p queda justo por debajo del umbral convencional, y es **frágil**:

| si hubiera salido | p |
|---|---|
| **25 – 12 (lo observado)** | **0,047** |
| 24 – 13 (un fallo más de GR00T) | 0,099 |
| 25 – 13 (un acierto más de ACT) | 0,073 |

Un solo rollout distinto duplica el valor p. La redacción defendible es **«GR00T queda por encima
de forma consistente en las dos tandas y la diferencia roza la significación (p = 0,047), sin
llegar a ser robusta»**, no «GR00T es significativamente mejor que ACT». La segunda frase se cae
en cuanto alguien pregunta qué pasa con otra semilla.

Con 100 rollouts la misma comparación daba p = 0,134. Doblar la muestra movió el resultado de
«no se puede afirmar nada» a «está en el límite», que es exactamente lo que se espera de una
diferencia real pero pequeña.

### Lo que SÍ es significativo, y con mucho margen: la disposición

| | frontal | cenital | Fisher |
|---|---|---|---|
| **GR00T** | 84/84 = **100 %** | 101/116 = **87 %** | **p = 0,00021** |
| **ACT** | 83/84 = **99 %** | 89/116 = **77 %** | **p = 0,0000018** |

**Las dos políticas son claramente peores con el volante hacia arriba**, y eso aguanta cualquier
test. Es además consistente con todo lo demás que hemos medido de esa disposición:

- Es la que rompía el re-render en lazo abierto (8 de 14 cenitales dejaban de abrir la válvula
  contra 1 de 11 frontales), porque agarrar un radio desde arriba depende mucho más del contacto
  exacto que empujar de frente.
- Es la que hubo que acercar dos veces en las gafas antes de que resultara cómoda de operar.

O sea: **no es un artefacto de la política, es que la tarea es más difícil por ese lado.**

### Y de ahí sale toda la diferencia entre políticas

De los **37 casos discordantes, 36 son cenitales**. En frontal las dos están saturadas —84/84
contra 83/84, un único caso discordante—, así que no hay margen donde separarse.

```
McNemar sólo frontal:  1 – 0    p = 1,0
McNemar sólo cenital: 24 – 12   p = 0,065
```

La lectura correcta no es «GR00T es mejor en general», sino **«GR00T aguanta algo mejor la
disposición difícil»** — y ni siquiera eso alcanza significación por sí solo al restringir la
muestra.

### El progreso parcial no discrimina

`revolute_joint_moved_rate` sale **100 % en las dos**, en las 400 tiradas. Nunca hay un rollout en
el que el robot no llegue a tocar la válvula: los fallos son siempre de *no completar media
vuelta*, no de no encontrarla. Se ve en la figura 3, donde la masa está pegada al umbral y la cola
baja llega como mucho a los 60°.

Eso hace que la métrica sea inútil **para esta comparación** —no separa nada—, pero es en sí un
resultado: las dos políticas han aprendido a aproximarse y agarrar, y lo que les falta es
completar el giro.

## Figuras

En `~/eval/figuras/`, en PNG a 300 ppp y PDF vectorial, regeneradas sobre las 200 tiradas:

| | |
|---|---|
| `fig1_curvas_perdida` | convergencia de las dos, en paneles separados |
| `fig2_tasa_exito` | tasa de éxito con intervalos de Wilson |
| `fig3_distribucion_angulo` | hasta dónde llega el volante, con el umbral marcado |
| `fig4_exito_por_disposicion` | frontal contra cenital — **la figura con el resultado** |

Vídeos de 5 rollouts por política, tercera persona y con el fondo de oficina, en
`~/eval/videos/politicas/{gr00t,act}/`.

## Qué hacer con esto

1. **Grabar más cenitales.** Es la conclusión fuerte de todo el experimento: el dataset está
   50/50 y esa mitad concentra el 97 % de los fallos. Un reparto 40/60 a favor de la cenital en
   las sesiones que quedan ataca directamente el punto débil, y está respaldado por dos tests con
   p < 0,001.
2. **Curva de eficiencia de datos** (25, 50, 100 demos). Es donde el VLA debería separarse del
   método clásico, y las sesiones ya están en ficheros separados, así que no hay que grabar nada.
   Si GR00T se despega con 25 demos y empata con 100, ése es el argumento real a favor del modelo
   fundacional — mucho más fuerte que 6 puntos al límite de la significación.
3. **Latencia de inferencia** por política, que es el otro eje donde 3,14 B contra 51,7 M tiene
   que notarse y todavía no está medido.

No merece la pena seguir subiendo rollouts para exprimir el p de la comparación entre políticas:
la diferencia real es pequeña, y con 200 emparejados ya se sabe que hace falta muchísima más
muestra para asentarla. El esfuerzo rinde más en los tres puntos de arriba.

## Aviso al leer la tasa de éxito

Las demostraciones acaban entre 180° y 220°, muy justas sobre el umbral, **porque el episodio
termina en cuanto se detecta el éxito y el operador nunca sigue girando**. La política copia eso:
aprende a parar justo al cruzar. Parte de los fallos son casi-éxitos por esa razón y no por no
saber hacer la tarea. Subir `--num_success_steps` en las sesiones que queden daría margen y
probablemente subiría las dos tasas.
