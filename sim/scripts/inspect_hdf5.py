# Audita un HDF5 grabado por `record_demos.py`. h5py puro: no arranca Isaac Sim.
import sys

import h5py
import numpy as np

ruta = sys.argv[1] if len(sys.argv) > 1 else "/datasets/isaaclab_arena/g1_valve/g1_valve_demo01.hdf5"
f = h5py.File(ruta, "r")

print("=" * 70)
print(f"FICHERO: {ruta}")
print("=" * 70)
print("atributos raiz:")
for k, v in f.attrs.items():
    print(f"   {k} = {v}")

data = f["data"]
print(f"\natributos de /data:")
for k, v in data.attrs.items():
    txt = str(v)
    print(f"   {k} = {txt[:120]}{'...' if len(txt) > 120 else ''}")

demos = sorted(data.keys(), key=lambda s: int(s.split("_")[-1]) if s.split("_")[-1].isdigit() else 0)
print(f"\nDEMOS: {len(demos)} -> {demos}")

for nombre in demos:
    d = data[nombre]
    print("\n" + "-" * 70)
    print(f"### {nombre}")
    for k, v in d.attrs.items():
        print(f"   attr {k} = {v}")

    def recorre(g, prefijo=""):
        for k in g.keys():
            item = g[k]
            ruta_k = f"{prefijo}/{k}"
            if isinstance(item, h5py.Group):
                recorre(item, ruta_k)
            else:
                info = f"   {ruta_k:52s} {str(item.shape):22s} {item.dtype}"
                if item.dtype != object and item.size and np.prod(item.shape) < 5e8:
                    try:
                        arr = item[...]
                        if np.issubdtype(arr.dtype, np.number):
                            info += f"  min={arr.min():.3f} max={arr.max():.3f} mean={arr.mean():.3f}"
                    except Exception:
                        pass
                print(info)

    recorre(d)

    # --- comprobaciones que importan ---
    print("\n   COMPROBACIONES")
    acciones = d["actions"][...] if "actions" in d else None
    if acciones is not None:
        print(f"   * acciones: {acciones.shape[0]} pasos x {acciones.shape[1]} dims"
              f"  {'OK (23 dims)' if acciones.shape[1] == 23 else 'AVISO: no son 23 dims'}")
        loco = acciones[:, 16:19]
        alt = acciones[:, 19]
        print(f"   * navigate_cmd [16:19]: min={loco.min():.4f} max={loco.max():.4f}"
              f"  {'CONGELADO (bien)' if np.allclose(loco, 0) else 'NO congelado -> revisar ARENA_STATIC_BASE'}")
        print(f"   * base_height_cmd [19]: min={alt.min():.3f} max={alt.max():.3f}")
        for i in range(acciones.shape[1]):
            col = acciones[:, i]
            if col.std() == 0:
                print(f"     - dim {i:2d} CONSTANTE en {col[0]:.4f}  (std=0 -> division por cero al normalizar)")

    # camara
    cams = []

    def busca_cam(g, prefijo=""):
        for k in g.keys():
            item = g[k]
            if isinstance(item, h5py.Group):
                busca_cam(item, f"{prefijo}/{k}")
            elif item.ndim >= 3 and item.dtype == np.uint8:
                cams.append((f"{prefijo}/{k}", item))

    busca_cam(d)
    if not cams:
        print("   * !! NO HAY IMAGENES DE CAMARA en la demo")
    for ruta_c, item in cams:
        arr = item[...]
        negros = int((arr.reshape(arr.shape[0], -1).max(axis=1) == 0).sum())
        print(f"   * camara {ruta_c}: {arr.shape} {arr.dtype}"
              f"  min={arr.min()} max={arr.max()} mean={arr.mean():.1f}")
        print(f"     fotogramas totalmente negros: {negros}/{arr.shape[0]}"
              f"  {'OK' if negros == 0 else 'AVISO'}")

f.close()
print("\n" + "=" * 70)
