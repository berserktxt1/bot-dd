"""Regiões de interesse (ROI) em frações da área cliente: independem da resolução."""
from __future__ import annotations

import numpy as np

Rect = tuple[int, int, int, int]


def frac_to_px(roi, shape) -> Rect:
    h, w = shape[:2]
    x, y, rw, rh = roi
    x0, y0 = int(round(x * w)), int(round(y * h))
    x1, y1 = int(round((x + rw) * w)), int(round((y + rh) * h))
    x0, y0 = max(0, min(w - 1, x0)), max(0, min(h - 1, y0))
    x1, y1 = max(x0 + 1, min(w, x1)), max(y0 + 1, min(h, y1))
    return x0, y0, x1 - x0, y1 - y0


def px_to_frac(rect: Rect, shape) -> list[float]:
    h, w = shape[:2]
    x, y, rw, rh = rect
    return [round(x / w, 5), round(y / h, 5), round(rw / w, 5), round(rh / h, 5)]


def crop(img: np.ndarray, roi) -> tuple[np.ndarray, Rect]:
    if roi is None:
        h, w = img.shape[:2]
        return img, (0, 0, w, h)
    x, y, w, h = frac_to_px(roi, img.shape)
    return img[y:y + h, x:x + w], (x, y, w, h)


def valid_roi(roi) -> bool:
    """ROI em frações dentro da imagem e com tamanho mínimo (0,5% de cada lado)."""
    try:
        x, y, w, h = (float(v) for v in roi)
    except (TypeError, ValueError):
        return False
    return 0 <= x < 1 and 0 <= y < 1 and w >= 0.005 and h >= 0.005 and x + w <= 1.001 and y + h <= 1.001


def expand(roi, fx: float, fy: float):
    """A mesma região aumentada ``fx`` larguras para cada lado e ``fy`` alturas (limitada à imagem)."""
    if roi is None:
        return None
    x, y, w, h = (float(v) for v in roi)
    x0, y0 = max(0.0, x - fx * w), max(0.0, y - fy * h)
    x1, y1 = min(1.0, x + w + fx * w), min(1.0, y + h + fy * h)
    return [x0, y0, x1 - x0, y1 - y0]
