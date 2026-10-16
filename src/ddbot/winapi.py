"""Acesso mínimo à API do Windows via ctypes (sem pywin32).

Somente funções públicas de janelas e entrada (SendInput). Nada de injeção, leitura de
memória ou hooks no processo do jogo.
"""
from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass

IS_WINDOWS = sys.platform == "win32"


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    left: int
    top: int
    width: int
    height: int
    pid: int = 0

    @property
    def rect(self):
        return self.left, self.top, self.width, self.height


if IS_WINDOWS:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)  # per-monitor DPI aware
    except Exception:  # Windows antigo
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND

    def _title(hwnd) -> str:
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    def window_info(hwnd) -> WindowInfo | None:
        if not user32.IsWindow(hwnd):
            return None
        rc = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rc)):
            return None
        pt = wintypes.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(pt))
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return WindowInfo(int(hwnd), _title(hwnd), pt.x, pt.y, rc.right - rc.left,
                          rc.bottom - rc.top, pid.value)

    def list_windows() -> list[WindowInfo]:
        result: list[WindowInfo] = []

        def cb(hwnd, _):
            if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
                info = window_info(hwnd)
                if info and info.width > 100 and info.height > 100:
                    result.append(info)
            return True

        user32.EnumWindows(EnumWindowsProc(cb), 0)
        return result

    def foreground_hwnd() -> int:
        h = user32.GetForegroundWindow()
        return int(h) if h else 0

    def is_minimized(hwnd) -> bool:
        return bool(user32.IsIconic(hwnd))

    def root_of(hwnd) -> int:
        h = user32.GetAncestor(hwnd, 2)  # GA_ROOT
        return int(h) if h else int(hwnd)

    def set_foreground(hwnd) -> bool:
        return bool(user32.SetForegroundWindow(hwnd))

    # ---------------------------------------------------------------- SendInput
    INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
    KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE, KEYEVENTF_EXTENDEDKEY = 0x2, 0x8, 0x1
    MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x2, 0x4

    ULONG_PTR = ctypes.c_size_t

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]

    # scancodes (conjunto 1); teclas estendidas marcadas
    SCANCODES = {
        "up": (0x48, True), "down": (0x50, True), "left": (0x4B, True), "right": (0x4D, True),
        "space": (0x39, False), "enter": (0x1C, False), "esc": (0x01, False), "tab": (0x0F, False),
        **{str(i): (sc, False) for i, sc in zip(range(1, 10), range(0x02, 0x0B))}, "0": (0x0B, False),
        **{c: (sc, False) for c, sc in zip("qwertyuiop", range(0x10, 0x1A))},
        **{c: (sc, False) for c, sc in zip("asdfghjkl", range(0x1E, 0x27))},
        **{c: (sc, False) for c, sc in zip("zxcvbnm", range(0x2C, 0x33))},
        **{f"f{i}": (0x3A + i, False) for i in range(1, 11)}, "f11": (0x57, False), "f12": (0x58, False),
        "shift": (0x2A, False), "ctrl": (0x1D, False), "alt": (0x38, False), "backspace": (0x0E, False),
        "pageup": (0x49, True), "pagedown": (0x51, True), "home": (0x47, True), "end": (0x4F, True),
        "insert": (0x52, True), "delete": (0x53, True),
    }

    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND

    def _send(inp) -> None:
        if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
            from .automation.safety import InputBlocked
            raise InputBlocked("o Windows bloqueou o envio de teclas/cliques; se o jogo roda como "
                               "administrador, abra o bot também como administrador")

    def send_key(key: str, up: bool):
        sc, ext = SCANCODES[key.lower()]
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if ext else 0) | (KEYEVENTF_KEYUP if up else 0)
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.u.ki = KEYBDINPUT(0, sc, flags, 0, 0)
        _send(inp)

    def mouse_click(x: int, y: int):
        import time
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.03)  # alguns clientes ignoram clique sem movimento/pausa
        for i, flag in enumerate((MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)):
            inp = INPUT(type=INPUT_MOUSE)
            inp.u.mi = MOUSEINPUT(0, 0, 0, flag, 0, 0)
            _send(inp)
            if i == 0:
                time.sleep(0.04)

    def window_at(x: int, y: int) -> int:
        h = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
        return int(h) if h else 0

else:  # Linux/macOS: só para desenvolvimento e testes
    def list_windows() -> list[WindowInfo]:
        return []

    def window_info(hwnd) -> WindowInfo | None:
        return None

    def foreground_hwnd() -> int:
        return 0

    def is_minimized(hwnd) -> bool:
        return False

    def root_of(hwnd) -> int:
        return hwnd

    def set_foreground(hwnd) -> bool:
        return False

    SCANCODES: dict = {}

    def window_at(x: int, y: int) -> int:
        return 0

    def send_key(key: str, up: bool):
        raise RuntimeError("Envio de teclas só é suportado no Windows")

    def mouse_click(x: int, y: int):
        raise RuntimeError("Cliques só são suportados no Windows")


def key_supported(key: str | None) -> bool:
    """True se a tecla pode ser enviada (fora do Windows não há como validar)."""
    if not key:
        return False
    return not IS_WINDOWS or key.lower() in SCANCODES


def find_game_windows(keywords) -> list[WindowInfo]:
    kws = [k.lower() for k in keywords]
    return [w for w in list_windows() if any(k in w.title.lower() for k in kws)]
