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
    exe: str = ""            # nome do executável do processo dono (ex.: launcher.exe)
    cls: str = ""            # classe da janela (identifica o tipo de área: navegador, Flash, Unity...)
    parent: int = 0          # 0 = janela principal; senão, a janela que a contém
    visible: bool = True

    @property
    def rect(self):
        return self.left, self.top, self.width, self.height

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)


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
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.IsChild.argtypes = [wintypes.HWND, wintypes.HWND]
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                    ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    class GUITHREADINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hwndActive", wintypes.HWND),
                    ("hwndFocus", wintypes.HWND), ("hwndCapture", wintypes.HWND),
                    ("hwndMenuOwner", wintypes.HWND), ("hwndMoveSize", wintypes.HWND),
                    ("hwndCaret", wintypes.HWND), ("rcCaret", wintypes.RECT)]

    user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUITHREADINFO)]

    def _class(hwnd) -> str:
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        return buf.value

    _exe_cache: dict[int, str] = {}

    def process_exe(pid: int) -> str:
        """Nome do executável do processo (só leitura do nome; nada é aberto para escrita)."""
        if pid in _exe_cache:
            return _exe_cache[pid]
        name = ""
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h:
            try:
                size = wintypes.DWORD(1024)
                buf = ctypes.create_unicode_buffer(size.value)
                if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    name = buf.value.replace("/", "\\").rsplit("\\", 1)[-1]
            finally:
                kernel32.CloseHandle(h)
        if len(_exe_cache) > 512:
            _exe_cache.clear()
        _exe_cache[pid] = name
        return name

    def focus_hwnd() -> int:
        """Janela que recebe o teclado agora (pode ser uma janela interna do launcher)."""
        info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
        if user32.GetGUIThreadInfo(0, ctypes.byref(info)) and info.hwndFocus:
            return int(info.hwndFocus)
        return foreground_hwnd()

    def is_same_or_child(target, hwnd) -> bool:
        return bool(hwnd) and (int(hwnd) == int(target) or bool(user32.IsChild(target, hwnd)))

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
        parent = user32.GetParent(hwnd)
        root = user32.GetAncestor(hwnd, 2)
        is_child = bool(root) and int(root) != int(hwnd)
        return WindowInfo(int(hwnd), _title(hwnd), pt.x, pt.y, rc.right - rc.left, rc.bottom - rc.top,
                          pid.value, process_exe(pid.value), _class(hwnd),
                          int(parent) if (parent and is_child) else 0, bool(user32.IsWindowVisible(hwnd)))

    def list_windows(min_size: int = 100) -> list[WindowInfo]:
        """Janelas principais visíveis (com ou sem título) maiores que ``min_size``."""
        result: list[WindowInfo] = []

        def cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                info = window_info(hwnd)
                if info and info.width > min_size and info.height > min_size:
                    result.append(info)
            return True

        user32.EnumWindows(EnumWindowsProc(cb), 0)
        return result

    def child_windows(hwnd, min_size: int = 100) -> list[WindowInfo]:
        """Janelas internas visíveis (ex.: a área onde o launcher desenha o jogo)."""
        result: list[WindowInfo] = []

        def cb(child, _):
            if user32.IsWindowVisible(child):
                info = window_info(child)
                if info and info.width > min_size and info.height > min_size:
                    result.append(info)
            return True

        user32.EnumChildWindows(hwnd, EnumWindowsProc(cb), 0)
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

    def work_area() -> tuple[int, int, int, int] | None:
        """Área de trabalho do monitor principal (sem a barra de tarefas): x, y, largura, altura."""
        rc = wintypes.RECT()
        if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rc), 0):  # SPI_GETWORKAREA
            return rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top
        return None

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
    def list_windows(min_size: int = 100) -> list[WindowInfo]:
        return []

    def child_windows(hwnd, min_size: int = 100) -> list[WindowInfo]:
        return []

    def process_exe(pid: int) -> str:
        return ""

    def focus_hwnd() -> int:
        return 0

    def is_same_or_child(target, hwnd) -> bool:
        return bool(hwnd) and hwnd == target

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

    def work_area():
        return None

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
