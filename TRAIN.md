# Del HDF5 grabado a una política evaluada

Hermano de [`LAUNCH.md`](LAUNCH.md), que cubre simular y grabar. Aquí empieza donde aquél acaba:
un HDF5 de sesión y termina con `success_rate` en el mismo simulador, para GR00T y para ACT.

Verificado de punta a punta el **2026-08-19** con `sesion_01.hdf5` (25 demostraciones). Resultados
en [`docs/ensayo_2026-08.md`](docs/ensayo_2026-08.md).

---

## 0. Lo que más confunde: hay tres intérpretes

Ninguno de los tres puede hacer el trabajo de los otros, y equivocarse de terminal es el error más
frecuente de este pipeline. **Cada comando de abajo dice dónde corre.**

| entorno | Python | qué corre ahí | por qué no vale otro |
|---|---|---|---|
| contenedor `isaaclab_arena-latest` | 3.12 | simulación, grabación, conversión, `policy_runner.py` (**cliente**) | Isaac Sim no arranca en el host |
| `~/TFM/isaac-gr00t-standalone/.venv` | 3.10 | estadísticas, fine-tune y **servidor** de GR00T | el submódulo que Arena fija sólo trae `Gr00tN1d6` y sus dependencias no están instaladas en el intérprete de Isaac Sim (`import tyro` falla) |
| `~/venvs/lerobot-act` | 3.10 | entrenamiento y **servidor** de ACT | LeRobot fija su propio torch; instalarlo en Isaac Sim rompe el simulador que necesitas para evaluar |

Los tres comparten ficheros (`~/datasets`, `~/models`, `~/eval` están montados en el contenedor) y
comparten `127.0.0.1`, porque el contenedor va en `network_mode: host`. De ahí que las políticas se
sirvan por ZMQ desde el host y el simulador sea sólo cliente.

**Esa arquitectura no es un apaño: es el argumento de la comparación.** El comando del cliente es
byte a byte el mismo para el replay, para GR00T y para ACT. Lo único que cambia es quién escucha en
el puerto.

---

## 1. Convertir el HDF5 a GR00T-LeRobot

*(contenedor)*

Apunta el YAML a la sesión — es el único campo que cambia entre sesiones:

```bash
sed -i 's|^hdf5_name:.*|hdf5_name: "sesion_01.hdf5"|' \
  ~/TFM/IsaacLab-Arena/isaaclab_arena_gr00t/lerobot/config/g1_valve_config.yaml
```

```bash
docker exec isaaclab_arena-latest rm -rf /datasets/isaaclab_arena/g1_valve/sesion_01
docker exec isaaclab_arena-latest bash -c \
 'cd /workspaces/isaaclab_arena && unset DISPLAY && export HOME=/home/ivines && \
  /isaac-sim/python.sh -u isaaclab_arena_gr00t/lerobot/convert_hdf5_to_lerobot.py \
    --yaml_file isaaclab_arena_gr00t/lerobot/config/g1_valve_config.yaml' \
  </dev/null 2>&1 | tee ~/eval/g1_valve_dryrun/convert_sesion_01.log
docker exec isaaclab_arena-latest chown -R $(id -u):$(id -g) /datasets/isaaclab_arena/g1_valve/sesion_01
```

Cuatro cosas que no son opcionales:

- **`rm -rf` del destino antes.** Si el directorio existe, `dataset_config.py:154` llama a un
  `input()` pelado. En un `docker exec` no interactivo eso cuelga.
- **`</dev/null`.** Convierte ese `input()` en un `EOFError` inmediato en vez de un cuelgue, si
  alguna vez se llega a él.
- **`chown` después.** Lo escribe root desde el contenedor, y GR00T necesita escribir estadísticas
  *dentro* del directorio al entrenar. Sin esto el fallo aparece cinco minutos después de empezar a
  cargar el modelo, no al principio.
- El conversor **tira el último fotograma de cada demo**: 5215 → 5190 en 25 demos.

Luego:

```bash
python3 train/scripts/fix_lerobot_meta.py ~/datasets/isaaclab_arena/g1_valve/sesion_01/lerobot
```

`total_chunks` sale a 0 (`len(demos) // chunks_size` = 25//1000) y `splits` se copia de la plantilla
como `{"train": "0:100"}`. Nada los lee al cargar, pero el `info.json` acaba en la memoria del TFM y
un dataset que se contradice a sí mismo no es citable.

### Verificar antes de seguir

*(contenedor: es donde están h5py, pyarrow y ffprobe a la vez)*

```bash
docker exec isaaclab_arena-latest bash -c 'cd /workspaces/isaaclab_arena && \
  /isaac-sim/python.sh /eval/arena_extras/verify_lerobot_dataset.py \
    --dataset /datasets/isaaclab_arena/g1_valve/sesion_01/lerobot \
    --hdf5    /datasets/isaaclab_arena/g1_valve/sesion_01.hdf5 \
    --png-out /eval/g1_valve_dryrun/train_frame0.png'
```

Comprueba longitudes (parquet ↔ `episodes.jsonl` ↔ mp4), contigüidad de `index`, `timestamp`,
**procedencia** (que la acción del episodio *k* sea de verdad la de su demo) y estadísticas por
dimensión con nombres de junta. **No sigas con FALLOS.** Los avisos sí son esperables: ver
[§ Lo que el verificador denuncia](#lo-que-el-verificador-denuncia).

---

## 2. Estadísticas

*(venv de GR00T)*

```bash
cd ~/TFM/isaac-gr00t-standalone
./.venv/bin/python gr00t/data/stats.py \
  --dataset-path ~/datasets/isaaclab_arena/g1_valve/sesion_01/lerobot \
  --embodiment-tag NEW_EMBODIMENT \
  --modality-config-path ~/TFM/IsaacLab-Arena/isaaclab_arena_gr00t/embodiments/g1/g1_sim_wbc_data_gr00t_n_1_7_config.py
```

**`NEW_EMBODIMENT` en mayúsculas aquí.** Esta ruta usa el *nombre* del enum vía tyro; el
`launch_finetune.py` usa `EmbodimentTag.resolve()` y acepta `new_embodiment` en minúsculas. No son
lo mismo y el mensaje de error no lo explica.

Escribe `meta/stats.json` y `meta/relative_stats.json` (que sale `{}`: las siete acciones del G1 son
`ABSOLUTE`). Se hace aquí, y no dejando que `factory.py` lo haga al entrenar, para que un problema de
permisos salte en diez segundos. **`generate_stats` se cortocircuita si ya hay un fichero válido**:
si regeneras el dataset, borra `meta/stats.json` a mano.

---

## 3. Probar el lazo de evaluación **antes** de entrenar nada

Este paso va antes del entrenamiento a propósito. Prueba lo más peligroso por lo más barato.

Las demos se graban con `g1_wbc_agile_pink` (23 dims: poses de muñeca que resuelve Pink IK). La
columna `action` del dataset es `processed_actions`: las **43 juntas de salida** de esa IK. Ninguna
política puede emitir las 23 originales porque no hay inversa 43→23 en el repositorio, así que se
evalúa con **`g1_wbc_agile_joint`** (50 dims = 43 juntas + 3 navegación + 1 altura de pelvis + 3
torso). Es decir: metemos la *salida* del controlador de cuerpo completo como su *entrada*. Nada en
el repositorio prueba ese viaje de ida y vuelta.

*(venv de GR00T, en el host)*

```bash
cd ~/TFM/IsaacLab-Arena
PYTHONPATH=$PWD:$HOME/Desktop/VLA-HumanoidG1/train/scripts \
  ~/TFM/isaac-gr00t-standalone/.venv/bin/python -u \
  -m isaaclab_arena.remote_policy.remote_policy_server_runner \
  --policy_type arena_replay_server.ArenaReplayServerSidePolicy \
  --host 127.0.0.1 --port 5561 --timeout_ms 120000 \
  --dataset_path ~/datasets/isaaclab_arena/g1_valve/sesion_01/lerobot --episode_index 0
```

Espera a leer `listening on tcp://127.0.0.1:5561` antes de lanzar el cliente.

*(contenedor)* — **este bloque es idéntico para las tres políticas**:

```bash
docker exec isaaclab_arena-latest bash -c 'cd /workspaces/isaaclab_arena && unset DISPLAY && export HOME=/home/ivines && \
 export ARENA_FIX_BASE=1 && export OFFICE_GS_LIGHT=1500 && export ARENA_VALVE_EPISODE_S=20 && \
 /isaac-sim/python.sh -u isaaclab_arena/evaluation/policy_runner.py \
   --policy_type isaaclab_arena.policy.action_chunking_client.ActionChunkingClientSidePolicy \
   --remote_host 127.0.0.1 --remote_port 5561 --remote_timeout_ms 120000 \
   --enable_cameras --device cuda:0 --num_envs 1 --num_episodes 10 --seed 42 \
   --language_instruction "turn the handwheel to open the valve" \
   --kit_args="--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0" \
   g1_valve --embodiment g1_wbc_agile_joint --background none'
```

- **`OFFICE_GS_LIGHT` depende de con qué se entrenó.** Esta línea del ensayo evaluaba en
  diáfano (`--background none`), donde la variable es **inerte**: sólo se lee en el camino NuRec
  (`g1_valve_environment.py:326`). Desde el dataset de 100 demos las imágenes salen del
  **re-render con la oficina**, generado con la variable **sin definir** (3000), así que se evalúa
  con `--background office_gs` y sin tocarla. Ponerla a 1500 ahí le daría a la política la mitad
  de luz que en entrenamiento, sobre su única entrada visual.
- **`--embodiment g1_wbc_agile_joint`**, no el de grabación. Con `g1_wbc_agile_pink` sale
  `Invalid action shape, expected: 23, received: 50`.
- **`--language_instruction`** con la cadena de `tasks.jsonl`, no la del entorno
  (`"Reach out and turn the wheel to open the valve."`). GR00T está condicionado por lenguaje y se
  afinó con la primera.
- **`--remote_timeout_ms 120000`.** El del *servidor* es sólo el tiempo de espera de ZMQ; el que
  aborta es el del cliente, y su valor por defecto son 15 s.

El HDF5 de métricas sale en `/tmp/isaaclab/logs/dataset_<ts>_rank0.hdf5`, visible desde el host
porque `/tmp` está montado. Guarda sólo `success` y `revolute_joint_state` (no cámaras).

**La decisión:** si `revolute_joint_moved_rate` sale 0, no sigas — ninguna política entrenada sobre
esa columna va a funcionar y hay que replantear la representación de acción antes de grabar más.

---

## 4. Fine-tune de GR00T

*(venv de GR00T)*

```bash
cd ~/TFM/isaac-gr00t-standalone
NUM_GPUS=1 GLOBAL_BATCH_SIZE=32 MAX_STEPS=10000 SAVE_STEPS=2000 USE_WANDB=0 \
SHARD_SIZE=512 DATALOADER_NUM_WORKERS=4 EPISODE_SAMPLING_RATE=0.1 \
CUDA_VISIBLE_DEVICES=0 PATH=$PWD/.venv/bin:$PATH \
bash examples/finetune.sh \
  --base-model-path ~/models/isaaclab_arena/static_apple_tutorial/gn1x_tuned_static_apple \
  --dataset-path ~/datasets/isaaclab_arena/g1_valve/sesion_01/lerobot \
  --embodiment-tag new_embodiment \
  --modality-config-path ~/TFM/IsaacLab-Arena/isaaclab_arena_gr00t/embodiments/g1/g1_sim_wbc_data_gr00t_n_1_7_config.py \
  --output-dir ~/models/isaaclab_arena/g1_valve/gr00t_n17_valve_10k --save-only-model
```

**Se parte del fine-tune de NVIDIA, no de un modelo base.** `gn1x_tuned_static_apple` es N1.7, el
mismo embodiment G1, el mismo espacio de 43 DoF y la misma cámara, y su `statistics.json` ya trae
exactamente nuestro juego de claves bajo `new_embodiment`: la cabeza que hace falta ya existe. Es lo
que más riesgo quita del plan — y además en disco no hay pesos base, habría que bajar 12,5 GB.

Elecciones que tienen motivo:

- **`NUM_GPUS=1`.** Con 2 GPUs el arranque se cuelga: NCCL avisa de que el mapeo rango→GPU es
  desconocido y "puede colgar", y cuelga, con ambos rangos al 90 % de CPU y las GPUs al 0 %, antes
  de generar los shards. En una GPU va a **3,2 pasos/s**: 10 000 pasos en menos de una hora.
- **`--modality-config-path` con el fichero `_n_1_7_`**, que declara horizonte 40, el del
  checkpoint. El hermano `g1_sim_wbc_data_config.py` usa 50. **No importes los dos en el mismo
  proceso**: `register_modality_config` revienta con tags duplicados.
- **`EPISODE_SAMPLING_RATE=0.1`, no 1.0.** El docstring dice "fracción de pasos a usar" y es falso:
  `sharded_single_step_dataset.py:203-207` hace `step_indices[i::num_splits]`, usa **todos** los
  pasos y sólo decide en cuántos trozos se parte cada episodio. Subirlo a 1.0 daría lotes mucho más
  correlacionados, lo contrario de lo que parece.
- **`SHARD_SIZE=512`** en vez de 1024: cada shard se procesa entero y se queda en RAM.
- **`--save-only-model`**: si no, cada checkpoint escribe 16 GB de estado de optimizador.
- **Directorio de salida siempre nuevo.** Ver abajo.

### Cómo saber si ha entrenado de verdad

`experiment.py` llama a `trainer.train(resume_from_checkpoint=True)` sin condiciones. Si queda un
checkpoint viejo cuyo `global_step` ya sea `max_steps`, HuggingFace ejecuta **cero pasos** y
`save_model()` guarda los pesos de antes: sales con un checkpoint impecable que nunca vio tus datos.

En el log tienen que salir:

- `Total steps: 4215` — los índices de arranque reales (5190 fotogramas − 25×39 de horizonte). Si
  dice 25 o 0, el *sharding* está mal y todo lo demás es basura.
- `No valid checkpoint found in output directory`. Si dice `Resuming from checkpoint`, párate.

Y la comprobación que no se puede engañar:

```bash
~/TFM/isaac-gr00t-standalone/.venv/bin/python train/scripts/compare_checkpoint_weights.py \
  --base  ~/models/isaaclab_arena/static_apple_tutorial/gn1x_tuned_static_apple \
  --tuned ~/models/isaaclab_arena/g1_valve/gr00t_n17_valve_10k/checkpoint-10000
```

Se espera `max|Δ| == 0` en los 493 tensores congelados (backbone Cosmos) y claramente distinto de
cero en los 537 entrenables (proyector y cabeza de difusión). Si los entrenables también salen a
cero, no ha pasado nada por muy bonita que sea la curva.

Conviene además mirar que `checkpoint-N/statistics.json` traiga rangos de **válvula** y no de
manzana, y que `processor_config.json` esté en la raíz del checkpoint: si no, el servidor no carga.

### Servirlo

*(venv de GR00T, desde la raíz de Arena — las rutas del YAML se resuelven contra el CWD)*

```bash
cd ~/TFM/IsaacLab-Arena
PYTHONPATH=$PWD ~/TFM/isaac-gr00t-standalone/.venv/bin/python -u \
  -m isaaclab_arena.remote_policy.remote_policy_server_runner \
  --policy_type isaaclab_arena_gr00t.policy.gr00t_remote_policy.Gr00tRemoteServerSidePolicy \
  --host 127.0.0.1 --port 5561 --timeout_ms 300000 \
  --policy_config_yaml_path isaaclab_arena_gr00t/policy/config/g1_valve_gr00t_closedloop_config.yaml \
  --policy_device cuda:1
```

`model_path` dentro del YAML es una ruta **de host**, no `/models/...`: el servidor no vive en el
contenedor. Luego, el mismo bloque de cliente del § 3.

---

## 5. ACT (LeRobot)

### El entorno

```bash
uv venv --python 3.10 ~/venvs/lerobot-act
UV_TORCH_BACKEND=cu128 uv pip install --python ~/venvs/lerobot-act/bin/python \
  "lerobot==0.3.3" pyzmq msgpack
```

Los dos pines son obligatorios:

- **`lerobot==0.3.3`** es la última versión con `CODEBASE_VERSION = "v2.1"`. La 0.4.0 salta a v3.0 y
  rechaza el dataset; las recientes además exigen Python ≥ 3.12.
- **`UV_TORCH_BACKEND=cu128`** porque estas Blackwell son sm_120 y la rueda por defecto de PyPI no
  trae kernels: falla en la primera convolución con `no kernel image is available`.

### La vista del dataset

El dataset convertido es v2.1 en estructura pero **sin estadísticas**, y a v2.1 LeRobot lee
`meta/episodes_stats.jsonl` — no `stats.json`, que sólo se consulta por debajo de v2.1.

```bash
~/venvs/lerobot-act/bin/python train/scripts/make_lerobot_act_view.py \
  --src  ~/datasets/isaaclab_arena/g1_valve/sesion_01/lerobot \
  --dest ~/datasets/isaaclab_arena/g1_valve/sesion_01/lerobot_act
```

Crea una vista hermana, no una copia: `data/` y `videos/` van por enlace simbólico. El `meta/` propio
quita de `info.json` las columnas que confundirían a ACT (`dataset_to_policy_features` mapea
*cualquier* clave que empiece por `action` a `FeatureType.ACTION`, así que `action.eef_pose` le daría
dos acciones) y escribe `episodes_stats.jsonl` con las funciones **de LeRobot**, no reimplementadas:
hay dos reglas que se incumplen a la primera —`count` con forma exactamente `(1,)`, y toda clave que
contenga la subcadena `image` con min/max/mean/std de forma exactamente `(3,1,1)`—.

Se valida instanciando el dataset antes de entrenar: 5190 muestras, `observation.state` `(43,)`,
`action` `(40,43)`.

### Entrenar

```bash
CUDA_VISIBLE_DEVICES=1 ~/venvs/lerobot-act/bin/lerobot-train \
  --dataset.repo_id=tfm/g1_valve_sesion_01 \
  --dataset.root=~/datasets/isaaclab_arena/g1_valve/sesion_01/lerobot_act \
  --dataset.video_backend=torchcodec \
  --policy.type=act --policy.device=cuda --policy.push_to_hub=false \
  --policy.chunk_size=40 --policy.n_action_steps=40 \
  --batch_size=8 --steps=20000 --save_freq=5000 --log_freq=200 --num_workers=8 \
  --wandb.enable=false --seed=42 \
  --output_dir=~/models/isaaclab_arena/g1_valve/act_valve_dryrun
```

`--policy.push_to_hub=false` es obligatorio o aborta pidiendo `policy.repo_id`. `chunk_size=40` en
vez del 100 por defecto de ACT, para comparar con GR00T al mismo horizonte y para que la demo más
corta (133 fotogramas) no sea tres cuartas partes de relleno. 20 000 pasos ≈ 31 épocas, unos 18 min.

### Servirlo

```bash
cd ~/TFM/IsaacLab-Arena
PYTHONPATH=$PWD:$HOME/Desktop/VLA-HumanoidG1/train/scripts CUDA_VISIBLE_DEVICES=1 \
  ~/venvs/lerobot-act/bin/python -u \
  -m isaaclab_arena.remote_policy.remote_policy_server_runner \
  --policy_type act_remote_policy.ActRemoteServerSidePolicy \
  --host 127.0.0.1 --port 5561 --timeout_ms 300000 \
  --checkpoint ~/models/isaaclab_arena/g1_valve/act_valve_dryrun/checkpoints/020000/pretrained_model \
  --device cuda \
  --stats_json ~/datasets/isaaclab_arena/g1_valve/sesion_01/lerobot/meta/stats.json
```

**`CUDA_VISIBLE_DEVICES=1` con `--device cuda`, nunca `--device cuda:1`.** Ver el fallo de los
búferes más abajo: es el error más caro de todo este documento y no da ningún mensaje.

Y otra vez el mismo bloque de cliente del § 3.

---

## Lo que el verificador denuncia

Tres avisos que salen siempre con esta sesión y **no** son defectos del pipeline:

1. **El índice de episodio no es el número de demo.** El conversor itera
   `list(f["data"].keys())`, que en h5py sale alfabético: `episode_000002 ← demo_10`,
   `episode_000012 ← demo_2`. Inofensivo, pero si comparas trazas sin saberlo no cuadran.
2. **El margen sobre el umbral de éxito es de 0,8° en la peor demo.** Las demos llegan a 181-232° y
   el éxito es media vuelta (180°). Una política que se quede algo corta puntúa `success_rate = 0`
   con la válvula girando perfectamente. Por eso **la métrica que hay que leer es
   `revolute_joint_moved_rate`**, con el replay como cota superior.
3. **11 de las 43 dimensiones de acción tienen desviación típica exactamente 0**: las 3 de cintura
   (`lock_waist`), las 7 de la mano derecha y `left_hand_thumb_0_joint`. En esta sesión no se cerró
   ninguna mano. GR00T lo tolera (min-max con `range = max(max-min, 1e-8)` y recorte); ACT lo
   normaliza con media/desviación y **eso es lo que hace explotar el estado si algo más va mal**.

---

## Fallos típicos

| síntoma | causa | solución |
|---|---|---|
| La conversión se queda parada sin mensaje | el destino existe y `dataset_config.py:154` está en un `input()` | `rm -rf` del destino, y lanzar con `</dev/null` |
| `info.json` dice 25 episodios pero hay menos parquets | el conversor se traga excepciones por demo y aun así cuenta `len(claves)` | contar ficheros; `grep "Error loading trajectory"` en el log |
| Fallo de permisos cinco minutos después de empezar a entrenar | el dataset es de root | `chown -R` tras convertir |
| `invalid choice: 'new_embodiment'` en `stats.py` | esa ruta quiere el **nombre** del enum | `NEW_EMBODIMENT` en mayúsculas |
| Entrenamiento de GR00T con 2 GPUs parado, GPUs al 0 % y CPU al 90 % | init distribuido sin `device_id`; NCCL lo avisa y cuelga antes de generar shards | `NUM_GPUS=1` (3,2 pasos/s, sobra) |
| El checkpoint sale idéntico al de partida | HF Trainer reanudó y ejecutó 0 pasos | `--output-dir` nuevo; `grep Resuming`; `compare_checkpoint_weights.py` |
| `Invalid action shape, expected: 23, received: 50` | el cliente usa el embodiment de grabación | `--embodiment g1_wbc_agile_joint` |
| **ACT emite exactamente ceros** | los búferes de normalización se corrompen al mover el modelo a `cuda:1` | `CUDA_VISIBLE_DEVICES=1` + `--device cuda`; el servidor lo comprueba al arrancar |
| El robot se sienta en el suelo | la cola de 50 dims se rellenó con ceros y el índice 46 es `base_height_cmd` | rellenar con 0.72, leído de `meta/stats.json` |
| El cliente aborta a mitad de episodio | `--remote_timeout_ms` por defecto son 15 s | subirlo a 120000 |
| `policy.repo_id argument missing` | LeRobot quiere subir al hub | `--policy.push_to_hub=false` |

### El fallo de los búferes, con detalle

Medido el 2026-08-19, torch 2.7.1+cu128, 2× RTX PRO 6000 Blackwell. Cargar la política ACT y moverla
a **`cuda:1`** pone a **cero** la desviación típica de `normalize_inputs.buffer_observation_state`,
sin lanzar nada. `Normalize` divide entonces por `0 + 1e-8`, el estado normalizado sale del orden de
10⁸, la red satura y `predict_action_chunk` devuelve exactamente ceros.

| dispositivo | std mínimo del búfer | estado normalizado (máx abs) | std de la acción |
|---|---|---|---|
| CPU | 5,075e-05 | 7,58 | 0,299 |
| `cuda:0` | 5,075e-05 | 7,58 | 0,299 |
| **`cuda:1`** | **0** | **5,0e+07** | **0** |
| `CUDA_VISIBLE_DEVICES=1` + `cuda` | 5,075e-05 | 7,58 | 0,299 |

Los pesos del checkpoint están bien; es el traslado a un índice de GPU distinto de 0 lo que los
corrompe. El síntoma —"la política no hace nada"— es indistinguible de un entrenamiento fallido, que
es exactamente por lo que `act_remote_policy.py` lo comprueba al arrancar y se niega a servir.

---

## Parar todo

```bash
# servidores de política (host)
pgrep -f remote_policy_server_runner | xargs -r kill -9
# simulador (dentro del contenedor: los procesos son de root)
docker exec isaaclab_arena-latest bash -c 'pkill -9 -f policy_runner.py'
```

**Ojo con `pkill -f` en el host**: el patrón coincide con la propia línea de comandos del shell que
lo lanza y se mata a sí mismo. Pasó dos veces montando esto. Usa `pgrep | xargs kill` o mata por PID.
