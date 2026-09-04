#!/usr/bin/env python3
"""Selecciona los frames mas nitidos de una extraccion densa, con cobertura temporal uniforme.

Por que no un umbral global de nitidez: descartaria bloques enteros de frames
consecutivos (justo donde el movil giraba rapido), abriendo huecos de cobertura
que rompen el matching secuencial. En su lugar se usa una **ventana deslizante**:
de cada grupo de `--window` frames consecutivos se queda el mas nitido. Asi se
garantiza a la vez nitidez Y un frame cada N del video, pase lo que pase.

La nitidez se mide como la varianza del Laplaciano (metrica estandar de
enfoque): una imagen movida tiene menos bordes de alta frecuencia, luego menor
varianza. Se calcula sobre una version reducida de cada frame porque a 4K es
innecesariamente lento y el ranking relativo no cambia.
"""

import argparse
import pathlib
import shutil

import cv2
import numpy as np


def sharpness(path: pathlib.Path, max_side: int) -> float:
    """Varianza del Laplaciano sobre el frame reducido a `max_side` px de lado mayor."""
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return -1.0
    h, w = img.shape
    scale = max_side / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(img, cv2.CV_64F).var())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=pathlib.Path, default="data/office_video/frames_raw")
    ap.add_argument("--dst", type=pathlib.Path, default="data/office_video/images")
    ap.add_argument("--window", type=int, default=2, help="Se queda 1 frame de cada `window` consecutivos.")
    ap.add_argument("--max-side", type=int, default=960, help="Lado mayor al que se reduce para medir nitidez.")
    ap.add_argument("--dry-run", action="store_true", help="Solo informa, no copia nada.")
    args = ap.parse_args()

    frames = sorted(args.src.glob("*.jpg"))
    if not frames:
        raise SystemExit(f"No hay frames en {args.src}")
    print(f"{len(frames)} frames en {args.src}, ventana={args.window}")

    print("Midiendo nitidez...")
    scores = np.array([sharpness(f, args.max_side) for f in frames])
    print(f"  nitidez: min={scores.min():.1f} p25={np.percentile(scores,25):.1f} "
          f"mediana={np.median(scores):.1f} p75={np.percentile(scores,75):.1f} max={scores.max():.1f}")

    keep_idx = []
    for start in range(0, len(frames), args.window):
        chunk = scores[start:start + args.window]
        keep_idx.append(start + int(np.argmax(chunk)))

    kept_scores = scores[keep_idx]
    print(f"\nSeleccionados {len(keep_idx)} de {len(frames)} frames")
    print(f"  nitidez de los elegidos: min={kept_scores.min():.1f} mediana={np.median(kept_scores):.1f}")
    print(f"  mejora de la mediana: {np.median(scores):.1f} -> {np.median(kept_scores):.1f} "
          f"(+{(np.median(kept_scores)/np.median(scores)-1)*100:.1f}%)")

    worst = np.argsort(kept_scores)[:5]
    print("  los 5 menos nitidos que sobreviven:")
    for i in worst:
        print(f"    {frames[keep_idx[i]].name}  {kept_scores[i]:.1f}")

    if args.dry_run:
        print("\n--dry-run: no se copia nada")
        return

    args.dst.mkdir(parents=True, exist_ok=True)
    for n, i in enumerate(keep_idx):
        shutil.copy2(frames[i], args.dst / f"frame_{n:05d}.jpg")
    print(f"\nCopiados a {args.dst}")


if __name__ == "__main__":
    main()
