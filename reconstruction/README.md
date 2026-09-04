# Reconstrucción fotorrealista de la oficina (Gaussian Splatting)

El fondo de las imágenes del dataset es una reconstrucción por *Gaussian Splatting* de una oficina
real, hecha con **fVDB Reality Capture** (NVIDIA) sobre poses de cámara de **COLMAP**. Este
directorio contiene los guiones propios del pipeline y la receta; el anexo D de la memoria lo
describe con sus cifras. El proyecto de trabajo original vive fuera del repositorio (`~/GS_fvdb`),
porque los datos de captura y los resultados intermedios pesan gigabytes.

## Qué hay aquí

| Fichero | Para qué |
|---|---|
| `env.sh` | Activa el entorno conda del proyecto y pone **delante** en el `PATH` el COLMAP compilado con CUDA. Sin él, la shell resuelve el COLMAP de apt, sin CUDA y con otros nombres de opciones |
| `scripts/01_select_sharp_frames.py` | De una extracción densa de fotogramas de vídeo, se queda con el más nítido de cada ventana (varianza del laplaciano), para garantizar nitidez y cobertura temporal a la vez |
| `scripts/05_make_metric.py` | Lleva el modelo COLMAP a metros y Z arriba **antes** de entrenar: vertical por RANSAC de suelo, escala por altura media de cámara (1,5 m) |
| `scripts/06_optimize_splat.py` | Poda el splat entrenado (opacidad < 0,005, escalas desproporcionadas) para que rinda en simulación sin cambiar lo que se ve |
| `scripts/07_render_check.py` | Renderiza vistas del splat desde las poses reales o desde cámaras libres, para revisarlo antes de exportar |

Los guiones son las versiones actuales del proyecto; algunos incorporan opciones añadidas después
para otras capturas (por ejemplo, referencias GPS en `05_make_metric.py`), que no se usaron aquí.

## Entorno

| | |
|---|---|
| Python | 3.12, en un entorno conda propio (`GS_fvdb/env`) |
| fVDB | `fvdb-core 0.5.1+pt211.cu128`, `fvdb-reality-capture 0.5.0`, `torch 2.11.0+cu128` |
| COLMAP | 4.2 de desarrollo, compilado con CUDA para `sm_120` (`-DCMAKE_CUDA_ARCHITECTURES=120`, nunca `native` en Blackwell) |
| Isaac Sim | 6.0 (contenedor `isaaclab_arena-latest`), con *Geometry Streaming* activado |

```bash
conda create -p ~/GS_fvdb/env python=3.12 -y && conda activate ~/GS_fvdb/env
pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
pip install fvdb-core==0.5.1+pt211.cu128 fvdb-reality-capture==0.5.0 \
    --extra-index-url https://d36m13axqqhiit.cloudfront.net/simple
# torchvision hay que forzarla con sufijo cu128, o falla `torchvision::nms` al importar
pip install torchvision==0.26.0+cu128 --index-url https://download.pytorch.org/whl/cu128 --force-reinstall --no-deps
```

## Las dos capturas

| | 3 de agosto (fotos) | **4 de agosto (vídeo) — la del dataset** |
|---|---|---|
| Fuente | 101 fotos de iPhone 12 (HEIC 3024×4032) | vídeo; 1089 fotogramas → **545** nítidos |
| COLMAP | 101/101 registradas, 54 321 puntos, traza 4,86, 1,41 px | **538/545 registradas**, 142 619 puntos, traza 8,32, 1,18 px |
| Entrenamiento | 200 épocas, 8 min 18 s | 200 épocas, 107 600 pasos, ~30 min |
| Gaussianas | 2 361 265 | 3 962 281 → **2 144 018** tras la poda |
| Salida | `office_nurec.usdz` | `office_video_nurec_opt.usdz` → `office_video_nurec_rot.usd` |

La primera validó el pipeline entero (incluida una malla de colisión por TSDF que al final no
hizo falta: la física de la escena es un plano de suelo). La segunda es la que carga Arena como
fondo `office_gs`.

## Receta (la del vídeo)

```bash
source reconstruction/env.sh
D=data/office_video

# 1. fotogramas
ffmpeg -i IMG_0392.MOV -qscale:v 2 $D/frames_raw/frame_%05d.jpg
python scripts/01_select_sharp_frames.py $D/frames_raw $D/images --window 2

# 2. SfM en GPU
colmap feature_extractor --database_path $D/database.db --image_path $D/images \
  --ImageReader.camera_model OPENCV --ImageReader.single_camera 1 \
  --FeatureExtraction.use_gpu 1 --SiftExtraction.estimate_affine_shape 1 --SiftExtraction.domain_size_pooling 1
colmap exhaustive_matcher --database_path $D/database.db --FeatureMatching.use_gpu 1
colmap mapper --database_path $D/database.db --image_path $D/images --output_path $D/sparse
colmap image_undistorter --image_path $D/images --input_path $D/sparse/0 --output_path $D/undistorted --output_type COLMAP

# 3. metros y Z arriba, ANTES de entrenar
python scripts/05_make_metric.py            # lee $D/undistorted, escribe $D/metric

# 4. splat (sin normalización de escena, para conservar las unidades)
frgs reconstruct $D/metric -o out/office_video_splat.ply --tx.normalization-type none --tx.image-downsample-factor 2 -d cuda:0

# 5. poda
python scripts/06_optimize_splat.py out/office_video_splat.ply out/office_video_splat_opt.ply

# 6. exportar a NuRec (mejor calidad visual en Isaac Sim 6.0 que ParticleField3D)
frgs convert out/office_video_splat_opt.ply out/office_video_nurec_opt.usdz --legacy --usdz
```

El `.usdz` se envuelve en una capa `.usd` propia que lo endereza (`rotateZYX(-89,0,0)` más una
traslación, verificadas contra las 538 cámaras), añade un plano de colisión de 10×10 m en Z=0 y una
escena de física, y es lo que `sim/patches/background_library.patch` registra como `office_gs`.

## Trampas que costaron sesiones

- **El exportador legacy deja el activo tumbado**: escribe una «matriz de conversión por defecto»
  pensada para datos Y arriba. Es su propia inversa, así que la corrección exacta es poner la
  transformación del prim `Volume` a identidad, no buscar ángulos a ojo.
- **Geometry Streaming**: sin activarlo en Isaac Sim, las gaussianas se muestran como esferas grises.
  `Edit > Preferences > Rendering > RTX Geometry Streaming`, y reiniciar.
- **Recorte robusto antes del RANSAC** en `05_make_metric.py`: sin él, los puntos triangulados a
  través de ventanas y reflejos inflaban la escena a 23×43 m.
- **El fondo heredado** al empezar (otra oficina, otra herramienta, sin datos fuente) llevaba una
  matriz transpuesta que USD lee como proyectiva y deforma el splat al moverlo. Se recapturó.

## Lo que no está aquí

Los datos de captura, los modelos COLMAP, los splats (`.ply`, 0,5–0,9 GB) y los `.usdz`
(253–592 MB). El activo que usa la simulación es `office_video_nurec_rot.usd` en `~/datasets`,
montado como `/datasets` en el contenedor.
