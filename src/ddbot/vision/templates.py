"""Biblioteca de modelos de imagem capturados pelo usuário e busca multi-escala."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..capture import load_image, save_image

SCALES = (1.0, 0.9, 1.1, 0.8, 1.25, 0.75, 1.5)
NEAR = (1.0, 0.95, 1.05)        # depois que a escala do modelo é conhecida para este tamanho de imagem
FOUND = 0.8                     # correlação a partir da qual a escala encontrada é memorizada
HALF_MIN_SIDE = 32              # modelos com os dois lados >= isto podem ser buscados em meia resolução
HALF_MIN_AREA = 400_000         # ... em imagens a partir deste tamanho (ex.: 800x500)
FULL_EVERY = 20                 # modelo ainda não encontrado: busca em todas as escalas a cada N buscas


@dataclass
class Match:
    key: str
    score: float
    rect: tuple[int, int, int, int]  # x, y, w, h em pixels da imagem completa
    template: int = 0                # qual amostra do modelo venceu (índice em ``get(key)``)

    @property
    def center(self):
        x, y, w, h = self.rect
        return x + w / 2, y + h / 2


def _gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def match_template(region: np.ndarray, tpl: np.ndarray, scales=SCALES, ref_scale=1.0):
    """Melhor correlação (score, x, y, w, h) do modelo dentro da região, em várias escalas.

    Em imagens grandes, modelos grandes são comparados em meia resolução (4x menos contas;
    a posição volta para a resolução cheia com erro de até 1 pixel).
    """
    g = _gray(region)
    t0 = _gray(tpl)
    small_side = min(t0.shape[:2]) * ref_scale
    if g.shape[0] * g.shape[1] >= HALF_MIN_AREA and small_side >= HALF_MIN_SIDE:
        g2 = cv2.resize(g, (g.shape[1] // 2, g.shape[0] // 2), interpolation=cv2.INTER_AREA)
        sc, x, y, w, h = _match(g2, t0, scales, ref_scale * 0.5)
        if sc < 0:
            return sc, x, y, w, h
        return sc, x * 2, y * 2, w * 2, h * 2
    return _match(g, t0, scales, ref_scale)


def _match(g, t0, scales, ref_scale):
    best = (-1.0, 0, 0, 0, 0)
    for s in scales:
        s = s * ref_scale
        tw, th = max(4, int(t0.shape[1] * s)), max(4, int(t0.shape[0] * s))
        if tw > g.shape[1] or th > g.shape[0]:
            continue
        t = cv2.resize(t0, (tw, th), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        if float(t.std()) < 1e-3:
            continue
        res = cv2.matchTemplate(g, t, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(res)
        if mx > best[0]:
            best = (float(mx), loc[0], loc[1], tw, th)
        if mx > 0.97:
            break
    return best


def find_all(region: np.ndarray, tpl: np.ndarray, threshold: float, scale=1.0, max_hits=10):
    """Todas as ocorrências acima do limiar (supressão simples de vizinhos)."""
    g, t0 = _gray(region), _gray(tpl)
    tw, th = max(4, int(t0.shape[1] * scale)), max(4, int(t0.shape[0] * scale))
    if tw > g.shape[1] or th > g.shape[0]:
        return []
    t = cv2.resize(t0, (tw, th))
    res = cv2.matchTemplate(g, t, cv2.TM_CCOEFF_NORMED)
    hits = []
    for _ in range(max_hits):
        _, mx, _, loc = cv2.minMaxLoc(res)
        if mx < threshold:
            break
        hits.append((float(mx), loc[0], loc[1], tw, th))
        # suprime vizinhos em toda a largura/altura do modelo (evita duplicar o mesmo alvo)
        x0, y0 = max(0, loc[0] - tw), max(0, loc[1] - th)
        res[y0:loc[1] + th + 1, x0:loc[0] + tw + 1] = -1
    return hits


class TemplateLibrary:
    """Modelos em ``templates/<chave>/*.png``. Chaves: estados, marcadores, botões, setas."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, list[np.ndarray]] = {}
        # escala em que cada modelo foi encontrado, por tamanho de imagem: a janela do jogo quase
        # nunca muda de tamanho, então as próximas buscas testam só essa escala e as vizinhas
        self._scales: dict[tuple, float] = {}
        # escala da última ocorrência de qualquer modelo neste tamanho de imagem: os modelos vêm todos
        # do mesmo cliente, então um modelo ausente da tela não precisa ser procurado em todas as escalas
        self._shape_scale: dict[tuple, float] = {}
        self._tries: dict[tuple, int] = {}

    def keys(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_dir() and any(p.glob("*.png")))

    def _dir(self, key: str) -> Path:
        """Pasta do modelo; nomes com '..' ou barras não saem da biblioteca."""
        d = (self.root / key).resolve()
        if d.parent != self.root.resolve() or not key or key.startswith("."):
            raise ValueError(f"nome de modelo inválido: {key!r}")
        return d

    def get(self, key: str) -> list[np.ndarray]:
        if key not in self._cache:
            d = self._dir(key)
            self._cache[key] = [load_image(p) for p in sorted(d.glob("*.png"))] if d.exists() else []
        return self._cache[key]

    def has(self, key: str) -> bool:
        return bool(self.get(key))

    def add(self, key: str, img: np.ndarray) -> Path:
        path = save_image(self._dir(key) / f"{int(time.time() * 1000)}.png", img)
        self._cache.pop(key, None)
        self._forget(key)
        return path

    def _forget(self, key: str):
        for k in [k for k in self._scales if k[0] == key]:
            self._scales.pop(k, None)
        self._shape_scale.clear()

    def remove_key(self, key: str):
        d = self._dir(key)
        if d.exists():
            for p in d.glob("*.png"):
                p.unlink()
        self._cache.pop(key, None)
        self._forget(key)

    def best(self, key: str, img: np.ndarray, offset=(0, 0), scale_hint=1.0) -> Match | None:
        best = None
        for i, tpl in enumerate(self.get(key)):
            mem = (key, i, img.shape[:2])
            learned = self._scales.get(mem)
            shared = self._shape_scale.get(img.shape[:2])
            if learned is not None:
                score, x, y, w, h = match_template(img, tpl, scales=NEAR, ref_scale=learned)
                # não achou na escala memorizada: a tela mudou (zoom, resolução) ou a escala era de uma
                # coincidência. Procura em todas, sempre se nenhuma escala comum é conhecida, senão
                # periodicamente (antes, com uma escala comum, a escala errada ficava para sempre)
                if score < FOUND and (shared is None or self._tries.get(mem, 0) % FULL_EVERY == 0):
                    score, x, y, w, h = match_template(img, tpl, ref_scale=scale_hint)
            elif shared is not None and self._tries.get(mem, 0) % FULL_EVERY:
                score, x, y, w, h = match_template(img, tpl, scales=NEAR, ref_scale=shared)
            else:
                score, x, y, w, h = match_template(img, tpl, ref_scale=scale_hint)
            self._tries[mem] = self._tries.get(mem, 0) + 1
            if len(self._tries) > 4096:
                self._tries.clear()
            if score >= FOUND and tpl.shape[1]:
                self._scales[mem] = self._shape_scale[img.shape[:2]] = w / tpl.shape[1]
            if best is None or score > best.score:
                best = Match(key, score, (x + offset[0], y + offset[1], w, h), i)
        return best
