# `train/` — del dataset a la política, versionado

Espejo de [`sim/`](../sim/README.md) para la mitad de aprendizaje. Los comandos están en
[`../TRAIN.md`](../TRAIN.md); aquí sólo qué es cada fichero y por qué existe.

Nada de esto corre desde aquí: los scripts se lanzan con `PYTHONPATH` apuntando a este directorio,
desde el venv que toque. **Es deliberado** — los servidores de política no entran en el checkout de
Arena para que un `git submodule update` no se los lleve por delante.

```
train/
├── config/g1_valve_gr00t_closedloop_config.yaml   qué checkpoint sirve el servidor de GR00T
├── scripts/
│   ├── fix_lerobot_meta.py            corrige total_chunks y splits del info.json
│   ├── verify_lerobot_dataset.py      audita el dataset convertido contra el HDF5 original
│   ├── compare_checkpoint_weights.py  ¿ha entrenado de verdad, o reanudo y guardo lo de antes?
│   ├── make_lerobot_act_view.py       vista del dataset que LeRobot 0.3.3 carga tal cual
│   ├── arena_replay_server.py         sirve acciones grabadas: la cota superior del pipeline
│   └── act_remote_policy.py           sirve una política ACT por la misma pila ZMQ
└── README.md
```

## Los tres entornos

| dónde | qué corre |
|---|---|
| contenedor (py3.12) | conversión, `verify_lerobot_dataset.py`, `policy_runner.py` como cliente |
| `~/TFM/isaac-gr00t-standalone/.venv` (py3.10) | estadísticas, fine-tune, `compare_checkpoint_weights.py`, `arena_replay_server.py`, servidor de GR00T |
| `~/venvs/lerobot-act` (py3.10) | `make_lerobot_act_view.py`, entrenamiento de ACT, `act_remote_policy.py` |

`fix_lerobot_meta.py` no depende de nada: vale cualquier Python 3.

## Por qué los servidores son tres ficheros con la misma forma

`arena_replay_server.py`, `act_remote_policy.py` y el `Gr00tRemoteServerSidePolicy` de Arena
implementan el **mismo** `ServerSidePolicy`: mismo protocolo ZMQ, mismas claves de observación
(`camera_obs.robot_head_cam_rgb` uint8 `(N,480,640,3)` y `policy.robot_joint_pos` float32 `(N,43)`),
misma acción de 50 dimensiones `[43 juntas | 3 navegación | 1 altura | 3 torso]`.

Esa simetría es el argumento de la comparación del TFM: el comando del cliente es byte a byte el
mismo para los tres y lo único que cambia es quién escucha en el puerto. Cualquier diferencia en
`success_rate` es de la política, no del montaje.

El replay es la pieza que hace falta primero: si reproducir las acciones grabadas no gira la
válvula, ninguna política entrenada sobre esa columna lo hará, y eso hay que saberlo antes de grabar
375 demostraciones más.

## Dos trampas que los tres comparten

- **El orden de juntas.** El dataset guarda estado y acción en orden de la *política* (grupos GR00T:
  piernas, cintura, brazo+mano izquierda, brazo+mano derecha); el simulador usa el suyo. Son
  permutaciones puras de los mismos 43 nombres, definidos en `43dof_joint_space.yaml` y
  `gr00t_43dof_joint_space.yaml`. Los tres scripts la construyen al arrancar y comprueban que sea
  biyectiva.
- **`base_height_cmd` es el índice 46.** Rellenar la cola de siete dimensiones con ceros es lo obvio
  y deja al robot sentado en el suelo, porque un cero pide pelvis a 0 m. El valor sale de
  `meta/stats.json` (0,72 en esta sesión), no se escribe a mano.
