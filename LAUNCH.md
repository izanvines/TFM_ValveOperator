# Cómo lanzar la simulación `g1_valve`

Comandos verificados el **2026-08-18** en la workstation `tr-robotics-workstation-tocha`.
Cada modo es autocontenido: copia el bloque entero.

Todo corre **dentro del contenedor** `isaaclab_arena-latest`. El código de simulación vive en
`~/TFM/IsaacLab-Arena` (montado en `/workspaces/isaaclab_arena`), **no** en este repo — ver
[`sim/README.md`](sim/README.md) para la correspondencia entre ambos.

---

## 0. Antes de nada

**Estas tres líneas van en *todos* los comandos.** No son cosmética:

| línea | qué pasa si falta |
|---|---|
| `unset DISPLAY` | Isaac Sim revienta a los ~2 s dentro de `libX11!XOpenDisplay`, sin traza de Python, solo un minidump |
| `export HOME=/home/ivines` | no encuentra `~/.cloudxr`, ni cachés, ni el runtime de OpenXR |
| `--kit_args "--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0"` | el XR muere con `VK_ERROR_OUT_OF_DEVICE_MEMORY` (la máquina tiene 2 GPUs) |

**Nunca uses `CUDA_VISIBLE_DEVICES`** para fijar la GPU: deja CUDA en un estado en el que el
monitor WebRTC sale negro. Se fija solo con `--kit_args`.

### Comprobar que el contenedor está vivo

```bash
docker ps --filter name=isaaclab_arena-latest --format '{{.Names}}\t{{.Status}}'
```

El healthcheck dice `unhealthy` y **es normal**, el contenedor funciona. Si no está,
levántalo desde `~/TFM/IsaacLab-Arena` con `./docker/run_docker.sh -d ~/datasets -m ~/models -e ~/eval`.

### Puertos y cortafuegos

`ufw` está activo con política `DROP` por defecto: un puerto sin regla **descarta el paquete en
silencio** — sin error, sin rechazo, sin línea de log. Es exactamente igual que "no funciona".

| puerto | protocolo | para qué |
|---|---|---|
| 49100 | TCP | señalización WebRTC (modo A) **o** backend de CloudXR (modos B/C) |
| 47998 | UDP | vídeo WebRTC (modo A) |
| 48322 | TCP | proxy WSS: **es al único puerto que se conectan las gafas** |
| 49120 / 48020 | TCP / UDP | monitor de 3ª persona durante teleop (opcional) |

```bash
# comprobar qué reglas hay
sudo ufw status numbered

# abrir lo necesario (ajusta la subred a la de tu portátil / gafas)
sudo ufw allow from 172.22.41.0/24 to any port 49100 proto tcp
sudo ufw allow from 172.22.41.0/24 to any port 47998 proto udp
sudo ufw allow from 172.22.41.0/24 to any port 48322 proto tcp
```

La señalización es **TCP** y el vídeo **UDP**. Un túnel SSH solo reenvía TCP, así que conectar el
cliente a `127.0.0.1` a través de un túnel negocia la sesión y luego se queda **negro para
siempre**. Apunta el cliente a `172.22.41.51` directamente.

---

## Modo A — Ver la simulación (sin gafas)

Para inspeccionar la escena, hacer capturas para la memoria, o comprobar que el entorno carga.
No hay teleoperación: el robot se queda de pie en una pose estable.

```bash
docker exec isaaclab_arena-latest bash -c \
 'cd /workspaces/isaaclab_arena && unset DISPLAY && export HOME=/home/ivines && \
  export PUBLIC_IP=172.22.41.51 && export OFFICE_GS_LIGHT=1500 && \
  /isaac-sim/python.sh -u /eval/arena_extras/stream_valve.py \
    --livestream 1 --viz kit --enable_cameras --device cuda:0 \
    --kit_args "--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0" \
    g1_valve --background none'
```

Espera a `>> STREAM LISTO`. Conecta el **Isaac Sim WebRTC Streaming Client**:

```
Server:      172.22.41.51
Signal port: 49100
Stream port: 47998
```

> **`--viz kit` no es opcional.** En esta versión de Isaac Lab el viewport es un *visualizer* que
> hay que pedir explícitamente. Sin él no existe viewport, y `omni.kit.livestream.app` —que
> transmite *el framebuffer de la aplicación*— emite un buffer vacío. Pantalla negra, con los
> puertos perfectamente abiertos. Detalles en `CLAUDE.md`.

Encuadre: se ajusta con `--cam_eye` / `--cam_target` (por defecto `2.2,-1.9,1.8` → `0.35,0,1.0`).

### Sin cliente WebRTC: sacar un PNG o un vídeo

```bash
# un PNG del viewport (sirve además para descartar que el render sea el problema)
docker exec isaaclab_arena-latest bash -c \
 'cd /workspaces/isaaclab_arena && unset DISPLAY && export HOME=/home/ivines && \
  /isaac-sim/python.sh -u /eval/arena_extras/capture_viewport.py \
    --viz kit --enable_cameras --device cuda:1 \
    --kit_args "--/renderer/multiGpu/enabled=false --/renderer/activeGpu=1" \
    g1_valve --background none'
# -> ~/eval/viewport_check.png
```

---

## Modo B — Teleoperar con las PICO 4 Ultra (prueba, sin grabar)

Son **dos procesos**. CloudXR es un servidor: si cierras su terminal, muere.

### B.1 Runtime de CloudXR

```bash
docker exec -e HOME=/home/ivines isaaclab_arena-latest \
  /isaac-sim/python.sh -m isaacteleop.cloudxr --accept-eula
```

Déjalo corriendo. Comprueba que escucha antes de seguir:

```bash
ss -tln | grep -E '49100|48322'
```

### B.2 Teleop

```bash
docker exec -w /workspaces/isaaclab_arena isaaclab_arena-latest bash -c \
 'source /home/ivines/.cloudxr/run/cloudxr.env && unset DISPLAY && export HOME=/home/ivines && \
  export ARENA_STATIC_BASE=1 && export ARENA_FIX_BASE=1 && export ARENA_XR_ANTIALIASING="" && \
  export OFFICE_GS_LIGHT=1500 && export ARENA_VALVE_EPISODE_S=60 && \
  /isaac-sim/python.sh -u isaaclab_arena/scripts/imitation_learning/teleop.py \
    --device cuda \
    --kit_args="--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0 --/persistent/xr/profile/ar/renderQuality=performance --/rtx/rendermode=RaytracedLighting --/rtx/post/tonemap/op=2" \
    g1_valve --teleop_device openxr --embodiment g1_wbc_agile_pink --background none'
```

Listo cuando aparezcan `Completed setting up the environment...` y `xrCreateInstance: Instance created`.

### B.3 Conectar las gafas

1. En la PICO: **Ajustes → WiFi** → anota la IP que tiene.
2. Abre en el navegador de las gafas `https://<IP de la workstation>:48322/` y **acepta el
   certificado** (es autofirmado; si no lo aceptas, la conexión WSS falla en silencio).
3. Ve a `https://nvidia.github.io/IsaacTeleop/client`
4. **Server IP** = la IP de la workstation que alcance esa red
   (`172.22.41.51` por cable, `192.168.84.71` por WiFi `TR-DT`).
5. **Connect → Play**. La sesión XR arranca sola; no busques ningún botón "Start XR".

### Los ajustes de rendimiento importan

Sin `renderQuality=performance` y `rendermode=RaytracedLighting` el estéreo va a **1 FPS**
—incontrolable—. Con ellos, ~20 FPS. Y **el monitor de 3ª persona cuesta un producto de render
entero**: si lo añades (`--viz kit --livestream 2` + los `signalPort`/`streamPort` de 49120/48020),
lo pagas en FPS del casco. Para teleoperar de verdad, sin monitor.

### Monitor de 3ª persona (opcional, cuesta FPS)

Añade al comando B.2: `--viz kit --livestream 2` y a los `--kit_args`:

```
--/exts/omni.kit.livestream.app/primaryStream/signalPort=49120
--/exts/omni.kit.livestream.app/primaryStream/streamPort=48020
--/exts/omni.kit.livestream.app/primaryStream/publicIp=172.22.41.51
```

CloudXR ocupa el 49100 fijo (`isaacteleop/cloudxr/wss.py:244`, sin opción de CLI), por eso el
monitor tiene que irse a otro puerto durante la teleoperación.

---

## Modo C — Grabar el dataset

Igual que el modo B pero con `record_demos.py`. **CloudXR tiene que estar corriendo** (paso B.1).

```bash
docker exec -w /workspaces/isaaclab_arena isaaclab_arena-latest bash -c \
 'source /home/ivines/.cloudxr/run/cloudxr.env && unset DISPLAY && export HOME=/home/ivines && \
  export ARENA_STATIC_BASE=1 && export ARENA_FIX_BASE=1 && export ARENA_XR_ANTIALIASING="" && \
  export OFFICE_GS_LIGHT=1500 && export ARENA_VALVE_EPISODE_S=20 && \
  mkdir -p /datasets/isaaclab_arena/g1_valve && \
  /isaac-sim/python.sh -u isaaclab_arena/scripts/imitation_learning/record_demos.py \
    --device cuda --enable_cameras \
    --dataset_file /datasets/isaaclab_arena/g1_valve/g1_valve_session_$(date +%Y%m%d_%H%M%S).hdf5 \
    --num_demos 20 --num_success_steps 10 --disable_full_sim_buffer_reset \
    --kit_args="--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0 --/persistent/xr/profile/ar/renderQuality=performance --/rtx/rendermode=RaytracedLighting --/rtx/post/tonemap/op=2" \
    g1_valve --teleop_device openxr --embodiment g1_wbc_agile_pink --background none'
```

El HDF5 sale en `~/datasets/isaaclab_arena/g1_valve/`.

Diferencias respecto al modo B, y por qué:

- **`--enable_cameras`**. Aquí sí y además hace falta: es lo que escribe la cámara en el HDF5, y
  esa cámara *es* la entrada de la política. Lo que quede fuera del encuadre no existe para ella.
  En `teleop.py` es imposible (llama a `remove_camera_configs()` sin condición cuando hay XR y
  cuelga el término de observación); en `record_demos.py:217` solo las quita si NO pasas el flag.
- **`ARENA_VALVE_EPISODE_S=20`** en vez de 60. La doc de NVIDIA recomienda episodios de 200-400
  pasos; a 50 Hz eso son 4-8 s. 20 s (1000 pasos) es un compromiso: da tiempo a aproximar, agarrar
  y dar media vuelta sin que las demostraciones se llenen de segundos muertos. **Si el episodio se
  agota, la demo muere por timeout y NO se escribe** — mejor pasarse que quedarse corto.
- **`--num_success_steps 10`**: hay que mantener el éxito 10 pasos para que cuente, así no se
  valida un roce.
- **Una sesión por fichero.** Se juntan luego con `merge_demos.py`, que valida que coincidan
  `format_version`, forma de la acción, claves de observación y geometría de cámara.

### Convertir a LeRobot

```bash
docker exec isaaclab_arena-latest bash -c \
 'cd /workspaces/isaaclab_arena && unset DISPLAY && export HOME=/home/ivines && \
  /isaac-sim/python.sh isaaclab_arena_gr00t/lerobot/convert_hdf5_to_lerobot.py \
    --yaml_file isaaclab_arena_gr00t/lerobot/config/g1_valve_config.yaml'
```

El YAML se copia de `g1_static_apple_config.yaml` (mismo embodiment G1, 43 DoF, `unitree_g1`,
`observation.images.ego_view`, 50 fps) cambiando solo `data_root`, `language_instruction`,
`task_index` y `hdf5_name`. **Convierte una sola demo y compruébala antes de grabar 400.**

---

## Parar todo

```bash
docker exec isaaclab_arena-latest bash -c \
  'pkill -9 -f teleop.py; pkill -9 -f record_demos.py; pkill -9 -f stream_valve.py; pkill -9 -f isaacteleop'
```

Los procesos corren como `root` dentro del contenedor: un `pkill` desde el host da
`Operation not permitted`. Hay que matarlos **desde dentro**.

---

## Variables de entorno

| variable | por defecto | qué hace |
|---|---|---|
| `ARENA_FIX_BASE` | `1` | clava la pelvis al mundo (`fix_root_link`). Con `0` vuelve el robot equilibrándose con AGILE |
| `ARENA_STATIC_BASE` | `0` | congela los comandos de locomoción a `[0,0,0,0.72]`. **Ponlo a 1 al grabar** |
| `ARENA_VALVE_EPISODE_S` | `15` | duración del episodio en segundos |
| `ARENA_XR_ANTIALIASING` | `DLSS` | vacío desactiva el DLSS forzado que pisa `rendermode` y sobreexpone la escena |
| `OFFICE_GS_LIGHT` | `3000` | intensidad de la dome light. 1500 va bien en la escena diáfana |
| `PUBLIC_IP` | `127.0.0.1` | IP que anuncia el livestream WebRTC (solo con `--livestream 1`) |

`ARENA_FIX_BASE` y `ARENA_STATIC_BASE` **no son lo mismo**: el segundo impide que el operador
camine con el joystick, pero la base sigue siendo un cuerpo libre que reacciona a las fuerzas de
contacto — al girar el volante, el par de reacción hacía girar al robot entero. El primero es el
que de verdad lo sujeta.

---

## Fallos típicos

| síntoma | causa | solución |
|---|---|---|
| Segfault ~2 s, sin traza | falta `unset DISPLAY` | ver §0 |
| Stream WebRTC en negro | falta `--viz kit`: no hay viewport | añadirlo; verificar con `capture_viewport.py` |
| Stream negro con los puertos "abiertos" | el cliente va por túnel SSH (TCP), el vídeo es UDP | apuntar a `172.22.41.51` directo |
| Conecta la señalización, nunca llega imagen | falta la regla UDP en ufw | ver §0 |
| `VK_ERROR_OUT_OF_DEVICE_MEMORY` | multi-GPU en XR | `--kit_args` con `multiGpu=false` + `activeGpu=0` |
| 1 FPS en las gafas | falta `renderQuality=performance` / sobra el monitor | ver §B |
| La válvula no gira al agarrarla | `drive:angular:physics:damping` alto | está en `sim/assets/valve_rig_arena.usda` |
| El robot gira al hacer fuerza | `ARENA_FIX_BASE=0` | ponlo a 1 |
| "active XRSession already exists" | varias pestañas conectadas | deja una y relanza el teleop |
| Las gafas no conectan a 48322 | falta la regla ufw para su subred | ver §0 |
| `pkill` da `Operation not permitted` | los procesos son de root del contenedor | matar desde dentro |
