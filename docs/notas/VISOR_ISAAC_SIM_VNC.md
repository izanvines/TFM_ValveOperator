# Ver la simulación de Isaac Sim desde la workstation VNC — Diagnóstico completo

Cómo conseguir **imagen interactiva** de un entorno de Isaac Lab-Arena (`g1_valve`) cuando se
trabaja contra la workstation por **TurboVNC**, y por qué el camino "obvio" (abrir la ventana
nativa de Isaac Sim) es **imposible** en este montaje.

Verificado funcionando el **2026-07-27**: el usuario ve el G1 y la válvula, con el fondo
Gaussian Splatting de la oficina cargado en la escena.

> Este documento es el post-mortem de una sesión de depuración larga en la que se encontraron
> **cinco causas independientes** apiladas. Cada una por separado producía el mismo síntoma
> —pantalla negra— lo que hacía muy difícil aislarlas. Se documentan todas, con la evidencia
> concreta que las confirmó, para no volver a pasar por aquí.

---

## TL;DR — receta que funciona

**Servidor** (dentro del contenedor `isaaclab_arena-latest`):

```bash
unset DISPLAY
export HOME=/home/ivines
cd /workspaces/isaaclab_arena

/isaac-sim/python.sh isaaclab_arena/evaluation/policy_runner.py \
  --livestream 2 \
  --viz kit \
  --kit_args="--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0 \
--/exts/omni.kit.livestream.app/primaryStream/allowDynamicResize=true \
--/exts/omni.kit.livestream.app/primaryStream/signalPort=49100 \
--/exts/omni.kit.livestream.app/primaryStream/streamPort=47998 \
--/exts/omni.kit.livestream.app/primaryStream/publicIp=<IP_ESTACION>" \
  --policy_type zero_action --num_steps 100000000 \
  g1_valve --embodiment g1_wbc_agile_pink --background office_gs
```

**Cliente** (`Isaac Sim WebRTC Streaming Client`, lanzado en la sesión VNC):

```bash
env -u LD_PRELOAD DISPLAY=:1 XAUTHORITY=/home/ivines/.Xauthority \
  "/opt/Isaac Sim WebRTC Streaming Client/isaacsim-webrtc-streaming-client" \
    --disable-features=WebRtcHideLocalIpsWithMdns \
    --disable-gpu --disable-gpu-compositing --no-sandbox
```

Y en la UI del cliente: Server **`<IP_ESTACION>`** (la IP de cable, **no** `127.0.0.1`),
Signal `49100`, Stream `47998` → Connect.

Los dos parámetros críticos, y los menos evidentes de todos, son **`--viz kit`** y
**`publicIp=<IP de cable>`**.

---

## Las cinco causas, en el orden en que se destaparon

### 1. Los assets se descargaban de S3 y la red los estrangula

**Síntoma**: la escena se quedaba colgada minutos y acababa en
`FileNotFoundError: Unable to open the usd file ... default_environment.usd`.

**Causa**: `isaaclab/utils/assets.py::_parse_kit_asset_root()` lee el valor de
`persistent.isaac.asset_root.cloud` de los ficheros `apps/isaaclab.python*.kit` y de ahí saca
todo (suelo, robot G1, modelo del WBC). Apuntaba a S3 y la red corporativa lo limita a
~12 KB/s. **No existe variable de entorno para sobreescribirlo**: hay que editar los `.kit`.

**Arreglo**: espejo local de assets + repuntar los seis `.kit`.

```
/home/ivines/datasets/isaac_assets/     (visible en el contenedor como /datasets/isaac_assets)
└── Assets/Isaac/6.0/Isaac/
    ├── Environments/Grid/default_environment.usd          ← bajado por WiFi
    ├── Samples/Groot/Robots/g1_29dof_with_hand_rev_1_0.usd ← de GR00T-WholeBodyControl
    └── IsaacLab/Arena/wbc_policy/robot_model/g1/           ← urdf + 65 STL, de decoupled_wbc
        ├── g1_29dof_with_hand.urdf
        └── meshes/
```

Ficheros modificados (tienen backup `.s3bak` al lado):
`isaaclab.python.kit`, `.headless.kit`, `.rendering.kit`, `.headless.rendering.kit`,
`.xr.openxr.kit`, `.xr.openxr.headless.kit` — todos con:

```
persistent.isaac.asset_root.cloud = "/datasets/isaac_assets/Assets/Isaac/6.0"
```

**Resultado**: la escena carga en ~8 s y **sin red**. Queda como efecto colateral que faltan
texturas del grid del suelo (`Wireframe_blue.png`), lo que produce errores `[UsdToMdl]` en el
log: son inofensivos, el suelo sale sin textura.

> Este arreglo es también la razón de que el proyecto ya no dependa de la VPN para arrancar.

---

### 2. La ventana nativa de Isaac Sim en VNC es IMPOSIBLE (no es configuración)

Esto se dio por cerrado con una prueba directa, no por descarte. `vkcube` es una aplicación
Vulkan mínima; si ella no puede pintar, Isaac Sim tampoco:

```console
$ DISPLAY=:1 vkcube
Selected GPU 0: NVIDIA RTX PRO 6000 Blackwell Max-Q, type: DiscreteGpu
Could not find both graphics and present queues
```

**Causa**: al `Xvnc` de TurboVNC le falta la extensión **DRI3**:

```console
$ DISPLAY=:1 xdpyinfo -queryExtensions | grep -E 'DRI3|Present|GLX'
    GLX  (opcode: 150...)
    MIT-SHM  (opcode: 130...)
    Present  (opcode: 147)          ← DRI3 NO aparece
```

Sin DRI3 el driver propietario de NVIDIA no expone cola de presentación para superficies X11,
así que **ninguna** app Vulkan puede abrir ventana acelerada ahí. Isaac Sim presenta por Vulkan.

**VirtualGL no lo salva**: la 3.1.4 instalada solo trae interposer de OpenGL/EGL
(`/usr/lib/libvglfaker*.so`), **no hay capa Vulkan** ni en
`/usr/share/vulkan/implicit_layer.d/`. VirtualGL arregla GLX/OpenGL —y de hecho funciona—
pero no toca Vulkan.

**Conclusión**: la única vía de imagen interactiva es **streaming** (WebRTC o XR). Deja de
buscar `vglrun`, flags de Kit o ajustes de TurboVNC: no existen.

---

### 3. El display del usuario es `:1`, no `:2`

```console
$ ps aux | grep Xvnc
ivines     3224  ... /opt/TurboVNC/bin/Xvnc :1 ... -rfbport 5901
alombra+   6156  ... /opt/TurboVNC/bin/Xvnc :2 ... -rfbport 5902   ← ¡otro usuario!
eapaola+  36625  ... /opt/TurboVNC/bin/Xvnc :3 ... -rfbport 5903
```

La workstation es **compartida**. Lanzar una GUI en `:2` la abre en el escritorio de otra
persona, no en el tuyo — y tú ves "no pasa nada". **Comprueba siempre el display antes**:

```bash
ps aux | grep "[X]vnc" | grep $USER
```

---

### 4. `--viz kit` — sin él no hay viewport que transmitir

**El más traicionero de todos.** El servidor reportaba salud perfecta:

```
Processed static resize of video stream to 1920x1080
Client connected to WebRTC server
Client disconnected from WebRTC server        ← 51 s después
```

Cero errores, GPU al 66%, encoder disponible. Pero en el volcado de configuración del entorno:

```python
sim=SimulationCfg(..., visualizer_cfgs=[])    ← VACÍO
```

**Causa**: `--viz` es un flag de IsaacLab (alias de `--visualizer`). De
`app_launcher.py:265`:

> *"To run headless by default, **omit `--viz`**. To force headless when config visualizers may
> be enabled, use `--viz none`."*

Es decir, **omitir `--viz` = sin visualizadores**. El visualizador `kit` (`KitVisualizer`) es
el que crea y alimenta el viewport de Kit. Sin él, `--livestream 2` monta el stream, negocia
con el cliente y transmite... un framebuffer vacío. **Negro perfecto, sin un solo error.**

**Evidencia de que el flag hace algo**: el ritmo de simulación cayó de **20.7 → 13.3 step/s**
al añadir `--viz kit`. Ese coste es exactamente el renderizado del viewport que antes no
ocurría.

**Por qué "una vez funcionó"**: la sesión que funcionó (2026-07-23, ver
[TELEOP_G1_VALVE.md](TELEOP_G1_VALVE.md)) usaba `teleop.py` **en modo XR**. XR fuerza el
renderizado por su cuenta (`_resolve_xr_settings` corre antes que el forzado de headless y lo
impide), así que allí sí había contenido. Al pasar a `policy_runner.py` sin XR se perdió el
viewport sin que nada lo avisara.

---

### 5. Tailscale envenenaba la negociación ICE

Con el viewport ya renderizando, seguía saliendo negro. La pista estaba en el **log del
proceso cliente** (no en su `main.log`, sino en su salida estándar):

```
ERROR:third_party/webrtc/p2p/base/port.cc:392]
Port[...:host:Net[tailscale0:100.115.70.x/32:Ethernet:id=4]]:
Received non-STUN packet from unknown address: 100.115.70.x:47998
```

**Lectura**: el vídeo **sí llegaba** (paquetes desde el puerto `47998`), pero viajaba por la
interfaz de **Tailscale**, y WebRTC los descartaba porque esa dirección no era una candidata
ICE validada. La máquina tiene cinco interfaces:

```
enp101s0        <IP_ESTACION>/24     ← cable (la buena)
wlp100s0        <IP_ESTACION_WIFI>/24    ← WiFi
tailscale0      100.115.70.117/32   ← VPN, la culpable
docker0         172.17.0.1/16
br-ee1db8fb5c58 172.18.0.1/16
```

Con `publicIp` vacío, Kit ofrece candidatas de todas ellas y el emparejamiento se iba por la VPN.

**Arreglo**: fijar la interfaz correcta.

```
--/exts/omni.kit.livestream.app/primaryStream/publicIp=<IP_ESTACION>
```

Y en el cliente, poner esa misma IP como Server (**no** `127.0.0.1`: la candidata anunciada
debe coincidir con la que se contacta).

---

## Cosas que se probaron y NO eran el problema

Se dejan anotadas para no repetirlas:

| Sospecha | Cómo se descartó |
|---|---|
| NVENC no disponible en el contenedor | `NVIDIA_DRIVER_CAPABILITIES=all` y `libnvidia-encode.so.595.84` presente |
| Puertos de señalización mal | El cliente logueaba `Stream started - status=success`; el servidor, `Client connected` |
| `ufw` bloqueando el vídeo | Está activo con `DEFAULT_INPUT_POLICY="DROP"`, pero los paquetes UDP **sí llegaban** (por la interfaz equivocada). Solo importa para conectar **desde otra máquina** |
| Electron sin GPU en VNC | Plausible, pero el negro persistía; los flags `--disable-gpu` se dejaron igualmente porque no estorban |
| Resize dinámico rechazado | `allowDynamicResize=true` quita un warning, no arregla el negro |
| El Gaussian Splat tapando la cámara | El negro era idéntico con la escena diáfana |

---

## Cómo diagnosticar la próxima vez (dónde mirar)

Tres fuentes, en este orden:

1. **Log del cliente** — `~/.config/Isaac Sim WebRTC Streaming Client/logs/main.log`
   Dice si la sesión se establece y cuánto dura. El patrón
   `started: success` → `stopped: error` a los ~50 s significa **sesión OK, media que no llega**.

2. **Salida estándar del proceso cliente** — hay que lanzarlo desde terminal para verla.
   Aquí es donde aparecen los errores de ICE/STUN de WebRTC. **Este fue el log que resolvió
   el caso**; no está en `main.log`.

3. **Log de Kit** — dentro del contenedor, `/isaac-sim/kit/logs/Kit/IsaacLab/3.0/kit_*.log`.
   Mucho más detallado que stdout. Filtrar por `livestream|webrtc|stun|ice|nvenc`.

**Prueba objetiva de si se está codificando vídeo** (parte el problema en dos limpiamente):

```bash
nvidia-smi --query-gpu=index,utilization.gpu,utilization.encoder --format=csv,noheader
```

Medición real del momento en que funcionó:

```
14:48:53  conns=2   GPU 66%   encoder 0%    ← sin cliente conectado
14:48:59  conns=3   GPU 67%   encoder 1%    ← el cliente conecta: NVENC arranca
14:49:30  conns=3   GPU 65%   encoder 3%    ← codificando de forma sostenida
```

Si `encoder` se queda a 0% con un cliente conectado, el problema es **anterior al transporte**
(típicamente: no hay viewport → falta `--viz kit`). Si sube, el vídeo sale y el problema está
en el transporte o en el cliente.

---

## Conectar desde otro equipo de la red

El portátil (`<IP_PORTATIL>`) está en la misma `/24` que la workstation por cable
(`<IP_ESTACION>`). Como `ufw` está activo con política `DROP`, hay que abrir los dos puertos:

```bash
sudo ufw allow from <SUBRED_LAN> to any port 49100 proto tcp
sudo ufw allow from <SUBRED_LAN> to any port 47998 proto udp
sudo ufw status numbered
```

Se limita a la subred local a propósito, en vez de abrirlo a todo el mundo.

**Aviso**: no funciona a través del túnel SSH que se usa para el VNC. SSH no tunela UDP y el
vídeo WebRTC es UDP → saldría negro. Tiene que ser conexión directa a `<IP_ESTACION>`.

---

## Fondo Gaussian Splatting de la oficina

El fondo está registrado como `office_gs` en
`isaaclab_arena/assets/background_library.py` y se activa con `--background office_gs`.
Es visual puro (`ObjectType.BASE` → sin colisión).

Alinearlo costó destapar **tres errores encadenados**, todos por fiarse de metadatos del USD
que están mal. La medición correcta sale de la **trayectoria de la cámara de captura**
(`/World/gauss/Cameras/camera_0` tiene 252 `timeSamples`), que es dato real, no declarado:

```
X: -7.07 ..  4.77   (rango 11.84 m)
Y: -0.49 ..  0.27   (rango  0.76 m)   ← eje casi constante
Z: -3.75 ..  8.92   (rango 12.67 m)
recorrido total: 93.33 m
```

Alguien paseando 93 m por una sala de ~12 × 12 m. De ahí salen los tres errores:

**a) El `extent` del USD es basura.** Declara ~8900 × 13466 × 10686 unidades, y como
`metersPerUnit = 1.0` eso serían kilómetros. Es un *bound* nominal inflado: los datos reales de
las gaussianas no están en el USD sino en `export_sh_optimized.nurec`, y el `extent` no los
refleja. La `xformOp:transform` del `Volume` es **rotación pura** (escala 1.0, traslación 0),
así que no hay corrección métrica escondida en ninguna parte. **La escala correcta es `1.0`.**
Calcular la escala a partir del extent daba `0.001` y encogía la oficina a un milímetro.

**b) El dato es Y-down, aunque el USD declare `upAxis = "Z"`.** Se ve en que el eje casi
constante de la trayectoria es Y (una persona andando mantiene la altura), y se confirma con la
orientación de la cámara: su vector "arriba" medio es `(0, -0.927, 0)`, o sea **−Y**. Formato
típico de COLMAP. Hace falta un giro de **−90° sobre X** para mapear −Y → +Z.

**c) El cuaternión se pasa como `wxyz`, no como `xyzw`.** En `object_base.py:83`:

```python
self.object_cfg.init_state.rot = initial_pose.rotation_xyzw   # ← sin conversión
```

El tuple va **tal cual** a IsaacLab, que lo interpreta como `(w, x, y, z)`. O sea que el
"identity" `0,0,0,1` era en realidad `w=0, z=1` = **giro de 180° en yaw**. El nombre del campo
miente; lo que se escriba en `OFFICE_GS_ROT` llega a IsaacLab como **wxyz**.

Valores correctos resultantes:

| Variable | Valor | Qué hace |
|---|---|---|
| `OFFICE_GS_USD` | `/datasets/office_gs/export_sh_optimized.usdz` | Ruta al splat |
| `OFFICE_GS_SCALE` | `1.0` | El dato ya está en metros |
| `OFFICE_GS_ROT` | `0.7071,-0.7071,0,0` | **wxyz** = −90° sobre X (Y-down → Z-up) |
| `OFFICE_GS_POS` | `1.152,-2.584,1.390` | Centra el recorrido de captura en el robot, con el suelo a z ≈ 0 (asume cámara a 1.5 m de altura) |
| `OFFICE_GS_LIGHT` | `300` | El splat lleva iluminación horneada; un dome alto lo lava a blanco |

La posición asume que quien grabó llevaba la cámara a ~1.5 m; si el suelo queda alto o bajo,
se ajusta el tercer componente de `OFFICE_GS_POS`.

> **Pendiente**: `object_base.py:83` debería convertir xyzw → wxyz, o el campo debería
> llamarse `rotation_wxyz`. Mientras no se arregle, cualquier rotación que se ponga en
> cualquier asset de Arena está silenciosamente mal interpretada.

---

## Estado y pendientes

- [x] Assets servidos en local, arranque sin red
- [x] Descartada definitivamente la ventana nativa en VNC (con prueba `vkcube`)
- [x] Streaming WebRTC funcionando en la workstation (robot + válvula visibles)
- [ ] Afinar la alineación del splat de la oficina (`OFFICE_GS_*`)
- [ ] Abrir puertos en `ufw` y validar la conexión desde el portátil
- [ ] Recuperar el modo XR/teleop con el fondo de la oficina cargado
- [ ] Grabar dataset con `record_demos.py` incluyendo el fondo
- [ ] Fine-tuning de GR00T

Documentos relacionados: [TELEOP_G1_VALVE.md](TELEOP_G1_VALVE.md) · [WBC.md](WBC.md) ·
[docs/acceso_remoto_vnc.md](docs/acceso_remoto_vnc.md)
