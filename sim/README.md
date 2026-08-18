# `sim/` — el entorno de simulación, versionado

Aquí está todo lo que define la tarea `g1_valve`. **La simulación no se ejecuta desde este
directorio**: corre desde un checkout de [`isaac-sim/IsaacLab-Arena`](https://github.com/isaac-sim/IsaacLab-Arena)
(rama `release/0.2.1`) en `~/TFM/IsaacLab-Arena`, montado dentro del contenedor en
`/workspaces/isaaclab_arena`. Este directorio es la copia versionada de las piezas propias, para
que el TFM sea reproducible sin depender de una máquina concreta.

Los comandos de lanzamiento están en [`../LAUNCH.md`](../LAUNCH.md).

## Qué hay

```
sim/
├── environments/g1_valve_environment.py   la tarea: escena, poses, robot, éxito
├── assets/
│   ├── valve_rig.usdz                     la válvula CAD (de jescobars, ver PROVENANCE)
│   ├── valve_rig_arena.usda               capa propia sobre el .usdz -- lee su `doc`
│   └── valve_rig_PROVENANCE.md            de dónde sale el CAD y cómo se verificó
├── patches/                               cambios sobre ficheros de upstream
├── scripts/                               utilidades de medida y diagnóstico
└── sync.sh                                mueve todo esto al checkout vivo, y al revés
```

### `environments/g1_valve_environment.py`

Fichero nuevo, no existe en upstream. Registra la tarea bajo el nombre `g1_valve`
(el registro en sí va en `isaaclab_arena_environments/cli.py`, que es un parche).

Define: escena diáfana (plano de suelo + dome light, sin USD de fondo), la válvula, el G1 con el
embodiment `g1_wbc_agile_pink`, y el criterio de éxito vía `OpenDoorTask` (apertura > 0.5).

**Todas las poses del fichero están medidas, no estimadas** — con
`scripts/measure_valve_rig.py`. Los comentarios del propio fichero explican cada número y qué
pasa si lo cambias.

### `assets/valve_rig_arena.usda`

Capa propia que referencia el `.usdz` de Javi sin modificarlo. Hace **tres** cosas, todas
documentadas en el `doc` del propio fichero:

1. **Reescala el recorrido** de 539.7°–2879.8° (6.5 vueltas, fiel a una válvula de compuerta
   real) a 0°–360°. Arena normaliza la apertura sobre los *límites* del joint y el éxito es
   apertura > 0.5, así que con los límites originales cada demostración exigiría **3.25 vueltas
   completas** en un episodio: imposible por teleoperación, todos los episodios morirían por
   timeout y **nunca se escribiría nada en el HDF5**.
2. **Mantiene los materiales enganchados.** Las mallas apuntan a `/World/Looks/OmniPBR` y
   `/World/PhysicsMaterial`, que quedan fuera del subárbol referenciado; sin traérselos se pierde
   en silencio el material físico (`staticFriction 1.2 / dynamicFriction 1.0`), que es
   justo la fricción que los dedos necesitan para no resbalar en un radio.
3. **Quita el freno del volante.** El rig venía con `drive:angular:physics:damping = 100` y
   velocidad objetivo 0: un freno viscoso que exige ~1000 N·m para girar a 10 °/s, cuando la mano
   del G1 da un par de N·m. Bajado a `0.01`. **Es el número a retocar** si quieres una válvula más
   dura (súbelo hacia 0.05–0.1).

### `patches/`

Ficheros que sí existen en upstream y solo cambian unas líneas. Se guardan como `.patch` en vez
de como copia entera para que se vea exactamente qué se tocó, y para poder rebasar sobre una
versión nueva de Arena.

| parche | qué cambia |
|---|---|
| `object_library.patch` | la clase `Valve`: `usd_path`, `openable_joint_name = "RevoluteJoint"`, umbral |
| `cli.patch` | registra `g1_valve` como entorno invocable |
| `g1_pink_locomanipulation_pipeline.patch` | lee `ARENA_STATIC_BASE` para congelar los canales de locomoción |
| `teleop.patch` | hace el DLSS opcional vía `ARENA_XR_ANTIALIASING` (si no, fuerza `RealTimePathTracing` y sobreexpone) |
| `record_demos.patch` | lo mismo para la ruta de grabación |
| `background_library.patch` | fondo Gaussian-Splatting (fuera del alcance del TFM, pero el parche existe) |
| `isaaclab_submodule.patch` | `xr_anchor_manager.py`: crea el prim de anclaje XR con USD crudo cuando `SingleXFormPrim` falla. Sin esto quedas anclado a la altura de la pelvis dentro del casco |

Un `git checkout` o un `git submodule update` en el checkout vivo **borra estos cambios sin
avisar**. Por eso están aquí.

### `scripts/`

Van montados en el contenedor como `/eval/arena_extras/` (el mount `~/eval` → `/eval`).

| script | para qué |
|---|---|
| `stream_valve.py` | levanta `g1_valve` y lo deja corriendo para verlo por WebRTC. Modo A de `LAUNCH.md` |
| `measure_valve_rig.py` | mide dónde acaban pelvis y muñecas, y dónde está la rueda. `--repeats N` para la dispersión |
| `capture_viewport.py` | saca un PNG del viewport. Sirve para descartar el render antes de culpar a la red |
| `test_valve_torque.py` | intenta girar el volante con un par conocido. **Ojo: el camino de fuerzas externas es un no-op en este backend**, el test da 0.00° incluso con 50 N·m |
| `inspect_valve_physics.py` | vuelca los parámetros de física del rig ya compuestos |
| `hold_pose_policy.py` | acción de "quedarse de pie" estable. Documenta dos trampas de convención |
| `record_robotcam_video.py` | graba la cámara del robot a PNGs para montar un vídeo |
| `launch_record_valve.sh` | wrapper de grabación con guardia de red para la API de Lightwheel |

**No uses la acción de ceros para medir nada**: el índice `[19]` es `base_height_cmd` y un cero
pide pelvis a 0 m — el robot se sienta y cualquier medida describe a un robot tumbado.

## Mantener esto y el checkout vivo sincronizados

```bash
./sync.sh diff    # ¿han divergido?
./sync.sh pull    # traer del checkout vivo a este repo
./sync.sh push    # instalar este repo en el checkout vivo
```

`push` copia los ficheros nuevos pero **no aplica los parches**: re-aplicar un parche ya aplicado
deja el fichero corrupto sin avisar. Te imprime los comandos `git apply` para que los lances tú.

## Lo que NO está aquí, a propósito

- **El USD del G1.** Sale de Isaac Nucleus:
  `Samples/Groot/Robots/g1_29dof_with_hand_rev_1_0.usd`. Es el modelo **`with_hand`** (7 juntas
  actuadas por mano), que es exactamente por lo que el espacio de juntas de GR00T son 43 DoF:
  29 del cuerpo + 7 + 7. No sustituir por la variante `with_inspire`: rompería en cascada las
  ganancias de `G1_AGILE_CFG`, el orden de juntas que espera la ONNX de AGILE (pérdida de
  equilibrio), el retargeter, la config de Pink IK y las 43 DoF de la conversión a GR00T.
- **Los datasets y los checkpoints.** Viven en `~/datasets` y `~/models`.
- **Isaac Lab Arena entero.** Es un repo de terceros; aquí solo va lo propio.
