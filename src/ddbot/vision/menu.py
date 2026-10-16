"""Descoberta das opções que o cliente mostra num menu (ex.: lista de instâncias).

Em vez de uma lista fixa no código, o usuário abre o menu no jogo e o bot procura
"cartões" retangulares de tamanho parecido. Cada cartão vira um modelo de imagem
que o usuário nomeia; depois ``find_known_options`` diz quais estão visíveis agora.
"""
from __future__ import annotations

import cv2
import numpy as np

from .regions import crop
from .templates import TemplateLibrary


def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / float(aw * ah + bw * bh - inter) if inter else 0.0


def detect_option_tiles(img: np.ndarray, roi=None, min_frac=0.003, max_frac=0.25) -> list[tuple[int, int, int, int]]:
    """Retângulos candidatos (x, y, w, h em pixels da imagem inteira), em ordem de leitura."""
    sub, (ox, oy, _, _) = crop(img, roi)
    h, w = sub.shape[:2]
    gray = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    area_img = float(w * h)
    rects = []
    for c in contours:
        x, y, rw, rh = cv2.boundingRect(c)
        a = rw * rh
        if not (min_frac * area_img <= a <= max_frac * area_img):
            continue
        if not (0.25 <= rw / float(rh) <= 4.0):
            continue
        fill = cv2.contourArea(c) / float(a)
        if fill < 0.6:  # precisa ser aproximadamente retangular
            continue
        rects.append((x, y, rw, rh))
    # remove duplicados (contorno interno/externo do mesmo cartão), mantendo o maior
    rects.sort(key=lambda r: r[2] * r[3], reverse=True)
    kept: list[tuple[int, int, int, int]] = []
    for r in rects:
        if all(_iou(r, k) < 0.5 and not _inside(r, k) for k in kept):
            kept.append(r)
    if len(kept) >= 3:  # opções de menu costumam ter o mesmo tamanho: descarta destoantes
        areas = np.array([r[2] * r[3] for r in kept], float)
        med = np.median(areas)
        kept = [r for r, a in zip(kept, areas) if 0.5 * med <= a <= 2.0 * med]
    kept = [(x + ox, y + oy, rw, rh) for x, y, rw, rh in kept]
    if not kept:
        return kept
    # ordem de leitura: agrupa em linhas quando o topo difere menos de meia altura
    row_h = float(np.median([r[3] for r in kept]))
    kept.sort(key=lambda r: r[1])
    rows: list[list] = []
    for r in kept:
        if rows and abs(r[1] - rows[-1][0][1]) <= row_h / 2:
            rows[-1].append(r)
        else:
            rows.append([r])
    return [r for row in rows for r in sorted(row, key=lambda t: t[0])]


def _inside(a, b, tol=2):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax >= bx - tol and ay >= by - tol and ax + aw <= bx + bw + tol and ay + ah <= by + bh + tol


def find_known_options(img: np.ndarray, templates: TemplateLibrary, threshold: float, prefix="instancia_"):
    """Opções já nomeadas (modelos com o prefixo) visíveis na imagem: [(chave, score)]."""
    out = []
    for key in templates.keys():
        if not key.startswith(prefix):
            continue
        m = templates.best(key, img)
        if m and m.score >= threshold:
            out.append((key, m.score))
    return sorted(out, key=lambda t: -t[1])
