# Estado de la teleoperación XR — 2026-08-04

Dónde lo dejamos, qué está parcheado y por dónde seguir. Todo cerrado: sin procesos, GPUs libres.

## Cómo relanzar

```bash
# 1. Runtime de CloudXR, en una TERMINAL DE VERDAD (pide aceptar la EULA, se queda abierto)
docker exec -it -e HOME=/home/ivines isaaclab_arena-latest /isaac-sim/python.sh -m isaacteleop.cloudxr

# 2. La teleop (en segundo plano)
docker exec -d isaaclab_arena-latest bash -c \
  "/eval/arena_extras/launch_teleop_office.sh > /eval/run_teleop_office.log 2>&1"
```

Cliente: certificado primero en `https://<IP_ESTACION_WIFI>:48322/`, luego
`https://nvidia.github.io/IsaacTeleop/client` con **Server IP `<IP_ESTACION_WIFI>`** (WiFi; desde el
portátil por cable sería `<IP_ESTACION>`). **Una sola pestaña**, y si sale
`An active XRSession already exists`, **cerrar Chrome del todo** — no basta cerrar la pestaña.

Solo para mirar la escena sin gafas: `launch_arena_office.sh` (monitor en 49120/48020).

## Lo que FUNCIONA

- Splat de la oficina alineado y verificado contra el dato (cámaras de captura a 1,50 m de media,
  suelo a 0,58°, escala 1.0). Se ve bien en el viewport normal.
- **Recorte del splat: de 2 fps a 20 fps en XR.** Es la mejora grande del día.
- Teleop XR arranca, `Teleoperation started`, mandos detectados (`ControllerTracker
  initialized (left + right)`), cero errores.

## EL PROBLEMA ABIERTO

**El splat se ve mal SOLO en el producto de render de XR.** La misma cámara `XRCamera` se ve
**bien en el Viewport 2** (render mono normal) y **mal en el Viewport 1** (el que XR toma para
sí): pixelado, con zonas en negro. El robot y la válvula se ven perfectos en ambos.

### Hipótesis ya DESCARTADAS (no repetirlas)

| Hipótesis | Cómo se descartó |
|---|---|
| Ajustes `/rtx` distintos entre apps | Diff del árbol resuelto: **1 diferencia de 1255**, y era de streaming de texturas |
| `rendermode` = RealTimePathTracing | Era causa real de OTRO síntoma (sobreexposición) y está arreglado; el fallo XR persiste |
| DLSS forzado por `teleop.py` | Parcheado, `antialiasing_mode=None` verificado; sigue igual |
| Presupuesto de render / nº de gaussianas | El recorte subió a 20 fps pero **no cambió el aspecto** |
| Preset de render de XR | `renderQuality=off` ("Stage", usa los ajustes del stage): **sin efecto** |
| Estéreo en sí | Al principio parecía, pero el Viewport 2 con la misma cámara se ve bien |

### Por dónde seguir (en este orden)

1. **Subir el log del compositor NuRec, que es la única herramienta que no hemos usado**:
   `--/omni/rtx/nre/compositing/logLevel=<verboso>`. Los cuatro ajustes de ese namespace son
   `rendererHints`, `disableNuRecBackground`, `disableNuRecPostProcessings` y `logLevel`
   (los lee `librtx.hydra.so`). Que el compositor cuente qué hace en el producto XR.
2. **`rendererHints`**: lo forzamos a `0`; las apps de IsaacLab traen `3`. Nunca se probó `3` en
   XR. Es un bit-mask y su significado no está documentado en las cadenas del binario.
3. **`disableNuRecBackground`**: comprobar si algo lo activa en el camino XR.
4. **Averiguar si NuRec soporta multi-view/estéreo.** Si no lo soporta, no hay ajuste que valga y
   habría que replantear el fondo para XR (p. ej. malla en vez de gaussianas para la sesión de
   teleop, y splat solo para la grabación mono).

## PARCHES LOCALES — se pierden fácil, ojo

Los tres tienen `.bak` al lado. Los dos primeros están **dentro del repo** y se irían con un
`git checkout` o un `git submodule update`; el tercero vive en el contenedor y se va si lo
reconstruyes. **Ninguno está commiteado.**

| Fichero | Qué hace | Síntoma si desaparece |
|---|---|---|
| `submodules/IsaacLab/source/isaaclab_teleop/isaaclab_teleop/xr_anchor_manager.py` | Crea el prim del ancla XR con USD puro cuando `SingleXFormPrim` falla (IsaacLab sustituye el `SimulationManager` de Isaac Sim por su `PhysxManager`, que no implementa `_get_backend_utils`) | En el log: `Failed to create XR anchor prim`; en las gafas apareces a la altura de la **pelvis** en vez de un metro por debajo |
| `isaaclab_arena/scripts/imitation_learning/teleop.py` | Hace opcional el `antialiasing_mode="DLSS"` vía `ARENA_XR_ANTIALIASING`. Esa asignación acaba en `set_render_rtx_realtime()`, cuya primera línea fuerza `/rtx/rendermode=RealTimePathTracing` y pisa los `kit_args` | El log muestra `antialiasing_mode='DLSS'` en vez de `None`, y la escena sale sobreexpuesta |
| `lightwheel_sdk/client/client.py` (en el contenedor) | Reintentos ante fallo de red; sin él, un parpadeo mata el arranque de Arena **después** de minutos de carga | `lightwheel_sdk.client - ERROR - API request failed ... Microwave039` |

## Cosas que cuestan tiempo si se olvidan

- **`--enable_cameras` NO se puede usar con `teleop.py`**: borra las cámaras siempre que hay XR y
  deja colgado el término de observación → el entorno ni se crea. La cámara del robot llega con
  `record_demos.py --enable_cameras`, que es además la que se escribe en el HDF5.
- **Locomoción activa** ahora mismo (joystick izquierdo camina). Para grabar dataset hay que
  quitarla, como hace la tarea estática de la doc de NVIDIA.
- **En XR `FABRIC_TRANSFORMS` va a `true`**, al revés que sin XR.
- El monitor WebRTC en 3ª persona es la mejor herramienta de diagnóstico: comparar lo que ve él
  con lo que ven las gafas es lo que aisló dos de los fallos de hoy.
