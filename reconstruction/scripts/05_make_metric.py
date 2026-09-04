#!/usr/bin/env python3
"""Lleva un modelo COLMAP (undistorted) a metros y Z-up, antes de entrenar el splat.

COLMAP es scale-free y su eje "up" es arbitrario (el que definio el primer par de
imagenes del mapper incremental). Este script:

  1. Estima una vertical aproximada u0 = media de la direccion "arriba de la imagen"
     de las 101 camaras, en coordenadas mundo. Como el movil se sostiene mas o menos
     recto durante la captura, esto ya da una buena primera aproximacion.
  2. Toma los puntos 3D mas bajos segun u0 (percentil --floor-percentile) como
     candidatos a suelo, y les ajusta un plano por RANSAC. La normal de ese plano
     es la vertical REAL (mas precisa que u0, porque mide una superficie fisica
     en vez de promediar hacia donde apuntaba el movil).

     Antes de esto se recorta el punto 3D a una caja "robusta" (percentiles
     --outlier-percentile / 100-eso, por eje). En interiores es habitual tener
     puntos triangulados muy lejos del cuarto (vistas por una ventana, reflejos
     en un monitor o cristal, falsos matches de texturas repetidas); sin este
     recorte, esos pocos puntos disparan la diagonal del bbox, y con ella tanto
     el umbral de RANSAC como el bounding box final quedan invalidos.
  3. Rota todo para que esa normal quede en +Z, traslada para que el suelo quede en
     Z=0 y el centro de las camaras en XY=(0,0).
  4. Escala: sin medida manual (fallback automatico), fija la altura media de las
     101 camaras sobre el suelo en --cam-height metros (por defecto 1.5 m, movil en
     la mano). Precision esperada ~5%.

Escribe el resultado en <out>/sparse/ (formato COLMAP binario) y enlaza
<out>/images -> <sparse-in>/../images, para que quede en el layout que
`frgs reconstruct` espera (colmap_path/images + colmap_path/sparse).
"""

import argparse
import os
import pathlib

import numpy as np
import pycolmap


def link_into(out_dir: pathlib.Path, name: str, target_dir: pathlib.Path) -> None:
    """Symlink relativo <out_dir>/<name> -> <target_dir>, rehecho si ya existia."""
    link = out_dir / name
    if link.is_symlink() or link.exists():
        link.unlink()
    target = os.path.relpath(target_dir.resolve(), start=link.parent.resolve())
    link.symlink_to(target)
    print(f"Symlink de {name}: {link} -> {target} (resuelve a {link.resolve()})")


def rotation_aligning_a_to_b(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Matriz de rotacion R (3x3) tal que R @ a queda alineado con b. a, b unitarios."""
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    s = np.linalg.norm(v)
    c = float(np.dot(a, b))
    if s < 1e-8:
        if c > 0:
            return np.eye(3)
        # a y b antiparalelos: cualquier eje perpendicular a a sirve, rotacion 180deg.
        axis = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        axis = axis - a * (axis @ a)
        axis /= np.linalg.norm(axis)
        return 2.0 * np.outer(axis, axis) - np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * ((1 - c) / (s * s))


def fit_plane_ransac(
    points: np.ndarray, n_iters: int, dist_thresh: float, rng: np.random.Generator
) -> tuple[np.ndarray, float, np.ndarray]:
    """RANSAC + refinado por SVD. Devuelve (normal_unitaria, offset_d, mascara_inliers)."""
    best_inliers = None
    best_count = -1
    for _ in range(n_iters):
        idx = rng.choice(len(points), 3, replace=False)
        p0, p1, p2 = points[idx]
        normal = np.cross(p1 - p0, p2 - p0)
        norm = np.linalg.norm(normal)
        if norm < 1e-9:
            continue
        normal = normal / norm
        d = float(normal @ p0)
        dist = np.abs(points @ normal - d)
        inliers = dist < dist_thresh
        count = int(inliers.sum())
        if count > best_count:
            best_count = count
            best_inliers = inliers

    assert best_inliers is not None, "RANSAC no encontro ningun plano"
    pts_in = points[best_inliers]
    centroid = pts_in.mean(axis=0)
    # full_matrices=False NO es opcional: por defecto numpy calcula U entera, de MxM,
    # y aqui M es el numero de inliers de suelo. Con 139178 (la refineria) eso son
    # 155 GB de una sola asignacion, para quedarnos solo con vt, que es 3x3.
    _, _, vt = np.linalg.svd(pts_in - centroid, full_matrices=False)
    normal = vt[-1]
    d = float(normal @ centroid)
    return normal, d, best_inliers


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sparse-in", type=pathlib.Path, default="data/office/undistorted/sparse")
    ap.add_argument("--images-in", type=pathlib.Path, default="data/office/undistorted/images")
    ap.add_argument("--masks-in", type=pathlib.Path, default=None,
                    help="Carpeta de mascaras. Si se pasa, se enlaza como <out>/masks, que es "
                         "donde fvdb las busca (_load_colmap_scene.py:61).")
    ap.add_argument("--out", type=pathlib.Path, default="data/office/metric")
    ap.add_argument("--cam-height", type=float, default=1.5, help="Altura media de camara sobre el suelo, en metros.")
    ap.add_argument("--floor-percentile", type=float, default=15.0, help="Percentil de altura para candidatos a suelo.")
    ap.add_argument("--outlier-percentile", type=float, default=1.0,
                     help="Recorte por eje [p, 100-p] para descartar outliers (ventanas, reflejos) antes de RANSAC y del bbox final.")
    ap.add_argument("--ransac-iters", type=int, default=2000)
    ap.add_argument("--ransac-thresh-frac", type=float, default=0.01, help="Umbral RANSAC como fraccion de la diagonal del bbox robusto.")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)

    print(f"Cargando reconstruccion de {args.sparse_in} ...")
    r = pycolmap.Reconstruction(str(args.sparse_in))
    print(f"  {r.num_images()} imagenes, {r.num_points3D()} puntos 3D")

    image_list = list(r.images.values())
    centers = np.stack([im.projection_center() for im in image_list])  # (N, 3)
    rots = [im.cam_from_world().rotation.matrix() for im in image_list]  # world<-cam es R^T

    # "Arriba de la imagen" en camara OpenCV (X derecha, Y abajo, Z adelante) es -Y.
    ups_world = np.stack([R.T @ np.array([0.0, -1.0, 0.0]) for R in rots])
    u0 = ups_world.mean(axis=0)
    u0 /= np.linalg.norm(u0)
    print(f"Vertical aproximada (media de {len(image_list)} camaras): {u0}")

    point_ids = list(r.points3D.keys())
    xyz = np.stack([r.points3D[pid].xyz for pid in point_ids])  # (M, 3)

    # Recorte robusto por eje: descarta el `outlier_percentile`% mas bajo y mas
    # alto de cada eje (min/max crudos son muy sensibles a un puñado de puntos
    # mal triangulados; el percentil no).
    lo = np.percentile(xyz, args.outlier_percentile, axis=0)
    hi = np.percentile(xyz, 100.0 - args.outlier_percentile, axis=0)
    core_mask = np.all((xyz >= lo) & (xyz <= hi), axis=1)
    xyz_core = xyz[core_mask]
    print(f"Recorte robusto (percentil {args.outlier_percentile}/{100-args.outlier_percentile}): "
          f"{len(xyz_core)} de {len(xyz)} puntos ({len(xyz) - len(xyz_core)} descartados como posibles outliers)")

    heights = xyz_core @ u0
    thresh = np.percentile(heights, args.floor_percentile)
    floor_candidates = xyz_core[heights <= thresh]
    print(f"Candidatos a suelo (percentil {args.floor_percentile}): {len(floor_candidates)} de {len(xyz_core)} puntos")

    bbox_diag = float(np.linalg.norm(hi - lo))
    dist_thresh = args.ransac_thresh_frac * bbox_diag
    print(f"Diagonal del bbox robusto (unidades COLMAP): {bbox_diag:.4f}  ->  umbral RANSAC: {dist_thresh:.5f}")

    normal, d, inliers = fit_plane_ransac(floor_candidates, args.ransac_iters, dist_thresh, rng)
    if normal @ u0 < 0:
        normal, d = -normal, -d
    print(f"Plano de suelo: normal={normal}  offset={d:.4f}  inliers={int(inliers.sum())}/{len(floor_candidates)}")
    angle_deg = np.degrees(np.arccos(np.clip(normal @ u0, -1, 1)))
    print(f"Desviacion entre vertical aproximada y normal del suelo: {angle_deg:.2f} grados")

    r_align = rotation_aligning_a_to_b(normal, np.array([0.0, 0.0, 1.0]))

    # Tras rotar, la componente Z de cualquier punto es exactamente su altura
    # original a lo largo de `normal` (ver derivacion en el plan). Por eso el
    # offset de suelo en Z, tras rotar, es simplemente `d`.
    centers_rot = centers @ r_align.T
    offset = np.array([np.median(centers_rot[:, 0]), np.median(centers_rot[:, 1]), d])

    # Alturas de camara sobre el suelo, en unidades COLMAP (sin escalar todavia):
    # distancia con signo de cada centro de camara al plano de suelo ajustado.
    cam_heights_raw = centers @ normal - d
    mean_cam_height_raw = float(np.mean(cam_heights_raw))
    scale = args.cam_height / mean_cam_height_raw
    print(f"Altura media de camara (unidades COLMAP): {mean_cam_height_raw:.4f}  ->  escala: {scale:.6f} m/unidad")

    sim3d = pycolmap.Sim3d(
        scale=scale,
        rotation=pycolmap.Rotation3d(matrix=r_align),
        translation=-scale * offset,
    )
    r.transform(sim3d)

    # --- Verificacion tras transformar ---
    xyz_new = np.stack([p.xyz for p in r.points3D.values()])
    centers_new = np.stack([im.projection_center() for im in r.images.values()])
    # Bbox robusto (mismos percentiles que arriba) en vez de min/max crudo: los
    # outliers siguen en el modelo (no se borran puntos), pero no deben
    # dominar las dimensiones que se reportan como "tamaño de la sala".
    bbox_min = np.percentile(xyz_new, args.outlier_percentile, axis=0)
    bbox_max = np.percentile(xyz_new, 100.0 - args.outlier_percentile, axis=0)
    print("\n=== Resultado (metros, Z-up) ===")
    print(f"Bounding box robusto (percentil {args.outlier_percentile}/{100-args.outlier_percentile}):  "
          f"X [{bbox_min[0]:.2f}, {bbox_max[0]:.2f}]  "
          f"Y [{bbox_min[1]:.2f}, {bbox_max[1]:.2f}]  Z [{bbox_min[2]:.2f}, {bbox_max[2]:.2f}]  (metros)")
    print(f"Dimensiones: {bbox_max[0]-bbox_min[0]:.2f} x {bbox_max[1]-bbox_min[1]:.2f} x {bbox_max[2]-bbox_min[2]:.2f} m")
    print(f"Altura media de camara sobre Z=0: {centers_new[:, 2].mean():.3f} m "
          f"(min {centers_new[:, 2].min():.3f}, max {centers_new[:, 2].max():.3f})")

    out_sparse = args.out / "sparse"
    out_sparse.mkdir(parents=True, exist_ok=True)
    r.write_binary(str(out_sparse))
    print(f"\nModelo metrico escrito en {out_sparse}")

    link_into(args.out, "images", args.images_in)
    if args.masks_in is not None:
        if not args.masks_in.is_dir():
            raise SystemExit(f"--masks-in apunta a {args.masks_in}, que no existe")
        link_into(args.out, "masks", args.masks_in)


if __name__ == "__main__":
    main()
