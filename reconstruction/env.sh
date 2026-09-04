# Entorno del proyecto GS_fvdb. Uso:  source env.sh
#
# Deja en el PATH el COLMAP compilado con CUDA de este proyecto (NO el de apt,
# que esta compilado "without CUDA") y activa el entorno conda local.

export GS_ROOT="/home/ivines/GS_fvdb"

# CUDA usado para compilar COLMAP (toolkit autocontenido en $HOME, ver plan).
export CUDA_HOME="$HOME/cuda-12.9"

# El COLMAP del proyecto va DELANTE de /usr/bin en el PATH.
export PATH="$GS_ROOT/install/colmap/bin:$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$GS_ROOT/install/colmap/lib:$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"

# Esta maquina es compartida. A 2026-08-05 la GPU 0 la ocupa un entrenamiento 3DGUT
# de otro compañero (train.py en contenedor, corre como root) y la 1 esta libre, o
# sea al reves que cuando se monto el proyecto. No es cuestion de memoria -- 96 GB
# por tarjeta y entre todos se usan 7 -- sino de computo: dos procesos en la misma
# GPU se reparten los SMs y van los dos mas lentos.
#
# COMPROBAR ABAJO ANTES DE LANZAR NADA LARGO: si la ocupacion ha cambiado, cambia esto.
export GS_DEVICE="cuda:1"

# Entorno conda local al proyecto (prefix, no un env con nombre).
source /opt/miniconda3/etc/profile.d/conda.sh
conda activate "$GS_ROOT/env"

echo "GS_fvdb listo"
echo "  python : $(command -v python)"
echo "  colmap : $(command -v colmap || echo 'aun no compilado')"
echo "  device : $GS_DEVICE"
echo "  GPUs   :"
python - <<'PY'
import subprocess
def smi(q, extra=()):
    out = subprocess.run(["nvidia-smi", f"--query-{q}", "--format=csv,noheader,nounits", *extra],
                         capture_output=True, text=True).stdout
    return [[c.strip() for c in l.split(",")] for l in out.splitlines() if l.strip()]
def usuario(pid):
    return subprocess.run(["ps", "-o", "user=", "-p", pid], capture_output=True, text=True).stdout.strip()
# Los stubs de escritorio (snapd-desktop-integration) reservan 12 MiB y no son computo:
# sin este filtro la GPU libre parece ocupada por media oficina.
apps = {}
for uuid, pid, mem in smi("compute-apps=gpu_uuid,pid,used_memory"):
    if int(mem) >= 100:
        apps.setdefault(uuid, set()).add(f"{usuario(pid) or '?'}({int(mem)/1024:.1f}G)")
for idx, uuid, util, mem in smi("gpu=index,uuid,utilization.gpu,memory.used"):
    quien = " ".join(sorted(apps.get(uuid, []))) or "libre"
    print(f"           {idx}: {util:>3} % uso, {int(mem)/1024:5.1f} GB   {quien}")
PY
