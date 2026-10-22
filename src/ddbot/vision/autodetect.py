"""Sugestões automáticas das regiões do combate a partir de uma captura do jogo.

Nada aqui é coordenada fixa: cada região é procurada pelo conteúdo da imagem (bordas, componentes
parecidos com dígitos, faixas uniformes). O que os clientes de DDTank conhecidos têm em comum entra
só como lugar onde procurar primeiro (ex.: o ângulo fica no canto de baixo à esquerda nos clientes
estudados em docs/RESEARCH.md). Toda sugestão vem com a confiança e o motivo, aparece desenhada na
captura e só é salva quando o usuário confirma; regiões já marcadas pelo usuário não são trocadas.

Limite honesto: testado com imagens sintéticas, não com capturas do jogo real.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .regions import px_to_frac as _px_to_frac


def px_to_frac(rect, shape) -> tuple[float, ...]:
    return tuple(float(v) for v in _px_to_frac(tuple(int(v) for v in rect), shape))


@dataclass
class Suggestion:
    key: str                              # chave de REGION_KEYS (angle, wind, power_bar, playfield)
    roi: tuple[float, float, float, float]  # frações x, y, largura, altura da área cliente
    confidence: float
    why: str


# onde procurar primeiro (frações x0, y0, x1, y1 da área de jogo); não é a posição da região
SEARCH = {
    "angle": (0.0, 0.62, 0.38, 1.0),
    "wind": (0.30, 0.0, 0.70, 0.20),
    "power_bar": (0.0, 0.62, 1.0, 1.0),
}


def _uniform_margin(gray: np.ndarray, axis: int, from_end: bool, max_frac=0.3, std_max=4.0) -> int:
    """Quantas linhas (axis=0) ou colunas (axis=1) da borda são de uma cor só (faixa preta, fundo de página)."""
    n = gray.shape[axis]
    limit = int(n * max_frac)
    count = 0
    ref = None
    for i in range(limit):
        idx = n - 1 - i if from_end else i
        line = gray[idx, :] if axis == 0 else gray[:, idx]
        if float(line.std()) > std_max:
            break
        mean = float(line.mean())
        if ref is None:
            ref = mean
        elif abs(mean - ref) > 6:
            break
        count += 1
    return count


def find_playfield(img: np.ndarray) -> Suggestion | None:
    """Área do jogo dentro da janela quando há faixas de cor única dos dois lados (navegador, proporção).

    Só faixas simétricas contam (esquerda e direita, ou em cima e embaixo, com larguras parecidas): o painel
    de baixo do próprio jogo também é de uma cor só e não é borda.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    def pair(a, b, n):
        if min(a, b) < 0.01 * n or abs(a - b) > 0.3 * max(a, b):
            return 0, 0
        return a, b
    left, right = pair(_uniform_margin(gray, 1, False), _uniform_margin(gray, 1, True), w)
    top, bottom = pair(_uniform_margin(gray, 0, False), _uniform_margin(gray, 0, True), h)
    if not (left or top):
        return None  # o jogo ocupa a janela inteira (o padrão da régua já serve)
    rect = (left, top, w - left - right, h - top - bottom)
    if rect[2] < 0.4 * w or rect[3] < 0.4 * h:
        return None
    inner = gray[top:h - bottom, left:w - right]
    if float(inner.std()) < 8:
        return None  # imagem vazia (janela preta ou ainda carregando)
    trimmed = (left + right) / w + (top + bottom) / h
    return Suggestion("playfield", px_to_frac(rect, img.shape), round(min(0.9, 0.5 + trimmed), 2),
                      "faixas de cor única dos dois lados da imagem do jogo")


def _area(img, frac):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = frac
    return int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)


def find_power_bar(img: np.ndarray) -> Suggestion | None:
    """Barra de força: retângulo comprido e baixo na parte de baixo da tela (pelo contorno)."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = _area(img, SEARCH["power_bar"])
    sub = img[y0:y1, x0:x1]
    gray = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 30, 90)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    best, best_score = None, 0.0
    for c in contours:
        x, y, rw, rh = cv2.boundingRect(c)
        if rw < 0.28 * w or rh < 0.008 * h or rh > 0.07 * h or rw / max(rh, 1) < 10:
            continue
        fill = cv2.contourArea(c) / float(rw * rh)
        if fill < 0.55:
            continue
        score = min(1.0, rw / (0.6 * w)) * 0.6 + fill * 0.4
        if score > best_score:
            best, best_score = (x + x0, y + y0, rw, rh), score
    if best is None:
        return None
    return Suggestion("power_bar", px_to_frac(best, img.shape), round(min(0.95, best_score), 2),
                      "retângulo comprido e baixo na parte de baixo da tela")


def _digit_groups(sub: np.ndarray, frame_h: int):
    """Grupos de 1 a 4 componentes com cara de dígito, alinhados na horizontal: [(caixa, nota)]."""
    gray = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
    _, b = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    out = []
    for mask in (b, 255 - b):  # dígito claro no fundo escuro ou o contrário
        n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        comps = []
        for i in range(1, n):
            x, y, cw, ch, area = stats[i]
            if not (0.018 * frame_h <= ch <= 0.08 * frame_h) or not (1.0 <= ch / max(cw, 1) <= 4.5):
                continue
            if area < 0.2 * cw * ch or area > 0.9 * cw * ch:
                continue  # bloco cheio (botão, faixa) ou risco fino não é dígito
            comps.append((x, y, cw, ch))
        comps.sort()
        used = set()
        for i, a in enumerate(comps):
            if i in used:
                continue
            group = [a]
            for j in range(i + 1, len(comps)):
                c = comps[j]
                last = group[-1]
                gap = c[0] - (last[0] + last[2])
                if gap > 1.2 * last[3] or abs(c[3] - a[3]) > 0.3 * a[3] or abs(c[1] - a[1]) > 0.4 * a[3]:
                    continue
                group.append(c)
                used.add(j)
                if len(group) == 4:
                    break
            gx0 = min(g[0] for g in group)
            gy0 = min(g[1] for g in group)
            gx1 = max(g[0] + g[2] for g in group)
            gy1 = max(g[1] + g[3] for g in group)
            heights = [g[3] for g in group]
            regular = 1.0 - min(1.0, float(np.std(heights)) / max(1.0, float(np.mean(heights))))
            score = 0.45 + 0.15 * min(len(group), 3) + 0.1 * regular if len(group) > 1 else 0.4
            out.append(((gx0, gy0, gx1 - gx0, gy1 - gy0), min(0.9, score)))
    return out


def _numbers(img: np.ndarray, key: str, why: str, prefer) -> Suggestion | None:
    h, w = img.shape[:2]
    x0, y0, x1, y1 = _area(img, SEARCH[key])
    groups = _digit_groups(img[y0:y1, x0:x1], h)
    if not groups:
        return None
    (gx, gy, gw, gh), score = max(groups, key=lambda g: (g[1], prefer(g[0], x1 - x0, y1 - y0)))
    pad_x, pad_y = max(2, int(0.25 * gh)), max(2, int(0.2 * gh))
    rect = (max(0, gx + x0 - pad_x), max(0, gy + y0 - pad_y), gw + 2 * pad_x, gh + 2 * pad_y)
    rect = (rect[0], rect[1], min(rect[2], w - rect[0]), min(rect[3], h - rect[1]))
    return Suggestion(key, px_to_frac(rect, img.shape), round(score, 2), why)


def find_angle(img: np.ndarray) -> Suggestion | None:
    return _numbers(img, "angle", "número no canto de baixo à esquerda (onde os clientes mostram o ângulo)",
                    lambda r, aw, ah: -(r[0] / max(aw, 1)))


def find_wind(img: np.ndarray) -> Suggestion | None:
    return _numbers(img, "wind", "número no alto, perto do centro (onde os clientes mostram o vento)",
                    lambda r, aw, ah: -abs((r[0] + r[2] / 2) / max(aw, 1) - 0.5))


def angle_from_change(before: np.ndarray, after: np.ndarray) -> Suggestion | None:
    """Região do ângulo pela diferença entre duas capturas, antes e depois de apertar a tecla do ângulo.

    É a evidência mais forte: no seu turno, só o número do ângulo (e o ponteiro) muda. Em geral muda só o
    último dígito: a região cresce para os dígitos vizinhos na mesma linha.
    """
    if before is None or after is None or before.shape != after.shape:
        return None
    h, w = before.shape[:2]
    diff = cv2.absdiff(cv2.cvtColor(before, cv2.COLOR_BGR2GRAY), cv2.cvtColor(after, cv2.COLOR_BGR2GRAY))
    _, mask = cv2.threshold(diff, 40, 255, cv2.THRESH_BINARY)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    boxes = [tuple(stats[i][:4]) for i in range(1, n) if stats[i][4] >= 6]
    if not boxes or len(boxes) > 12:
        return None  # nada mudou, ou mudou a tela inteira (câmera andando): não serve
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    if (x1 - x0) > 0.3 * w or (y1 - y0) > 0.2 * h:
        return None
    # dígitos vizinhos que não mudaram (dezena, sinal de grau) entram na região
    ch = y1 - y0
    wx0, wy0 = max(0, x0 - 4 * ch), max(0, y0 - ch)
    wx1, wy1 = min(w, x1 + 4 * ch), min(h, y1 + ch)
    for (gx, gy, gw, gh), _ in _digit_groups(after[wy0:wy1, wx0:wx1], h):
        gx, gy = gx + wx0, gy + wy0
        if gx <= x1 and gx + gw >= x0 and gy <= y1 and gy + gh >= y0:
            x0, y0, x1, y1 = min(x0, gx), min(y0, gy), max(x1, gx + gw), max(y1, gy + gh)
    pad = max(2, int(0.2 * (y1 - y0)))
    rect = (max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad) - max(0, x0 - pad),
            min(h, y1 + pad) - max(0, y0 - pad))
    return Suggestion("angle", px_to_frac(rect, before.shape), 0.85,
                      "a parte que mudou ao apertar a tecla do ângulo (e os dígitos ao lado)")


def suggest_regions(img: np.ndarray) -> list[Suggestion]:
    """Todas as sugestões que a imagem permite (pode ser uma lista vazia)."""
    out = []
    for fn in (find_playfield, find_power_bar, find_angle, find_wind):
        try:
            s = fn(img)
        except cv2.error:
            s = None
        if s is not None:
            out.append(s)
    return out


COLORS = {"angle": (0, 200, 255), "wind": (255, 200, 0), "power_bar": (0, 220, 0), "playfield": (200, 200, 200)}
NAMES = {"angle": "angulo", "wind": "vento", "power_bar": "forca", "playfield": "area de jogo"}


def draw_suggestions(img: np.ndarray, found: list[Suggestion]) -> np.ndarray:
    out = img.copy()
    h, w = out.shape[:2]
    for s in found:
        x, y, rw, rh = s.roi
        p0 = (int(x * w), int(y * h))
        p1 = (int((x + rw) * w), int((y + rh) * h))
        color = COLORS.get(s.key, (255, 255, 255))
        cv2.rectangle(out, p0, p1, color, 2)
        label = f"{NAMES.get(s.key, s.key)} {s.confidence:.2f}"
        cv2.putText(out, label, (p0[0] + 3, max(12, p0[1] - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3)
        cv2.putText(out, label, (p0[0] + 3, max(12, p0[1] - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
    return out
