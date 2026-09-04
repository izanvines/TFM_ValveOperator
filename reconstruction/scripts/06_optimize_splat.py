#!/usr/bin/env python3
"""Adelgaza un splat entrenado para que rinda mejor en simulacion, sin tocar lo que se ve.

Un splat recien salido de `frgs reconstruct` arrastra mucho peso muerto. Hay tres
palancas independientes, y conviene entender que optimiza cada una porque atacan
cuellos de botella distintos:

1. **Opacidad minima** -> menos gaussianas -> render mas rapido.
   El refinado de frgs se detiene en `refine-stop-epoch` (100 de 200 por defecto).
   Durante las 100 epocas restantes las opacidades siguen bajando, pero ya no hay
   nadie podando: el resultado es una montana de gaussianas practicamente
   invisibles que el rasterizador sigue proyectando y ordenando en cada frame.
   El umbral 0.005 es el que usa el 3DGS original durante el entrenamiento.

2. **Escala maxima** -> quita las gaussianas gigantes -> render mucho mas rapido.
   Son pocas pero desproporcionadamente caras: el coste de rasterizar una
   gaussiana crece con el area que cubre en pantalla, porque toca mas tiles. Una
   sola gaussiana de 200 m se procesa en practicamente todos los tiles de la
   imagen. Suelen ser artefactos de zonas mal observadas (ventanas, reflejos).

   OJO: el umbral esta en **metros**, lo cual solo tiene sentido porque el modelo
   se paso a escala metrica antes de entrenar (ver 05_make_metric.py). En un
   splat sin esa fase este parametro no significaria nada.

   Un umbral en metros FIJO castiga lo lejano: una gaussiana a 30 m que cubra los
   mismos pixeles en pantalla que una de 0.1 m a 3 m tiene que medir 1 m. Medido
   en la refineria, `--max-scale 0.3` se llevaba el 2.2 % de las gaussianas a menos
   de 15 m pero el **13.8 % de las de 15-40 m**, justo la banda que ya iba floja.
   Por eso existe `--max-scale-rel`: el limite pasa a ser
   `max(--max-scale, --max-scale-rel * d)` con `d` la distancia a la camara de
   entrenamiento mas cercana. Con 0.03, una gaussiana a 30 m puede medir 0.9 m, que
   a la resolucion angular de estas vistas (11.2 px/grado) son unos 20 px: sigue
   matando los splats gigantes de verdad sin castigar el fondo. Necesita `--scene`
   para saber donde estaban las camaras.

3. **Grado de armonicos esfericos** -> fichero y VRAM mucho menores.
   Los coeficientes `f_rest` son 45 de los 59 floats por gaussiana: el **76 %**
   del fichero. Codifican como cambia el color segun el angulo de vista
   (reflejos, brillos especulares). Bajar el grado no acelera el rasterizado de
   forma apreciable, pero recorta el fichero y la memoria en la misma
   proporcion, que es lo que manda en tiempo de carga.

   grado 3 = 16 bases (por defecto) | grado 2 = 9 | grado 1 = 4 | grado 0 = 1
   El grado 0 deja el color plano, sin dependencia del punto de vista. En una
   oficina, mayormente difusa, se nota poco; en una escena con cristales o metal
   pulido se nota bastante.

Las tres son independientes: se pueden aplicar juntas o por separado.
"""

import argparse
import pathlib

import numpy as np
import torch

import fvdb

BANDAS = [(0, 5), (5, 15), (15, 40), (40, 100), (100, float("inf"))]


def distancia_a_camara(means: torch.Tensor, scene_path: pathlib.Path) -> torch.Tensor:
    """Distancia de cada gaussiana a la camara de entrenamiento mas cercana, en metros."""
    from fvdb_reality_capture.sfm_scene import SfmScene

    scene = SfmScene.from_colmap(scene_path)
    centros = np.array([np.linalg.inv(np.asarray(im.world_to_camera_matrix))[:3, 3] for im in scene.images])
    c = torch.as_tensor(centros, dtype=torch.float32, device=means.device)
    print(f"  {len(centros)} camaras leidas de {scene_path}")
    # Por trozos: la matriz completa serian 2.7M x 2340 floats = 25 GB.
    d = torch.full((means.shape[0],), float("inf"), device=means.device)
    for i in range(0, c.shape[0], 64):
        d = torch.minimum(d, torch.cdist(means, c[i:i + 64]).min(dim=1).values)
    return d


def reparto(mascara_descarte: torch.Tensor, d: torch.Tensor, titulo: str) -> None:
    """Imprime que fraccion se descarta en cada banda de distancia."""
    print(f"    {titulo}")
    for lo, hi in BANDAS:
        en_banda = (d >= lo) & (d < hi)
        n = int(en_banda.sum())
        if n == 0:
            continue
        frac = float(mascara_descarte[en_banda].float().mean()) * 100
        print(f"      {lo:>3}-{hi if hi != float('inf') else '+':<4} m: {n:>10,} gaussianas, se descarta {frac:5.2f} %")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in-ply", type=pathlib.Path, required=True)
    ap.add_argument("--out-ply", type=pathlib.Path, required=True)
    ap.add_argument("--min-opacity", type=float, default=0.005,
                    help="Descarta gaussianas por debajo de esta opacidad (0 = no filtrar).")
    ap.add_argument("--max-scale", type=float, default=0.3,
                    help="Descarta gaussianas cuyo eje mayor supere estos METROS (0 = no filtrar).")
    ap.add_argument("--max-scale-rel", type=float, default=0.0,
                    help="Fraccion de la distancia a la camara mas cercana que se le permite medir "
                         "a una gaussiana. El limite real es max(--max-scale, este valor * distancia). "
                         "0 = desactivado (umbral fijo, comportamiento historico). Necesita --scene.")
    ap.add_argument("--scene", type=pathlib.Path,
                    help="Carpeta COLMAP metrica. Obligatoria si se usa --max-scale-rel.")
    ap.add_argument("--sh-degree", type=int, default=-1, choices=[-1, 0, 1, 2, 3],
                    help="Grado de armonicos a conservar (-1 = dejarlo como esta).")
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--dry-run", action="store_true", help="Solo informa, no escribe nada.")
    args = ap.parse_args()

    print(f"Cargando {args.in_ply} ...")
    splat, metadata = fvdb.GaussianSplat3d.from_ply(args.in_ply, device=args.device)
    n0 = splat.num_gaussians
    sh0, shN = splat.sh0, splat.shN
    floats0 = 3 + 1 + 3 + 4 + (sh0.shape[1] + shN.shape[1]) * 3
    print(f"  {n0:,} gaussianas | grado SH {splat.sh_degree} ({splat.num_sh_bases} bases)")
    print(f"  shN {tuple(shN.shape)} -> {floats0} floats/gaussiana = {n0 * floats0 * 4 / 1e6:.0f} MB")

    # --- Mascara de conservacion -------------------------------------------------
    keep = torch.ones(n0, dtype=torch.bool, device=splat.means.device)

    if args.max_scale_rel > 0 and args.scene is None:
        raise SystemExit("--max-scale-rel necesita --scene para saber donde estaban las camaras")

    d = None
    if args.scene is not None:
        print(f"\nDistancia a la camara mas cercana:")
        d = distancia_a_camara(splat.means.detach(), args.scene)

    if args.min_opacity > 0:
        m = splat.opacities.squeeze() >= args.min_opacity
        print(f"\n  opacidad < {args.min_opacity}: descarta {(~m).sum().item():,} ({(~m).float().mean().item()*100:.1f} %)")
        if d is not None:
            reparto(~m, d, "por banda de distancia:")
        keep &= m

    if args.max_scale > 0 or args.max_scale_rel > 0:
        limite = torch.full((n0,), args.max_scale if args.max_scale > 0 else float("inf"),
                            device=splat.means.device)
        if args.max_scale_rel > 0:
            limite = torch.maximum(limite, args.max_scale_rel * d)
            print(f"\n  limite de escala = max({args.max_scale} m, {args.max_scale_rel} * distancia)")
            for lo, hi in BANDAS[:4]:
                en = (d >= lo) & (d < hi)
                if int(en.sum()):
                    print(f"      {lo:>3}-{hi:<4.0f} m -> limite mediano {float(limite[en].median()):.2f} m")
        else:
            print(f"\n  limite de escala = {args.max_scale} m fijo")
        m = splat.scales.max(dim=1).values <= limite
        print(f"  descarta {(~m).sum().item():,} ({(~m).float().mean().item()*100:.2f} %)")
        if d is not None:
            reparto(~m, d, "por banda de distancia:")
        keep &= m

    n1 = int(keep.sum().item())
    print(f"\n  quedan {n1:,} de {n0:,} ({n1/n0*100:.1f} %)")

    # --- Recorte de armonicos ----------------------------------------------------
    # Grado d necesita (d+1)^2 bases en total; sh0 aporta 1, el resto van en shN.
    if args.sh_degree >= 0:
        n_shN = (args.sh_degree + 1) ** 2 - 1
        if n_shN > shN.shape[1]:
            raise SystemExit(f"El splat solo tiene grado {splat.sh_degree}, no se puede subir a {args.sh_degree}")
        print(f"  SH grado {splat.sh_degree} -> {args.sh_degree}: shN pasa de {shN.shape[1]} a {n_shN} bases")
        shN = shN[:, :n_shN, :]

    floats1 = 3 + 1 + 3 + 4 + (sh0.shape[1] + shN.shape[1]) * 3
    mb0, mb1 = n0 * floats0 * 4 / 1e6, n1 * floats1 * 4 / 1e6
    print(f"\n  {mb0:.0f} MB -> {mb1:.0f} MB  ({mb1/mb0*100:.0f} % del original, -{mb0-mb1:.0f} MB)")

    if args.dry_run:
        print("\n--dry-run: no se escribe nada")
        return

    out = fvdb.GaussianSplat3d.from_tensors(
        means=splat.means[keep],
        quats=splat.quats[keep],
        log_scales=splat.log_scales[keep],
        logit_opacities=splat.logit_opacities[keep],
        sh0=sh0[keep],
        shN=shN[keep],
        detach=True,
    )
    args.out_ply.parent.mkdir(parents=True, exist_ok=True)
    # Se reinyecta la metadata original (poses de camara, matrices de proyeccion,
    # normalization_transform) para que el PLY siga siendo autodescriptivo.
    out.save_ply(args.out_ply, metadata=metadata)
    print(f"\nEscrito {args.out_ply} ({args.out_ply.stat().st_size/1e6:.0f} MB)")


if __name__ == "__main__":
    main()
