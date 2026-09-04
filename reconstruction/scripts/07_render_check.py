#!/usr/bin/env python3
"""Renderiza vistas del splat entrenado, desde las poses reales o desde camaras libres.

Hay dos preguntas distintas que responder y cada una necesita su modo:

**--pick masked / spread** -- ¿quedaron agujeros donde estaba el operador?
El criterio de exito del enmascarado no se puede leer en la loss: las zonas tapadas
tienen loss CERO por construccion (`gaussian_splat_reconstruction.py:1388` iguala el
ground-truth al render en los pixeles enmascarados). O sea que el operador podria
haber dejado un agujero perfecto y la loss no se enteraria. Por eso `masked` no elige
vistas al azar: coge las que tenian **mas superficie enmascarada**, que son justo
donde puede quedar hueco. Si en esas el sitio se ve completo, en el resto tambien.
Salida: una tira por vista, foto | render | mascara.

**--pick fly** -- ¿como se ve desde donde el robot va a mirar de verdad?
Desde las poses de entrenamiento un splat SIEMPRE se ve bien: son las poses contra
las que se optimizo. Medido en la refineria: 0.0 % de pixeles vacios desde las 260
poses originales, pero **100 % desde una cenital a 60 m**. El modelo habia tapado el
cielo con gaussianas "papel pintado" a 5-15 m que solo funcionan desde el camino.
Este modo usa camaras sinteticas fuera del recorrido -- cenitales, oblicuas y de pie
a distancia -- y ademas imprime y estampa el **porcentaje de pixeles vacios**, que es
la medida objetiva de "aqui no hay nada reconstruido".
"""

import argparse
import math
import pathlib

import cv2
import numpy as np
import torch

import fvdb
from fvdb_reality_capture.sfm_scene import SfmScene


def look_at(eye: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Matriz world-to-camera en convencion OpenCV (+x derecha, +y abajo, +z delante)."""
    f = np.asarray(target, float) - np.asarray(eye, float)
    f /= np.linalg.norm(f)
    # Con la camara mirando recto arriba o abajo, Z ya no sirve de referencia vertical.
    up = np.array([0.0, 0.0, 1.0])
    if abs(float(f @ up)) > 0.999:
        up = np.array([0.0, 1.0, 0.0])
    r = np.cross(f, up)
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    c2w = np.eye(4)
    c2w[:3, :3] = np.stack([r, -u, f], axis=1)   # -u: en OpenCV el eje y va hacia abajo
    c2w[:3, 3] = eye
    return np.linalg.inv(c2w)


def fly_cameras(centro: np.ndarray, suelo_z: float) -> list[tuple[str, np.ndarray]]:
    """Juego fijo de camaras fuera del recorrido, en metros y relativas al centro."""
    c = np.array([centro[0], centro[1], suelo_z], float)
    ojo = np.array([centro[0], centro[1], suelo_z + 1.8], float)
    casos = [
        ("cenital_30m",   c + [0, 0, 30],    c),
        ("cenital_60m",   c + [0, 0, 60],    c),
        ("oblicua_25m",   c + [25, 25, 25],  c),
        ("oblicua_40m",   c + [40, 0, 40],   c),
        ("depie_40m_E",   ojo + [40, 0, 0],  ojo),
        ("depie_40m_N",   ojo + [0, 40, 0],  ojo),
        ("depie_80m_E",   ojo + [80, 0, 0],  ojo),
        # Desde dentro mirando al cielo: es donde se ve si hay cupula o un agujero negro.
        ("mirando_arriba", ojo,              ojo + [25, 0, 25]),
    ]
    return [(n, look_at(e, t)) for n, e, t in casos]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ply", type=pathlib.Path, required=True)
    ap.add_argument("--scene", type=pathlib.Path, required=True, help="Carpeta COLMAP (la metrica).")
    ap.add_argument("--out", type=pathlib.Path, default="out/check_refinery")
    ap.add_argument("-n", type=int, default=6, help="Cuantas vistas (ignorado en modo fly).")
    ap.add_argument("--pick", choices=["masked", "spread", "fly"], default="masked",
                    help="'masked' = las de mayor cobertura de mascara (peor caso). "
                         "'spread' = repartidas por el recorrido. "
                         "'fly' = camaras libres fuera del recorrido, con % de vacio.")
    ap.add_argument("--size", type=int, default=1024, help="Lado del render en modo fly.")
    ap.add_argument("--hfov", type=float, default=90.0, help="Campo de vision en modo fly, en grados.")
    ap.add_argument("--ground-z", type=float, default=0.0,
                    help="Cota del suelo en el modelo metrico (05_make_metric.py lo deja en 0).")
    ap.add_argument("--device", default="cuda:1")
    args = ap.parse_args()

    splat, _ = fvdb.GaussianSplat3d.from_ply(args.ply, device=args.device)
    print(f"{args.ply}: {splat.num_gaussians:,} gaussianas, grado SH {splat.sh_degree}")

    scene = SfmScene.from_colmap(args.scene)
    imgs = list(scene.images)
    print(f"escena: {len(imgs)} vistas")
    args.out.mkdir(parents=True, exist_ok=True)

    if args.pick == "fly":
        render_fly(splat, scene, imgs, args)
    else:
        render_poses(splat, scene, imgs, args)


def render_fly(splat, scene, imgs, args) -> None:
    centros = np.array([np.linalg.inv(np.asarray(im.world_to_camera_matrix))[:3, 3] for im in imgs])
    centro = centros.mean(axis=0)
    print(f"centro del recorrido: {centro.round(1)}   suelo en Z={args.ground_z:g}")

    s = args.size
    f = (s / 2.0) / math.tan(math.radians(args.hfov) / 2.0)
    k = torch.tensor([[f, 0, s / 2.0], [0, f, s / 2.0], [0, 0, 1]],
                     dtype=torch.float32, device=args.device)[None].contiguous()

    print(f"\n  {'vista':16s} {'vacio':>8s}  luminancia")
    for nombre, w2c_np in fly_cameras(centro, args.ground_z):
        w2c = torch.as_tensor(w2c_np, dtype=torch.float32, device=args.device)[None].contiguous()
        rgb, alpha = splat.render_images(w2c, k, s, s, near=0.01, far=1e5)
        vacio = float((alpha[0].squeeze() < 0.5).float().mean())
        lum = float(rgb[0].mean())

        render = (rgb[0].clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)[..., ::-1]  # RGB -> BGR
        render = np.ascontiguousarray(render)
        etiqueta = f"{nombre}   vacio {vacio*100:.1f} %"
        cv2.putText(render, etiqueta, (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 5)
        cv2.putText(render, etiqueta, (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.imwrite(str(args.out / f"fly_{nombre}.jpg"), render, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        print(f"  {nombre:16s} {vacio*100:7.1f} %  {lum:.2f}")
    print(f"\n  escritas en {args.out}")


def render_poses(splat, scene, imgs, args) -> None:
    if args.pick == "masked":
        # La cobertura se mide sobre el PNG: negro = enmascarado.
        cov = []
        for i, im in enumerate(imgs):
            m = cv2.imread(str(im.mask_path), cv2.IMREAD_GRAYSCALE)
            cov.append((0.0 if m is None else float((m <= 127).mean()), i))
        cov.sort(reverse=True)
        elegidas = [i for _, i in cov[: args.n]]
        print("elegidas por cobertura de mascara: " +
              ", ".join(f"{pathlib.Path(imgs[i].image_path).stem} {cov[k][0]*100:.0f}%"
                        for k, i in enumerate(elegidas)))
    else:
        elegidas = list(np.linspace(0, len(imgs) - 1, args.n).astype(int))

    for n, idx in enumerate(elegidas):
        im = imgs[idx]
        foto = cv2.imread(str(im.image_path))
        h, w = foto.shape[:2]

        cam = scene.cameras[im.camera_id]
        w2c = torch.as_tensor(np.asarray(im.world_to_camera_matrix), dtype=torch.float32,
                              device=args.device).contiguous()
        k = torch.as_tensor(np.asarray(cam.projection_matrix), dtype=torch.float32,
                            device=args.device).contiguous()
        rgb, _ = splat.render_images(w2c[None].contiguous(), k[None].contiguous(), w, h, near=0.01, far=1e4)
        render = (rgb[0].clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)[..., ::-1]  # RGB -> BGR

        mask = cv2.imread(str(im.mask_path), cv2.IMREAD_GRAYSCALE)
        mask = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

        tira = np.hstack([foto, render, mask])
        etiqueta = f"{pathlib.Path(im.image_path).stem}   FOTO | RENDER | MASCARA"
        cv2.putText(tira, etiqueta, (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 5)
        cv2.putText(tira, etiqueta, (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        p = args.out / f"check_{n}_{pathlib.Path(im.image_path).stem}.jpg"
        cv2.imwrite(str(p), tira, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        print(f"  {p}")


if __name__ == "__main__":
    main()
