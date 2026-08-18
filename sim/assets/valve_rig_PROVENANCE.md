# Valve asset handoff — para IsaacLab-Arena (`Openable` affordance)

Origen: `unitree_rl_lab/source/unitree_rl_lab/unitree_rl_lab/assets/valve_rig_collision.usda`
(+ sublayer `valve_rig.usd`, + 2 referencias internas a `original_files/*.usd` — todo embebido/empaquetado abajo).
NO incluye nada del G1 ni del modelo Inspire — asset de la válvula en aislamiento.

## Entregables

- **`valve_rig.usdz`** (2.0M, preferido) — paquete USDZ autocontenido, creado con `UsdUtils.CreateNewUsdzPackage`.
- **`valve_rig_flat.usda`** (8.1M, respaldo legible) — misma composición aplanada a una sola capa de texto (`Usd.Stage.Flatten()`).

Ambos verificados por separado: reabiertos desde `/tmp/valve_handoff/` (fuera del árbol original), mismo prim count (24), mismos joints, mismo bbox — ninguno depende ya de rutas de jescobars.

**Gap conocido, no crítico:** ambos referencian `OmniPBR.mdl` (material shader estándar de Omniverse, no un archivo del proyecto) — no se pudo empaquetar dentro del usdz porque no es un archivo real en disco, se resuelve vía el MDL search path estándar de cualquier instalación Omniverse/Isaac Sim. No afecta geometría/física, solo el shading por defecto.

## Datos del asset

**Prim raíz de la articulación:** `/World/Valve` (tiene `PhysicsArticulationRootAPI`)

**Estructura:** SÍ incluye base/pilar fijo, no es solo el volante:
- `/World/Valve/valve_body/valve_model/valve_model_stl_001` — base/pilar (rigid body, fijado al mundo)
- `/World/Valve/handwheel/node_50_AL_250_B7_8_A/mesh_50_AL_250_B7_8_A_stl` — volante (rigid body dinámico)

**Anclaje al mundo:** `PhysicsFixedJoint` en `/World/Valve/FixedJoint`, `body0` vacío (mundo implícito) → `body1 = valve_body/valve_model/valve_model_stl_001`. El anclaje está horneado dentro del propio USD, NO lo pone `InteractiveSceneCfg` de IsaacLab — ese solo posiciona el prim raíz `Valve` en la escena (ver abajo).

**Joint del volante:** `/World/Valve/RevoluteJoint` (`PhysicsRevoluteJoint`)
- nombre exacto: `RevoluteJoint`
- body0 = `valve_body/valve_model/valve_model_stl_001` (base), body1 = `handwheel/node_50_AL_250_B7_8_A/mesh_50_AL_250_B7_8_A_stl` (volante)
- eje: **Z** (en el frame local del joint, tras `localRot0`)
- **con tope, NO continuo/ilimitado**: `lowerLimit = 539.7°`, `upperLimit = 2879.8°` (en grados, convención USD) — equivale a 1.5–8 vueltas completas. Multi-vuelta pero limitado, no infinito.
- drive: `angular, type=force, stiffness=0.0, damping=100.0, maxForce=1000.0` (drive de velocidad/torque puro, sin resorte de posición)

**Eje de giro en espacio mundo, dirección del volante:**
Componiendo `localRot0` del joint con la rotación de spawn usada en la escena original (`base_cfg.py`: `rot=(w,x,y,z)=(0.707,0,0,0.707)`, 90° sobre Z) → el eje de giro queda en **~(1,0,0), es decir el eje X del mundo/escena** (volante vertical tipo timón, no un tapón horizontal). Si Arena coloca la válvula con otra orientación de spawn, hay que recomponer con esa rotación en vez de la de arriba.

**Stage:** `upAxis = Z`, `metersPerUnit = 1.0`, `defaultPrim = World`

**Dimensiones (en el frame local del asset, sin aplicar la transform de escena):**
- bbox completo (`/World/Valve`, base+volante): min `(-0.100, -0.100, -0.038)`, max `(0.100, 0.100, 0.142)` → altura total 0.180 m
- bbox solo volante (`handwheel`): diámetro X/Y ≈ **0.200 m**, grosor Z ≈ 0.040 m, **centro del volante en (0, 0, 0.122)** m relativo al origen del asset

**Posición usada en la escena original (para referencia, no viene en el USD):** `base_cfg.py` spawnea `valve_rig` en `pos=(0.60, 0.0, 0.90)`, `rot=(0.707,0,0,0.707)` relativo al origen del robot — es decir, el centro del volante queda ≈0.60 m delante y ≈1.02 m de altura (0.90 + 0.122) respecto al origen del robot. Esto es específico de esa escena/robot; para Arena hay que recolocar según el alcance del brazo del G1 que estén usando.
