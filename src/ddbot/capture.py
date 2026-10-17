"""Fontes de imagem: janela do jogo (MSS) ou arquivo/pasta (testes e diagnóstico offline)."""
from __future__ import annotations

import logging
import threading
import time
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

    unavailable = ""
    focus_problem = ""

    def is_foreground(self) -> bool:
        return False

    def keyboard_focused(self) -> bool:
        return self.is_foreground()

    def release_thread(self):
        """Libera recursos da thread atual (só a captura de janela usa)."""

    def close(self):
        pass


def covered(hwnd: int, info, window_at, root_of) -> bool:
    """A área do jogo está coberta por outra janela (ex.: a do próprio bot)?

    Confere cinco pontos (centro e quadrantes): todos precisam pertencer à janela do jogo.
    """
    root = root_of(hwnd)
    for fx, fy in ((0.5, 0.5), (0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)):
        h = window_at(info.left + int(info.width * fx), info.top + int(info.height * fy))
        if h and root_of(h) != root:
            return True
    return False


def blank(img) -> bool:
    """Imagem toda preta/uniforme: o jogo não desenhou nada para a captura pela janela."""
    small = img[::8, ::8, :3]
    return float(small.std()) < 2.0


class WindowCapture(FrameSource):
    """Captura a área cliente da janela.

    Primeiro pede a imagem à própria janela (PrintWindow): assim a captura é do jogo mesmo
    com outra janela por cima. Se o jogo devolver imagem vazia (alguns motores gráficos),
    usa a cópia da tela (MSS), mas só se nenhuma outra janela cobrir a área do jogo; senão
    devolve None com o motivo (nunca analisa a imagem de outra janela como se fosse o jogo).

    O MSS precisa de uma instância por thread e só libera os recursos do Windows (DCs e
    bitmaps GDI) em ``close()``. Por isso todas as instâncias ficam registradas: cada
    thread de trabalho chama ``release_thread()`` ao terminar e ``close()`` libera todas.
    """

    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self._local = threading.local()
        self._all: dict[int, object] = {}
        self._lock = threading.Lock()
        self.unavailable = ""      # motivo quando grab() devolve None
        self.last_info = None      # posição/tamanho da janela no último quadro
        self.method = ""           # "janela" (PrintWindow) ou "tela" (MSS)
        self._pw_failures = 0      # PrintWindow vazio seguido: desiste dele por um tempo
        self._pw_retry_at = 0

    def _sct(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            import mss
            sct = mss.mss()
            self._local.sct = sct
            with self._lock:
                self._all[id(sct)] = sct
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
        if info is None:
            self.unavailable = "a janela do jogo foi fechada"
            return None
        if winapi.is_minimized(self.hwnd) or info.width <= 0 or info.height <= 0:
            self.unavailable = "a janela do jogo está minimizada"
            return None
        self.unavailable = ""
        img = self._grab_window(info)
        if img is not None:
            self.method = "janela"
            self.last_info = info
            return img
        if covered(self.hwnd, info, winapi.window_at, winapi.root_of):
            self.unavailable = ("outra janela está na frente do jogo; deixe a janela do jogo visível "
                                "(o JonFlow se minimiza sozinho durante a rotina)")
            return None
        mon = {"left": info.left, "top": info.top, "width": info.width, "height": info.height}
        shot = self._sct().grab(mon)
        self.method = "tela"
        self.last_info = info
        return cv2.cvtColor(np.asarray(shot), cv2.COLOR_BGRA2BGR)

    def _grab_window(self, info):
        if not winapi.IS_WINDOWS:
            return None
        if self._pw_failures >= 3 and time.monotonic() < self._pw_retry_at:
            return None
        try:
            raw = winapi.print_window(self.hwnd, info.width, info.height)
        except Exception:
            log.debug("PrintWindow falhou", exc_info=True)
            raw = None
        if raw is None or blank(raw):
            self._pw_failures += 1
            if self._pw_failures >= 3:
                self._pw_retry_at = time.monotonic() + 30  # o jogo não responde a PrintWindow: usa a tela
            return None
        self._pw_failures = 0
        return cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)

    def is_foreground(self) -> bool:
        """A janela principal que contém o jogo está na frente (requisito para clicar)."""
        fg = winapi.foreground_hwnd()
        return fg != 0 and winapi.root_of(fg) == winapi.root_of(self.hwnd)

    @property
    def is_child(self) -> bool:
        info = self.info
        return bool(info and info.parent)

    def keyboard_focused(self) -> bool:
        """As teclas chegariam ao jogo (foco do teclado dentro da área do jogo, não no launcher)."""
        from .game_window import keyboard_ok
        ok, why = keyboard_ok(self.hwnd, self.is_child, winapi.foreground_hwnd(), winapi.focus_hwnd(),
                              winapi.root_of, winapi.is_same_or_child)
        self.focus_problem = why
        return ok

    focus_problem = ""

    def rebind(self, hwnd: int):
        """O jogo foi reaberto (nova janela): passa a capturar a janela nova."""
        self.hwnd = hwnd
        self.last_info = None
        self._pw_failures = 0

    def release_thread(self):
        sct = getattr(self._local, "sct", None)
        if sct is not None:
            self._local.sct = None
            with self._lock:
                self._all.pop(id(sct), None)
            try:
                sct.close()
            except Exception:
                pass

    def close(self):
        with self._lock:
            items = list(self._all.values())
            self._all.clear()
        for sct in items:
            try:
                sct.close()
            except Exception:
                pass
        self._local = threading.local()

    @property
    def open_instances(self) -> int:
        with self._lock:
            return len(self._all)


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

    def keyboard_focused(self):
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
