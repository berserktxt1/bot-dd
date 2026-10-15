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
