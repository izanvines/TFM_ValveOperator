# Teleoperación de `g1_valve` en la workstation (VNC) — Guía de lanzamiento

Cómo teleoperar el entorno **`g1_valve`** (G1 + válvula) con el emulador web (Meta Quest 3
simulado, sin gafas físicas) en la workstation, viendo a la vez un **monitor en 3ª persona**.

Verificado funcionando el 2026-07-23.

---

## Arquitectura (por qué cada pieza)

- **Modo XR headless**: la ventana nativa de Isaac Sim NO se puede abrir durante XR sobre
  TurboVNC (da `GLXBadFBConfig`: la ventana estéreo pide un framebuffer GLX que el VNC virtual
  no tiene). Por eso se va headless y la vista llega por streaming al navegador.
- **CloudXR** (puerto 49100): transmite la vista estéreo Meta Quest al navegador → teleoperas.
- **Livestream WebRTC** (puerto 49200): transmite un viewport en 3ª persona → monitorizas.
- **GPU fijada** (`--kit_args`): la workstation tiene 2 GPUs; sin fijar una, el XR falla con
  `VK_ERROR_OUT_OF_DEVICE_MEMORY`. OJO: **no** usar `CUDA_VISIBLE_DEVICES` (rompe el render del
  monitor → negro); basta con los kit_args.

---

## Requisitos previos (una sola vez)

1. **Contenedor corriendo**: `isaaclab_arena-latest` levantado (`./docker/run_docker.sh` desde
   `~/TFM/IsaacLab-Arena`).
2. **Google Chrome** (obligatorio; Opera/Firefox rompen WebXR con `TypeError ... 'prototype'`).
3. **Extensión "Immersive Web Emulator" de Meta** en ese Chrome
   (Chrome Web Store, o sideload del release `iwe-v1.3.0.zip` de
   github.com/meta-quest/immersive-web-emulator → `chrome://extensions` → Modo desarrollador →
   Cargar descomprimida).
4. **Cliente "Isaac Sim WebRTC Streaming Client"** instalado (para el monitor 3ª persona).

---

## Paso 1 — Arrancar el runtime CloudXR

En una terminal (déjala abierta, es un servidor):
```bash
docker exec -it isaaclab_arena-latest bash
python -m isaacteleop.cloudxr
# La primera vez pide aceptar el EULA de NVIDIA → escribe: Yes
```
Espera a que quede escuchando. Crea `/home/ivines/.cloudxr/run/cloudxr.env`.

> Si esta terminal se cierra, CloudXR muere y hay que relanzarlo.

## Paso 2 — Lanzar el teleop (headless XR + monitor WebRTC)

En otra terminal:
```bash
docker exec -w /workspaces/isaaclab_arena isaaclab_arena-latest bash -c \
  'source /home/ivines/.cloudxr/run/cloudxr.env && unset DISPLAY && export HOME=/home/ivines && \
   /isaac-sim/python.sh isaaclab_arena/scripts/imitation_learning/teleop.py \
     --device cpu \
     --livestream 2 \
     --kit_args="--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0 --/exts/omni.kit.livestream.app/primaryStream/signalPort=49200" \
     g1_valve --teleop_device openxr'
```
Espera ~40-60 s a que cargue. Comprueba que escuchan los dos puertos:
```bash
ss -tlnp | grep -E "49100|49200"
```

> **Solo teleop, sin monitor**: quita `--livestream 2` y el `signalPort=49200` de los kit_args.

## Paso 3 — Conectar la Vista 1 (teleoperar, Meta Quest)

1. Chrome → `https://nvidia.github.io/IsaacTeleop/client`
2. **Server IP** = `<IP_ESTACION>` (o la IP que uses para el VNC)
3. Acepta el certificado en `https://<IP_ESTACION>:48322/` si lo pide
4. **Connect** → **Play**  (la sesión XR arranca sola, no hay que pulsar "Start XR")
5. `F12` → pestaña **WebXR** → dispositivo **Meta Quest 3**, controllers activados → mueves las
   manos del robot con ratón/teclado

> Solo **una** pestaña conectada. Si sale "active XRSession already exists", cierra las demás y
> reinicia el teleop (Paso 2).

## Paso 4 — Conectar la Vista 2 (monitor 3ª persona)

En el **Isaac Sim WebRTC Streaming Client** (instalado en la workstation):
- **Server** = `127.0.0.1` (localhost, porque el cliente está en la misma máquina)
- **Puerto de señalización** = `49200`
- Connect

Deberías ver la escena en 3ª persona en tiempo real.

---

## Controles del emulador (IWER)

- **Joystick izquierdo**: mover cuerpo (adelante/atrás/lados)
- **Joystick derecho**: agacharse / rotar torso
- **Controladores (ratón, pestaña WebXR)**: mover las manos → con esto agarras la rueda de la válvula

---

## Grabar demostraciones (dataset)

Mismo comando del Paso 2 pero con `record_demos.py` en lugar de `teleop.py`, añadiendo cámaras y
destino del HDF5:
```bash
docker exec -w /workspaces/isaaclab_arena isaaclab_arena-latest bash -c \
  'source /home/ivines/.cloudxr/run/cloudxr.env && unset DISPLAY && export HOME=/home/ivines && \
   /isaac-sim/python.sh isaaclab_arena/scripts/imitation_learning/record_demos.py \
     --device cpu --enable_cameras \
     --dataset_file /datasets/g1_valve_dataset.hdf5 \
     --num_demos 20 --num_success_steps 10 --disable_full_sim_buffer_reset \
     --livestream 2 \
     --kit_args="--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0 --/exts/omni.kit.livestream.app/primaryStream/signalPort=49200" \
     g1_valve --teleop_device openxr'
```
El HDF5 queda en `~/datasets/g1_valve_dataset.hdf5` (mount `/datasets` → `~/datasets`).

---

## Ver el entorno en la ventana NATIVA de Isaac Sim (modo aparte, sin teleop)

Para inspeccionar la escena en la GUI de Isaac Sim dentro del VNC (orbitar cámara, árbol de la
stage, etc.), sin teleoperar. En una terminal interactiva del escritorio VNC:
```bash
docker exec -it isaaclab_arena-latest bash
export DISPLAY=:2
cd /workspaces/isaaclab_arena
vglrun -d :2 /isaac-sim/python.sh isaaclab_arena/evaluation/policy_runner.py \
  --viz kit --policy_type zero_action --num_steps 100000 \
  g1_valve --embodiment g1_wbc_agile_pink
```
Con `zero_action` los brazos se cruzan (cosmético, no hay política que los mueva); las piernas se
sostienen por AGILE. Este modo **no** es XR, por eso sí abre ventana en VNC.

---

## Fallos típicos y solución

| Síntoma | Causa | Solución |
|---|---|---|
| `GLXBadFBConfig` al arrancar | Intentas ventana nativa (`--viz kit`) con XR sobre VNC | No se puede; usa modo headless (sin `--viz kit`) |
| `VK_ERROR_OUT_OF_DEVICE_MEMORY` | Multi-GPU en el XR | Añade los kit_args `multiGpu=false` + `activeGpu=0` |
| Monitor WebRTC en negro | `CUDA_VISIBLE_DEVICES` deja CUDA en mal estado | Quítalo; fija la GPU solo con kit_args |
| `TypeError ... 'prototype'` en el navegador | No es Chrome | Usa Google Chrome |
| "immersive mode not supported" | Falta el emulador WebXR | Instala la extensión Immersive Web Emulator |
| "active XRSession already exists" | Varias pestañas/conexiones | Deja una sola; reinicia el teleop |
| CloudXR (49100) no escucha | Se cerró su terminal | Relanza el Paso 1 |

## Parar todo
```bash
docker exec isaaclab_arena-latest bash -c "pkill -9 -f teleop.py; pkill -9 -f isaacteleop.cloudxr"
```
