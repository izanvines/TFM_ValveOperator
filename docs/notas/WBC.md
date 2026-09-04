# WBC + Teleop VR con Pico 4 Ultra para Unitree G1 (sin Jetson Thor)

> Investigación: julio 2026. Stack: **NVIDIA GR00T-WholeBodyControl** (GEAR-SONIC) + **XRoboToolkit** (PICO).
> Objetivo: teleoperar el G1 en cuerpo completo con Pico 4 Ultra + motion trackers, probando primero en MuJoCo y después en el robot real.

---

## 1. Conclusión principal

**La Jetson Thor NO es necesaria.** Solo la requiere la variante `isaacteleop[cloudxr]` (runtime CloudXR *in-process* en una "mochila" Thor sobre el G1), que es lo que documenta el workflow end-to-end de NVIDIA. La ruta estándar del tutorial oficial de whole-body teleop usa XRoboToolkit y funciona con:

- Un **PC Linux normal** (para el streamer del casco y, en simulación, para todo).
- La política WBC corriendo en un **PC x86 con GPU RTX** (simulación / desarrollo) o en el **Orin NX que ya lleva el G1** (robot real, flasheado a JetPack 6).

Referencia comercial de que esto funciona: el kit de teleop de RoboStore para el G1 es exactamente Pico 4 Ultra + 2 mandos + 2 trackers de tobillo + GR00T-WBC, con un portátil gaming (Lenovo Legion) como único cómputo externo.

---

## 2. Componentes del stack

| Componente | Qué es |
|---|---|
| **GR00T-WholeBodyControl** ([repo](https://github.com/NVlabs/GR00T-WholeBodyControl)) | Plataforma unificada de NVIDIA para WBC de humanoides. Incluye **GEAR-SONIC** (foundation model de comportamiento, RL en Isaac Lab sobre BONES-SEED: 142k movimientos / ~288 h) y el **Decoupled WBC** de GR00T N1.5/N1.6 (RL tren inferior + IK tren superior). Licencia Apache 2.0 (código) + NVIDIA Open Model License (pesos). |
| **gear_sonic_deploy** | Stack C++ de inferencia (ONNX → TensorRT, CUDA graphs, latencia sub-ms). Es el binario que ejecuta la política WBC, tanto contra MuJoCo como contra el G1 real. |
| **XRoboToolkit** ([PC Service](https://github.com/XR-Robotics/XRoboToolkit-PC-Service)) | Framework abierto de PICO para teleop: app Unity en el casco + servicio en el PC (gRPC). Streamea cabeza, mandos, hand tracking (26 art./mano) y **cuerpo completo (24 articulaciones) con los motion trackers**. |
| **PICO streamer** (`pico_manager_thread_server.py`) | Script del repo GR00T-WBC que convierte el tracking de XRoboToolkit en poses SMPL y las publica por **ZMQ** al deployment C++. |

### Arquitectura (3 procesos)

```
[Pico 4 Ultra + 2 trackers tobillo]
        │  WiFi (XRoboToolkit, gRPC)
        ▼
[PC: XRoboToolkit PC Service + pico_manager_thread_server.py]   ← Terminal 3
        │  ZMQ (poses SMPL)
        ▼
[Deployment C++ gear_sonic_deploy — política WBC en TensorRT]   ← Terminal 2
        │                          (PC x86 en sim / Orin NX del G1 en real)
        ▼
[MuJoCo (run_sim_loop.py)  ó  G1 real]                          ← Terminal 1
```

---

## 3. Hardware necesario

- **Pico 4 Ultra** con modo desarrollador. *Nota:* la doc oficial lista "PICO 4 / PICO 4 Pro", pero la 4 Ultra está confirmada en el ecosistema (kit RoboStore, paper XRoboToolkit). La versión **Enterprise** evita fricciones, pero la consumer con dev mode funciona.
- **2 × PICO Motion Tracker (Swift)** — uno por tobillo, LED hacia arriba.
- **2 mandos** de la Pico (calibración y combos de botones).
- **PC con Ubuntu 22.04 o 24.04**:
  - Para **simulación**: GPU NVIDIA RTX (TensorRT 10.13, CUDA 12.4.1, driver ≥ 550).
  - Para **solo streamer** (cuando la política corre en el Orin del G1): sin requisito de GPU.
- **Unitree G1** con Orin NX a bordo (para la fase real; hay que flashearlo a JetPack 6.2).
- **WiFi rápida y de baja latencia**, idealmente router dedicado; casco, PC y robot en la misma red.
- **Ropa**: pantalón ajustado — la doc avisa de que ropa holgada tapa los trackers y el tracking falla de forma impredecible.

---

## 4. Instalación del pipeline

### 4.1 PC de desarrollo (base común)

> ✅ **HECHO en este PC (2026-07-13)** — Ubuntu 24.04.4, 2× RTX PRO 6000 Blackwell, driver 580.159:
> - **TensorRT 10.13.3.9 (variante cuda-12.9)** extraído en `~/TensorRT`. Descarga directa sin login:
>   `https://developer.nvidia.com/downloads/compute/machine-learning/tensorrt/10.13.3/tars/TensorRT-10.13.3.9.Linux.x86_64-gnu.cuda-12.9.tar.gz`
> - **CUDA toolkit 12.9.1 en espacio de usuario** en `~/cuda-12.9` (runfile con `--silent --toolkit --toolkitpath=$HOME/cuda-12.9`, **sin sudo**, driver intacto). Necesario porque el nvcc 12.0 de los repos de Ubuntu no soporta Blackwell (sm_120) y TensorRT cuda-12.9 necesita un `libcudart` 12.9.
> - En `~/.bashrc`: `TensorRT_ROOT=$HOME/TensorRT`, `CUDAToolkit_ROOT=$HOME/cuda-12.9`, y `~/TensorRT/lib` + `~/cuda-12.9/lib64` en `LD_LIBRARY_PATH`.
> - Verificado: `trtexec --onnx=.../mnist.onnx` → **PASSED** en la GPU 0.
> - Instaladores conservados en `~/` (`TensorRT-*.tar.gz` 6,5 GB, `cuda_12.9.1_linux.run` 4,5 GB) — se pueden borrar.

**TensorRT 10.13 (x86_64)** — descarga el tar de [developer.nvidia.com/tensorrt](https://developer.nvidia.com/tensorrt/download/10x):

```bash
sudo apt-get install -y pv
pv TensorRT-*.tar.gz | tar -xz -f -
mv TensorRT-* ~/TensorRT
echo 'export TensorRT_ROOT=$HOME/TensorRT' >> ~/.bashrc && source ~/.bashrc
```

> ⚠️ **Versiones exactas obligatorias**: TensorRT **10.13** en x86 y **10.7** en Jetson. La doc avisa de que otra versión "produce resultados de inferencia incorrectos".
> ⚠️ **En este PC (Blackwell)**: no dejar que `install_deps.sh` instale CUDA 12.4 por apt — ya hay CUDA 12.9 en `~/cuda-12.9` vía `CUDAToolkit_ROOT`.

**Repo:**

```bash
git clone https://github.com/NVlabs/GR00T-WholeBodyControl.git
cd GR00T-WholeBodyControl
git lfs pull
```

**Build del deployment C++:**

```bash
cd gear_sonic_deploy
chmod +x scripts/install_deps.sh
./scripts/install_deps.sh
source scripts/setup_env.sh
echo "source $(pwd)/scripts/setup_env.sh" >> ~/.bashrc
just build
```

*Alternativa Docker* (ROS2 Humble, x86 y Jetson): `./docker/run-ros2-dev.sh` (flags `--rebuild`, `--with-opengl`), y dentro del contenedor `source scripts/setup_env.sh && just build`.

**Modelos (ONNX de SONIC, repo público `nvidia/GEAR-SONIC` en Hugging Face):**

```bash
pip install huggingface_hub
python download_from_hf.py        # deja encoder/decoder/planner en gear_sonic_deploy/
```

Estructura resultante: `gear_sonic_deploy/policy/release/{model_encoder.onnx, model_decoder.onnx, observation_config.yaml}` + `planner/target_vel/V2/planner_sonic.onnx`. Flags útiles: `--low-latency`, `--sample`, `--training` (~30 GB, solo si vas a entrenar).

**Entornos Python** (venvs separados):

```bash
# Entorno de teleop PICO (Python 3.10 + SDKs)
bash install_scripts/install_pico.sh
source .venv_teleop/bin/activate

# Entorno del simulador MuJoCo (.venv_sim) — según Quick Start del repo
```

### 4.2 Casco y trackers (paso a paso)

**Paso 0 — Preparación**
- Casco en la **misma WiFi** que el PC (Settings → WLAN).
- Actualizar PICO OS (Settings → System Update); las guías de teleop piden ≥ 5.15.x para el enhanced tracking de los trackers.

**Paso 1 — Modo desarrollador**
- **Settings → General → Developer** → activar **Developer Mode** y **USB Debugging**.
- Si "Developer" no aparece: **Settings → General → About** → pulsar ~7 veces sobre la versión de software para desbloquearlo (unidades consumer; las Enterprise lo traen visible).

**Paso 2 — Instalar el APK del cliente**
- Vía navegador del casco: ir a `github.com/XR-Robotics/XRoboToolkit-Unity-Client/releases`, descargar **`XRoboToolkit-PICO-1.1.1.apk`** (v1.1.1), instalar desde descargas/File Manager. La app aparece en **Library → Unknown**.
- Alternativa: `adb install XRoboToolkit-PICO-1.1.1.apk` por USB (requiere USB Debugging).

**Paso 3 — Emparejar los motion trackers** (app preinstalada **"PICO Motion Tracker"**)
1. Poner cada tracker en modo pairing: mantener su botón (~6 s, parpadeo rojo/azul).
2. En la app: **Connect Tracker** con el tracker cerca del casco. Azul fijo = conectado. Repetir con el 2º.
3. Seleccionar el modo de **2 trackers en tobillos** (tracking de piernas / full body con 2 unidades).
4. Colocarlos en los tobillos con el **LED hacia arriba** y hacer la calibración de la app (mirar hacia los trackers). **Pantalón ajustado.**

**Paso 4 — PC Service y app XRoboToolkit**
1. En el PC: instalar y **arrancar antes que nada** el **XRoboToolkit PC Service** — `XRoboToolkit_PC_Service_1.0.0_ubuntu_22.04_amd64.deb` (o `24.04`; `roboticsservice_1.0.0.0_arm64.deb` para Jetson).
2. Abrir **XRoboToolkit** en el casco → seleccionar la **IP del PC** → estado **"WORKING"**.
3. Configurar en el panel: Head tracking **ON**, Controller tracking **ON**, **Body tracking mode = "PICO Motion Tracker" (full body → 24 joints)**, Number of trackers = **2**. El toggle "Switch w/ A Button" pausa/reanuda el streaming con el botón A.

**Paso 5 — Verificación**
- El PC Service debe mostrar el casco conectado. Comprobar el esqueleto con el streamer: `pico_manager_thread_server.py --manager --vis_vr3pt --vis_smpl` (visualiza los 3 puntos VR y el SMPL estimado).

**Gotchas conocidos**
- En varios flujos de XRoboToolkit hay que **mantener apretado el grip** de los mandos para que se acepten los datos de brazos (hombre muerto anti-movimientos accidentales).
- Las cámaras passthrough (VST) requieren aprobación enterprise de PICO — no se necesitan para este teleop.
- Subir el timeout de pantalla del casco para que no se duerma en sesión.
- Si se elige modo "object tracking" en vez de full body, el PC solo recibe los trackers sueltos, no las 24 articulaciones.

> ✅ **HECHO en este PC (2026-07-13), resto del 4.1:**
> - `install_deps.sh` ejecutado (cppzmq, nlohmann/json, `just` 1.43, ONNX Runtime 1.16.3 en `/opt/onnxruntime`).
> - `just build` → 100% OK, binarios en `gear_sonic_deploy/target/release/` (`g1_deploy_onnx_ref`, etc.). Sin ROS2 (no necesario para teleop ZMQ).
> - Modelos SONIC descargados de `nvidia/GEAR-SONIC` + `--sample` (6 PKL en `sample_data/`).
> - `.venv_sim` y `.venv_teleop` instalados (Python 3.10, unitree-sdk2py, CycloneDDS).
> - **Smoke test OK**: `echo Y | ./deploy.sh --input-type zmq_manager sim` construyó los engines TensorRT (`*.trt` junto a los ONNX) y quedó esperando el LowState de MuJoCo — comportamiento correcto sin simulador. Ojo: `deploy.sh` pide confirmación interactiva (`Proceed? [Y/n]`).
> - El unit test `run_tests` falla por un fixture no distribuido (`reference/bones_072925_test/`) — no bloqueante.

### 4.3 Fase 1 — Prueba en simulación (MuJoCo, sin robot)

Todo el pipeline se valida con el casco y los trackers reales contra MuJoCo. Tres terminales en el PC:

```bash
# Terminal 1 — simulador MuJoCo
source .venv_sim/bin/activate      # o el venv que cree el quickstart
python gear_sonic/scripts/run_sim_loop.py

# Terminal 2 — política WBC (TensorRT)
cd gear_sonic_deploy
source scripts/setup_env.sh
./deploy.sh --input-type zmq_manager sim

# Terminal 3 — streamer PICO
source .venv_teleop/bin/activate
python gear_sonic/scripts/pico_manager_thread_server.py --manager --vis_vr3pt --vis_smpl
```

Si el streamer corre en otra máquina que el deployment: añadir `--zmq-host <IP-de-la-máquina-del-streamer>` al deployment (por defecto `localhost`).

**Calibración y controles** (igual en sim y en real):

| Acción | Comando |
|---|---|
| Postura de calibración | De pie, pies juntos, brazos pegados, antebrazos 90° hacia delante (forma de L), palmas hacia dentro |
| Calibración completa + activar política | **A + B + X + Y** |
| Entrar en modo POSE (teleop cuerpo completo SMPL) | **A + X** |
| Volver a idle (planner) | **A + X** de nuevo |
| Parada / e-stop | **A + B + X + Y** (o tecla **O** en el PC) |

Recomendación de la propia doc: dominar los controles en MuJoCo antes de tocar el robot.

### 4.4 Fase 2 — Robot real (G1)

**a) Flashear el Orin NX del G1 a JetPack 6.2** (guía `references/jetpack6.html` del repo):

1. Desmontar: quitar el asa trasera (llave Allen 5 mm, hex 2 mm, Phillips), extraer el SSD NVMe del Orin NX. **Hacer backup antes.**
2. Escribir la imagen desde un PC con el SSD en un adaptador externo:
   ```bash
   bzip2 -dc g1-nx-j6.2.img.bz2 | sudo dd of=/dev/sda bs=4M   # ⚠️ verificar el dispositivo
   ```
3. Poner el robot en modo flasheo (mantener los dos botones blancos, soltar el superior, mantener el inferior ~2 s hasta que 3 luces pasen a 2) y ejecutar los scripts de flasheo (~8 min).
4. Reensamblar y configurar:
   ```bash
   sudo nvpmodel -m 0                                          # modo maxn
   sudo apt-get install nvidia-l4t-dla-compiler libcudla-dev-12-6
   ```

**b) Instalar el stack en el Orin** (mismos pasos que §4.1 pero con **TensorRT 10.7** para JetPack 6 / CUDA 12.6): clonar repo, `install_deps.sh`, `setup_env.sh`, `just build`, descargar modelos ONNX.

**c) Lanzar teleop real:**

```bash
# En el Orin del G1 — política WBC contra el robot
cd gear_sonic_deploy && source scripts/setup_env.sh
./deploy.sh --input-type zmq_manager real --zmq-host <IP-del-PC-del-streamer>

# En el PC — XRoboToolkit PC Service corriendo + streamer
python gear_sonic/scripts/pico_manager_thread_server.py --manager
```

Misma calibración y combos que en simulación.

**Seguridad:** robot colgado del arnés/soporte en las primeras pruebas; e-stop (**A+B+X+Y** / tecla **O**) siempre a mano; el deployment incluye monitor de errores de motor con avisos TTS.

---

## 5. Problemas conocidos / avisos

**Incidencias resueltas en este PC (2026-07-13):**
- **MuJoCo a cámara lenta (ventana fluida, física lenta)** — causa raíz real: la sesión de trabajo es **TurboVNC** (`Xvnc :1`), un X virtual que renderiza OpenGL con llvmpipe (CPU) por diseño. El bucle del sim (`base_sim.py`) corre física a 200 Hz y llama a `viewer.sync()` cada 4 pasos sin recuperar tiempo perdido → con render por CPU no llega a tiempo real. **Fix: VirtualGL** (`virtualgl_3.1.4_amd64.deb`, instalado 2026-07-13) — lanzar el sim con `vglrun -d egl0 python gear_sonic/scripts/run_sim_loop.py` (usa la GPU vía EGL; requiere grupos `video`/`render`, ya concedidos). El deployment C++ no usa GL y no necesita vglrun. Verificación: `vglrun -d egl0 glxinfo -B | grep renderer` → NVIDIA. Nota: también había una errata real en GRUB (`nvidia_drm.modset=1` → corregida a `modeset` + `update-grub` + reboot), que arregló la aceleración de la **consola física**, pero no afecta a las sesiones VNC. Mitigación alternativa sin GPU: subir `VIEWER_DT` (0.02→0.05) en `gear_sonic/utils/mujoco_sim/wbc_configs/g1_29dof_sonic_model12.yaml`.
- **"No puedo escribir en las terminales"**: el handler de teclado del deployment pone stdin en modo raw sin eco (termios). Mientras corre es normal no ver lo tecleado (las teclas actúan igual). Si el proceso muere sin salir con `O`, la terminal queda rota → `stty sane` (a ciegas) o `reset`. Salir siempre con `O`.
- **Caché de Hugging Face propiedad de root** (por Docker antiguos): `sudo chown -R $USER:$USER ~/.cache/huggingface`.
- **`deploy.sh` pide confirmación interactiva** (`Proceed? [Y/n]`) — para scripts: `echo Y | ./deploy.sh …`.
- **La app del casco no conecta con el PC Service ("no se conectan los sockets")**: era el firewall (ufw activo). El PC Service escucha en **TCP 63901** (conexión del casco, posiblemente dinámico entre arranques) y **UDP 49456** (discovery); el gRPC local (TCP 60061, solo 127.0.0.1) no necesita regla. Fix aplicado (2026-07-13): `sudo ufw allow from <IP_ESTACION_WIFI>/24` (subred WiFi del lab). El casco debe tener IP en la misma subred que la interfaz WiFi del PC (<IP_ESTACION_WIFI>). PC Service instalado: `XRoboToolkit_PC_Service_1.0.0_ubuntu_24.04_amd64.deb` → `/opt/apps/roboticsservice/` (proceso `RoboticsServiceProcess`).

**Incidencias resueltas (2026-07-14) — la saga del "esqueleto convulsionando":**
- **🏆 CAUSA RAÍZ: EL IDIOMA DEL CASCO (bug de separador decimal).** Con el PICO en **español**, la app XRoboToolkit (Unity) serializa las poses como strings con `ToString()` sensible a la cultura → decimales con **coma** (`0,123`). El binding del PC (`py_bindings.cpp::stringToPoseArray`) separa los campos **por comas** → cada número se parte en `[parte entera, decimales como entero gigante]` → cuaterniones con norma ~10⁸, posiciones de millones de metros → esqueleto SMPL convulsionando y robot loco, mientras el avatar nativo del PICO se ve perfecto (nunca sale del casco). Los mandos no se ven afectados (van como números JSON, no strings). **Fix: Ajustes → General → Idioma → English (United States)** + cerrar del todo y reabrir la app. **CONFIRMADO** (diagnóstico con `~/TFM/diag_body.py`: norma de quats pasó de 10⁸ a exactamente 1.000). Probablemente es la causa del issue abierto NVlabs/GR00T-WholeBodyControl#130 — pendiente de reportar a XR-Robotics/XRoboToolkit-Unity-Client.
- **Calibración envenenada por frames basura**: si se pulsa A+B+X+Y justo tras conectar (stream aún inestable o datos corruptos), la línea `Calibration captured` muestra offsets absurdos (p.ej. Z de -43 millones de m) y todo lo posterior sale mal. La referencia del cuello **se conserva entre recalibraciones** → una calibración mala exige **reiniciar el terminal 3**. Regla: esperar 3-4 líneas seguidas de `[PicoReader] dt_ts ~11-15 ms / fps ~90` con el casco puesto, calibrar, y **verificar que los offsets impresos son < ±0.5 m** antes de pulsar A+X.
- **El streamer (T3) debe lanzarse con la app del casco YA conectada** — si arranca antes, el SDK nunca ve el dispositivo y se queda en `waiting for body data` para siempre.
- **T2 correcto: `bash deploy.sh sim`** a secas (default = `--input-type zmq_manager`, localhost:5556). ¡OJO!: `--input-type zmq` es OTRO protocolo (un solo topic `pose`, sin topic `command`) → los botones del mando no hacen nada.
- **T3 también necesita `vglrun -d egl0`**: la visualización PyVista renderizaba por llvmpipe en VNC (75 ms/frame) y estrangulaba el PoseLoop a 11 FPS (target 50). Con VirtualGL: 7.6 ms y ~50 FPS.
- **Quitarse el casco = sesión muerta**: el sensor de proximidad lo duerme y la app se desconecta (`device missing`). Para leer la pantalla durante una sesión: mirar por el hueco de la nariz, o desactivar el reposo automático.
- **Pico 4 Ultra por cable**: adaptador USB-C→Ethernet al segundo puerto libre del PC (`eno1`). Config: `sudo nmcli con add type ethernet ifname eno1 con-name pico-direct ipv4.method shared && sudo nmcli con up pico-direct && sudo ufw allow from 10.42.0.0/24` → PC = 10.42.0.1, el casco recibe IP por DHCP (10.42.0.x), conectar la app a **10.42.0.1** y desactivar el WiFi del casco. Ping medio 3.3 ms (vs. parones de 100-800 ms por el WiFi del lab). Los trackers no se ven afectados (enlace propio con el casco).
- **Workstation compartida cargada** (colmap de otro usuario ocupando 11+ núcleos, load ~25-30): los procesos Python a nice 5 sufren *scheduling jitter* — se nota como dt del PicoReader en múltiplos de ~11 ms. Convivible, pero para sesiones críticas conviene coordinarse.

- **TensorRT exacto** (10.13 x86 / 10.7 Jetson) — no negociable.
- **Pantalón ajustado** para los trackers de tobillo.
- Puerto **ZMQ 5557** en el Orin: hay issues conocidos de binding (revisar que no esté ocupado).
- WiFi congestionada = latencia y tracking a saltos; router dedicado si es posible.
- El PC Service debe arrancar **antes** que la app del casco.
- Flashear el Orin del G1 es invasivo (desmontaje físico + `dd`): backup del SSD original y verificar bien `/dev/sdX`.

---

## 6. Contexto: alternativas descartadas/complementarias

| Opción | Estado |
|---|---|
| **unitree xr_teleoperate** | Ya probado y funcionando. Pico 4 Ultra vía WebXR, IK de tren superior (pinocchio) + locomoción básica. **No es WBC de cuerpo completo.** Útil más adelante para grabar demos IL (unitree_IL_lerobot). |
| **Workflow e2e de NVIDIA (CloudXR in-process)** | Requiere **Jetson AGX Thor** como mochila en el G1. Es la única ruta que necesita Thor — descartada. |
| **Isaac Lab CloudXR teleop (simulación)** | Para teleoperar Isaac Lab con el casco. Pico 4 Ultra solo en **Early Access** de CloudXR (NGC) y exige workstation muy potente (RTX 5090-class, 64 GB RAM, Docker, 45 FPS sostenidos). El sim2sim en MuJoCo de GR00T-WBC es mucho más accesible. |
| **Cara al TFM** | SONIC puede quedar como controlador de bajo nivel sobre el que una política IL/RL de alto nivel (manipulación de válvula) manda objetivos; el mismo repo cubre después recolección de datos y fine-tune de GR00T N1.7. |

---

## 7. Fuentes

- [GR00T-WholeBodyControl (repo)](https://github.com/NVlabs/GR00T-WholeBodyControl) · [Docs](https://nvlabs.github.io/GR00T-WholeBodyControl/)
- [VR Teleop Setup (PICO)](https://nvlabs.github.io/GR00T-WholeBodyControl/getting_started/vr_teleop_setup.html) · [PICO VR Whole-body Teleop](https://nvlabs.github.io/GR00T-WholeBodyControl/tutorials/vr_wholebody_teleop.html)
- [Installation (Deploy)](https://nvlabs.github.io/GR00T-WholeBodyControl/getting_started/installation_deploy.html) · [Download Models](https://nvlabs.github.io/GR00T-WholeBodyControl/getting_started/download_models.html) · [Quick Start](https://nvlabs.github.io/GR00T-WholeBodyControl/getting_started/quickstart.html) · [JetPack 6 (G1 Orin)](https://nvlabs.github.io/GR00T-WholeBodyControl/references/jetpack6.html)
- [GEAR-SONIC en Hugging Face](https://huggingface.co/nvidia/GEAR-SONIC)
- [XRoboToolkit PC Service](https://github.com/XR-Robotics/XRoboToolkit-PC-Service) · [XRoboToolkit Unity Client (APK)](https://github.com/XR-Robotics/XRoboToolkit-Unity-Client/releases) · [Paper XRoboToolkit](https://arxiv.org/html/2508.00097v1) · [Guía práctica Pico 4 Ultra](https://www.akshayparkhi.net/2026/Mar/4/xr-robotics-with-pico-4-ultra-vr-teleoperation-setup-from-headse/) · [Setup Pico 4 Ultra + trackers (PNDbotics wiki)](https://wiki.pndbotics.com/en/teleoperation/mocap/pico/)
- [NVIDIA e2e G1 teleop (ruta Thor)](https://docs.nvidia.com/learning/physical-ai/gr00t-e2e-workflow/latest/real-robot-workflow/real-teleop.html) · [Isaac Lab CloudXR Teleoperation](https://isaac-sim.github.io/IsaacLab/main/source/how-to/cloudxr_teleoperation.html)
- [Kit RoboStore G1 + Pico 4 Ultra](https://robostore.com/products/unitree-g1-teleoperation-kit) · [Blog del kit](https://robostore.com/blogs/news/full-body-teleoperation-for-unitree-g1-using-vr-and-nvidia-gr00t)
- [PICO Motion Tracker (Swift)](https://www.knoxlabs.com/products/pico-motion-tracker)
- [unitree xr_teleoperate](https://github.com/unitreerobotics/xr_teleoperate)
