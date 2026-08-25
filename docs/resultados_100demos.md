# ACT contra GR00T sobre 100 demostraciones

Primera comparación que significa algo. El ensayo del 19–20 de agosto usó 25 demos de una sola
disposición, sin agarre y con la misma condición inicial siempre: las dos políticas dieron 10/10
porque el problema era trivial. Esto es otra cosa.

**Fecha:** 2026-08-22, ampliado el 2026-08-24 y el 2026-08-25 · **Dataset:** `valve_100` ·
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

## Eficiencia en datos: 25, 50 y 100 demostraciones

Añadido el 2026-08-25. Se reentrenaron las dos políticas sobre subconjuntos **estratificados**
del mismo dataset y se evaluaron las seis con las **mismas** 100 condiciones iniciales
(semilla 42), así que lo único que cambia entre puntos es la cantidad de datos.

| | 25 demos | 50 demos | 100 demos |
|---|---|---|---|
| **GR00T** | **93 %** (86–97) | 91 % (84–95) | 91 % (84–95) |
| **ACT** | 84 % (76–90) | 91 % (84–95) | 83 % (75–89) |

Estratificados quiere decir 12F/13C y 25F/25C, sorteados con semilla fija y **anidados**. No es
un detalle: las sesiones 02 y 03 se escoraron a cenital (19F/31C), así que coger «las primeras
50» habría mezclado *menos datos* con *más cenitales* y la curva habría caído por el motivo
equivocado — la disposición, no la cantidad.

### La curva es plana, y eso responde a la pregunta

La hipótesis era la que justifica usar un modelo fundacional: que GR00T se despegara con pocas
demostraciones y ACT necesitara más. **No ocurre.** Ninguna diferencia dentro de una misma
política es significativa:

```
GR00T  @25 vs @100   7 / 5    p = 0,77
GR00T  @50 vs @100   6 / 6    p = 1,00
ACT    @25 vs @100  13 / 12   p = 1,00
ACT    @50 vs @100  15 / 7    p = 0,13     (cenital solo: p = 0,12)
```

Y entre políticas, en cada punto: p = 0,078 con 25, p = 1,00 con 50, p = 0,134 con 100. En el
punto de 50 empatan exactamente (91 % las dos, 6 discordantes en cada sentido).

Tres lecturas, en orden de solidez:

1. **Con esta tarea, 25 demostraciones ya saturan lo que el tamaño del dataset puede dar.**
   Cuadruplicar los datos no mueve la tasa de éxito de ninguna de las dos. Es un resultado
   negativo, y es el más útil del experimento: dice que el 8–15 % de fallo que queda **no es un
   problema de cantidad de datos**, así que grabar hacia 400 demostraciones con el mismo reparto
   no lo habría arreglado.
2. **Lo que sí importa es la composición.** El panel derecho de la figura 8 lo enseña: en frontal
   GR00T hace 37/37 en los tres puntos y ACT 34–36/37, o sea saturado desde 25 demos; toda la
   variación vive en cenital. Refuerza la recomendación de grabar 40/60 a favor de la cenital,
   que ahora se apoya en dos argumentos independientes.
3. **GR00T aguanta mejor con pocos datos, pero no se puede afirmar.** 93 % contra 84 % con 25
   demos es la mayor separación de los tres puntos y va en la dirección esperada — pero p = 0,078
   y con 50 demos el orden se invierte al empate. Es una tendencia, no un hallazgo.

**Aviso obligatorio al leer esta figura:** cada punto es **un único entrenamiento**, así que la
variación entre puntos mezcla el efecto de los datos con la varianza de semilla del
entrenamiento. El sube-y-baja de ACT (84 → 91 → 83) es casi con seguridad ruido de entrenamiento,
no una relación real con el tamaño del dataset; para separarlas harían falta varias semillas por
punto, que a estas alturas del calendario no cabían. Escrito así en el pie de la figura.

## Latencia de inferencia

El otro eje donde 3,14 B contra 51,7 M tiene que notarse. Medida **en lazo cerrado dentro del
simulador** con `train/scripts/latencia_wrapper.py`, no con un tensor sintético: 10 tiradas por
política, cronometrando `get_action` en el servidor con `torch.cuda.synchronize()` a los dos
lados.

| | mediana | p95 | máximo | 1.ª llamada | margen |
|---|---|---|---|---|---|
| **GR00T N1.7** | **53 ms** | 58 ms | 133 ms | 485 ms | ×15 |
| **ACT** | **5,2 ms** | 5,5 ms | 6,8 ms | 198 ms | ×154 |

El presupuesto son **800 ms**: el cliente pide un chunk cada 40 pasos y el entorno corre a 50 Hz.
**Ninguna de las 226 medidas se sale**, ni el máximo de GR00T. La primera llamada de cada política
se descarta porque es compilación de kernels.

Conclusión práctica: los **61× de diferencia en parámetros cuestan 10× en latencia**, y aun así
las dos caben con muchísima holgura. La latencia **no es un argumento contra el VLA en esta
tarea**. Dicho lo cual, esto se mide con el servidor solo en una RTX PRO 6000 de 96 GB: en un
robot real, con más carga en la misma GPU y un enlace de red por medio, los 53 ms son el suelo,
no el techo.

## Figuras

Versionadas en **[`docs/figuras/`](figuras/)**, en PDF vectorial y PNG a 300 ppp, listas para
`\includegraphics`. Se generan en `~/eval/figuras/` con tres guiones:

| figura | guion | qué enseña |
|---|---|---|
| `fig1_curvas_perdida` | `figuras_resultados.py` | convergencia de las dos, en paneles separados |
| `fig2_tasa_exito` | ” | tasa de éxito con intervalos de Wilson |
| `fig3_distribucion_angulo` | ” | hasta dónde llega el volante, con el umbral marcado |
| `fig4_exito_por_disposicion` | ” | frontal contra cenital — **la figura con el resultado** |
| `fig5_reparto_disposiciones` | `figuras_dataset.py` | cómo se repartió el sorteo por sesión |
| `fig6_duracion_episodios` | ” | duración de las 100 demostraciones |
| `fig7_std_espacio_accion` | ” | **las 6 dimensiones de acción con std = 0** |
| `fig8_curva_eficiencia` | `figuras_eficiencia.py` | 25/50/100 demos, total y solo cenital |
| `fig9_latencia` | ” | ms por chunk contra el presupuesto de 800 ms |

Vídeos de 5 rollouts por política, tercera persona y con el fondo de oficina, en
`~/eval/videos/politicas/{gr00t,act}/`.

## Qué hacer con esto

De los tres puntos que había aquí el 22 de agosto, **dos están hechos** y su respuesta está arriba:
la curva de eficiencia sale plana y la latencia no descarta a ninguna de las dos. Queda uno, y ha
salido reforzado:

1. **Grabar más cenitales.** Es la conclusión fuerte de todo el experimento, y ahora se apoya en
   dos argumentos independientes: el dataset está 50/50 y esa mitad concentra el 97 % de los
   fallos (dos tests con p < 0,001), y además **la curva de eficiencia demuestra que más datos
   del mismo tipo no arreglan nada**. Un reparto 40/60 a favor de la cenital en lo que quede de
   grabación ataca lo único que sí está limitando el resultado.
2. **Si sobrara máquina, varias semillas por punto antes que más rollouts.** La curva está
   limitada por tener un solo entrenamiento por punto, no por el número de tiradas de evaluación.
3. **Congelar las 6 dimensiones muertas** (`[16:19]` navegación y `[20:22]` torso) sigue
   pendiente. A una semana del cierre no se toca: introduciría una variable nueva en un
   experimento que ya está cerrado, y al menos ahora está documentado en la figura 7.

No merece la pena seguir subiendo rollouts para exprimir el p de la comparación entre políticas:
la diferencia real es pequeña, y con 200 emparejados ya se sabe que hace falta muchísima más
muestra para asentarla.

## Aviso al leer la tasa de éxito

Las demostraciones acaban entre 180° y 220°, muy justas sobre el umbral, **porque el episodio
termina en cuanto se detecta el éxito y el operador nunca sigue girando**. La política copia eso:
aprende a parar justo al cruzar. Parte de los fallos son casi-éxitos por esa razón y no por no
saber hacer la tarea. Subir `--num_success_steps` en las sesiones que queden daría margen y
probablemente subiría las dos tasas.
