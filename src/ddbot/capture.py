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


GRID = (8, 6)  # pontos conferidos na área do jogo (colunas x linhas)


def grid_points(grid=GRID) -> list[tuple[float, float]]:
    nx, ny = grid
    return [((i + 0.5) / nx, (j + 0.5) / ny) for j in range(ny) for i in range(nx)]


def sample_points(hwnd: int, info, window_at, root_of, grid=GRID):
    """Classifica uma grade de 8×6 pontos (frações da área do jogo): (cobertos, visíveis, fora da tela).

    Com só o centro e os quadrantes, uma janela menor entre eles (aviso, outro programa)
    passava despercebida e a cópia da tela trazia os pixels dela. Ponto sem janela nenhuma
    está fora de qualquer monitor: não é "descoberto" (a cópia da tela ali é preta).
    """
    root = root_of(hwnd)
    cov, vis, off = [], [], []
    for fx, fy in grid_points(grid):
        h = window_at(info.left + int(info.width * fx), info.top + int(info.height * fy))
        (off if not h else vis if root_of(h) == root else cov).append((fx, fy))
    return cov, vis, off


def covered_points(hwnd: int, info, window_at, root_of, grid=GRID) -> list[tuple[float, float]]:
    """Pontos em que outra janela está por cima do jogo."""
    return sample_points(hwnd, info, window_at, root_of, grid)[0]


def covered(hwnd: int, info, window_at, root_of) -> bool:
    """A área do jogo está coberta, mesmo que em parte, por outra janela (ex.: a do próprio bot)?"""
    return bool(covered_points(hwnd, info, window_at, root_of))


def blank(img) -> bool:
    """Imagem toda preta/uniforme: o jogo não desenhou nada para a captura pela janela."""
    small = img[::8, ::8, :3]
    return float(small.std()) < 2.0


def _cells(img, points, size=0.06):
    """Recortes pequenos em volta de cada ponto (frações), para comparar duas imagens."""
    h, w = img.shape[:2]
    rw, rh = max(2, int(w * size / 2)), max(2, int(h * size / 2))
    for fx, fy in points:
        cx, cy = int(w * fx), int(h * fy)
        yield img[max(0, cy - rh):cy + rh, max(0, cx - rw):cx + rw, :3].astype(np.int16)


def same_pixels(a, b, points, tol: float = 10.0) -> float:
    """Fração dos recortes em volta de ``points`` em que as duas imagens são praticamente iguais."""
    if a is None or b is None or a.shape[:2] != b.shape[:2] or not points:
        return 0.0
    hits = sum(1 for ca, cb in zip(_cells(a, points), _cells(b, points)) if float(np.abs(ca - cb).mean()) <= tol)
    return hits / len(points)


def check_window_image(window_img, screen_img, covered_pts, visible_pts=None) -> tuple[bool | None, str]:
    """Confere a imagem pedida à janela (PrintWindow) contra a cópia da tela.

    - onde outra janela cobre o jogo, a imagem da janela **não pode** ser igual à tela (seria
      a janela da frente vista como se fosse o jogo);
    - onde o jogo está descoberto, as duas precisam coincidir (prova que é a imagem atual do
      jogo, não uma imagem velha ou de outra janela).

    Devolve (True, "") se confirmada, (False, motivo) se é de outra janela e (None, motivo)
    quando não há como confirmar (jogo coberto por inteiro).
    """
    # pontos fora da tela não entram: lá a cópia da tela não tem o jogo
    free = visible_pts if visible_pts is not None else [p for p in grid_points() if p not in set(covered_pts)]
    if covered_pts and same_pixels(window_img, screen_img, covered_pts) >= 0.5:
        return False, "a imagem da janela do jogo mostra a janela que está na frente dele"
    if not free:
        return None, "o jogo não está visível em nenhum ponto da tela e a imagem dele não pôde ser confirmada"
    # o jogo anima (água, vento, personagens): basta a maior parte da área descoberta coincidir
    if same_pixels(window_img, screen_img, free) < 0.6:
        return False, "a imagem da janela do jogo não confere com o que aparece na tela"
    return True, ""


class WindowCapture(FrameSource):
    """Captura a área cliente da janela.

    Primeiro pede a imagem à própria janela (PrintWindow): assim a captura é do jogo mesmo
    com outra janela por cima. Essa imagem é conferida com a tela (alguns drivers e sessões
    remotas devolvem o que está na tela, inclusive a janela da frente, como se fosse a do
    jogo). Se o jogo devolver imagem vazia (alguns motores gráficos),
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
        self._pw_ok_at: float | None = None  # última vez em que a imagem da janela conferiu com a tela

    VERIFY_EVERY_S = 10.0

    def _sct(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            import mss
            # mss.MSS a partir do MSS 10 (mss.mss ficou obsoleto); mss.mss nas versões antigas
            sct = (getattr(mss, "MSS", None) or mss.mss)()
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
        pts, visible, offscreen = sample_points(self.hwnd, info, winapi.window_at, winapi.root_of)
        img = self._grab_window(info)
        if img is not None:
            img = self._verified(img, info, pts, visible)
            if img is not None:
                self.method = "janela"
                self.last_info = info
                return img
            if self.unavailable:
                return None
        if pts:
            self.unavailable = ("outra janela está na frente do jogo; deixe a janela do jogo visível "
                                "(o JonFlow se minimiza sozinho durante a rotina)")
            return None
        if offscreen:
            self.unavailable = "parte da janela do jogo está fora da tela; deixe o jogo inteiro dentro do monitor"
            return None
        self.method = "tela"
        self.last_info = info
        return self._screen(info)

    def _screen(self, info):
        mon = {"left": info.left, "top": info.top, "width": info.width, "height": info.height}
        return cv2.cvtColor(np.asarray(self._sct().grab(mon)), cv2.COLOR_BGRA2BGR)

    def _verified(self, img, info, pts, visible=None):
        """A imagem da janela só vale se conferir com a tela (ver ``check_window_image``).

        Com o jogo descoberto, a conferência é refeita a cada ``VERIFY_EVERY_S``; com ele coberto,
        a cada quadro. Imagem que não confere nunca é usada: com o jogo descoberto vale a cópia da
        tela; coberto, a captura recusa com o motivo (``unavailable``).
        """
        now = time.monotonic()
        if not pts and self._pw_ok_at is not None and now - self._pw_ok_at < self.VERIFY_EVERY_S:
            return img
        ok, why = check_window_image(img, self._screen(info), pts, visible)
        if ok:
            self._pw_ok_at = now
            return img
        if ok is None and self._pw_ok_at is not None:
            return img  # coberto por inteiro, mas a imagem da janela já foi confirmada antes
        self._pw_ok_at = None
        log.warning("captura pela janela recusada: %s", why)
        if not pts:
            # descoberto e sem conferir: usa a cópia da tela por um tempo (sem cópia dupla e aviso a cada quadro)
            self._pw_failures, self._pw_retry_at = 3, time.monotonic() + self.VERIFY_EVERY_S
        if pts:
            self.unavailable = f"{why}; deixe a janela do jogo visível"
        return None

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
        self._pw_ok_at = None

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
