"""Leitura de números (ângulo, vento, força) com glifos aprendidos do próprio cliente.

O usuário seleciona a região, digita o valor mostrado e o leitor aprende cada glifo.
Assim não dependemos de OCR genérico nem de fontes que não conhecemos.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

GLYPH_SIZE = (12, 18)


def binarize(img: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    g = cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # texto deve ser branco (minoria dos pixels)
    if np.count_nonzero(b) > b.size / 2:
        b = 255 - b
    return b


def segment(img: np.ndarray) -> list[np.ndarray]:
    """Separa glifos por componentes conectados, da esquerda para a direita."""
    b = binarize(img)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(b, connectivity=8)
    h = b.shape[0]
    boxes = []
    for i in range(1, n):
        x, y, w, hh, area = stats[i]
        if area < 4 or hh < h * 0.15:
            # pontos decimais são pequenos: aceita se estiverem na metade de baixo
            if not (area >= 3 and y > h * 0.5):
                continue
        boxes.append((x, y, w, hh))
    boxes.sort(key=lambda r: r[0])
    # junta componentes sobrepostos horizontalmente (glifos quebrados)
    merged: list[list[int]] = []
    for x, y, w, hh in boxes:
        if merged and x <= merged[-1][0] + merged[-1][2] - 1:
            mx, my, mw, mh = merged[-1]
            nx, ny = min(mx, x), min(my, y)
            merged[-1] = [nx, ny, max(mx + mw, x + w) - nx, max(my + mh, y + hh) - ny]
        else:
            merged.append([x, y, w, hh])
    glyphs = []
    for x, y, w, hh in merged:
        g = b[y:y + hh, x:x + w]
        glyphs.append(_normalize(g, small=hh < h * 0.35))
    return glyphs


def _normalize(g, small=False):
    out = cv2.resize(g, GLYPH_SIZE, interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    if small:
        out[0, 0] = -1.0  # marca glifos pequenos (ponto) para não confundir com dígitos
    return out


class DigitReader:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.glyphs: dict[str, list[np.ndarray]] = {}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
                self.glyphs = {k: [np.array(v, dtype=np.float32).reshape(GLYPH_SIZE[::-1]) for v in vs]
                               for k, vs in raw.items()}
            except (OSError, ValueError, TypeError):
                # arquivo corrompido: guarda e recomeça o treino em vez de impedir o programa de abrir
                try:
                    self.path.replace(self.path.with_suffix(".corrompido.json"))
                except OSError:
                    pass
                self.glyphs = {}

    @property
    def trained(self) -> bool:
        return sum(1 for k in self.glyphs if k.isdigit()) >= 3

    MIN_CONFIDENCE = 0.3

    def learn(self, img: np.ndarray, text: str) -> bool:
        text = text.strip().replace(",", ".")
        glyphs = segment(img)
        if len(glyphs) != len(text):
            # o cliente pode não desenhar o sinal: tenta sem ele
            text = text.replace("-", "")
            if len(glyphs) != len(text):
                return False
        for ch, g in zip(text, glyphs):
            self.glyphs.setdefault(ch, []).append(g)
            self.glyphs[ch] = self.glyphs[ch][-8:]
        self.save()
        return True

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        from ..util import atomic_write_text
        atomic_write_text(self.path, json.dumps({k: [g.round(3).tolist() for g in v] for k, v in self.glyphs.items()}))

    def read(self, img: np.ndarray) -> tuple[float | None, float]:
        """Retorna (valor, confiança 0-1)."""
        if not self.trained or img is None or img.size == 0:
            return None, 0.0
        chars, scores = [], []
        for g in segment(img):
            best_ch, best_s = None, -1.0
            for ch, samples in self.glyphs.items():
                for s in samples:
                    score = 1.0 - float(np.mean(np.abs(s - g)))
                    if score > best_s:
                        best_ch, best_s = ch, score
            if best_ch is None:
                return None, 0.0
            chars.append(best_ch)
            scores.append(best_s)
        text = "".join(chars).strip(".")
        if not text or text.count(".") > 1 or "-" in text[1:]:
            return None, 0.0
        try:
            value = float(text)
        except ValueError:
            return None, 0.0
        conf = max(0.0, (float(min(scores)) - 0.6) / 0.4) if scores else 0.0
        if conf < self.MIN_CONFIDENCE:
            return None, conf  # parecido demais com ruído: melhor não ler nada do que ler errado
        return value, conf
