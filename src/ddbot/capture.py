"""Fontes de imagem: janela do jogo (MSS) ou arquivo/pasta (testes e diagnóstico offline)."""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import cv2
import numpy as np

from . import winapi

log = logging.getLogger(__name__)


class FrameSource:
    """Interface: ``grab()`` devolve imagem BGR da área cliente e ``origin`` (x, y) na tela."""

    origin = (0, 0)

    def grab(self) -> np.ndarray | None:
        raise NotImplementedError

    def is_foreground(self) -> bool:
        return False

    def close(self):
        pass


class WindowCapture(FrameSource):
    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self._local = threading.local()  # MSS não é thread-safe

    def _sct(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            import mss
            sct = mss.mss()
            self._local.sct = sct
        return sct

    @property
    def info(self):
        return winapi.window_info(self.hwnd)

    @property
    def origin(self):
        info = self.info
        return (info.left, info.top) if info else (0, 0)

    def grab(self):
        info = self.info
        if info is None or winapi.is_minimized(self.hwnd) or info.width <= 0:
            return None
        mon = {"left": info.left, "top": info.top, "width": info.width, "height": info.height}
        shot = self._sct().grab(mon)
        return cv2.cvtColor(np.asarray(shot), cv2.COLOR_BGRA2BGR)

    def is_foreground(self) -> bool:
        fg = winapi.foreground_hwnd()
        return fg != 0 and winapi.root_of(fg) == winapi.root_of(self.hwnd)

    def close(self):
        sct = getattr(self._local, "sct", None)
        if sct is not None:
            sct.close()
            self._local.sct = None


class ImageSource(FrameSource):
    """Reproduz imagens salvas (uma ou várias, em ordem)."""

    def __init__(self, paths):
        if isinstance(paths, (str, Path)):
            p = Path(paths)
            paths = sorted(p.glob("*.png")) if p.is_dir() else [p]
        self.frames = [load_image(x) for x in paths]
        self.index = 0

    def grab(self):
        if not self.frames:
            return None
        img = self.frames[min(self.index, len(self.frames) - 1)]
        self.index += 1
        return img.copy()


class ArraySource(FrameSource):
    def __init__(self, frame=None):
        self.frame = frame
        self.foreground = True

    def grab(self):
        return None if self.frame is None else self.frame.copy()

    def is_foreground(self):
        return self.foreground


def load_image(path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)  # suporta acentos no caminho do Windows
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"não foi possível ler a imagem {path}")
    return img


def save_image(path, img) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("falha ao codificar PNG")
    buf.tofile(str(path))
    return path
