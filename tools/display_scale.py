"""Muda a escala da tela principal do Windows (100%, 125%, 150%...) sem sair da sessão. Feito para a CI.

O runner do GitHub roda em 100%, e várias falhas só aparecem com a escala que os PCs costumam usar
(125%): programas sem suporte a DPI desenham em 100% e o Windows estica a imagem na tela. Usa o
mesmo ajuste de "Escala" das Configurações do Windows (``SystemParametersInfo`` com
``SPI_SETLOGICALDPIOVERRIDE``, não documentado: o valor é relativo à escala recomendada do monitor).
Programas abertos depois da troca já veem a escala nova. Confere com ``GetDpiForMonitor`` e sai com
erro se a escala não mudou (assim a CI nunca relata como "testado em 125%" algo que rodou em 100%).

Uso: python tools/display_scale.py 125
     python tools/display_scale.py          (só mostra a escala atual)
"""
from __future__ import annotations

import ctypes
import sys
import time

SCALES = [100, 125, 150, 175, 200, 225, 250, 300, 350, 400, 450, 500]
SPI_GETLOGICALDPIOVERRIDE, SPI_SETLOGICALDPIOVERRIDE = 0x009E, 0x009F


def current_scale() -> int:
    """Escala efetiva do monitor principal, em %."""
    from ctypes import wintypes
    mon = ctypes.windll.user32.MonitorFromPoint(wintypes.POINT(0, 0), 1)  # MONITOR_DEFAULTTOPRIMARY
    x, y = wintypes.UINT(), wintypes.UINT()
    ctypes.windll.shcore.GetDpiForMonitor(wintypes.HANDLE(mon), 0, ctypes.byref(x), ctypes.byref(y))
    return round(x.value * 100 / 96)


def set_scale(target: int, timeout: float = 15.0) -> int:
    user32 = ctypes.windll.user32
    rel = ctypes.c_int(0)
    user32.SystemParametersInfoW(SPI_GETLOGICALDPIOVERRIDE, 0, ctypes.byref(rel), 1)
    recommended = -rel.value  # índice da escala recomendada na lista SCALES
    if not user32.SystemParametersInfoW(SPI_SETLOGICALDPIOVERRIDE, SCALES.index(target) - recommended, None, 1):
        raise OSError(f"o Windows recusou a escala {target}% (erro {ctypes.GetLastError()})")
    end = time.monotonic() + timeout
    while current_scale() != target and time.monotonic() < end:
        time.sleep(0.5)
    return current_scale()


def main(argv) -> int:
    if sys.platform != "win32":
        print("só no Windows")
        return 2
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # sem isso o Windows informa 96 DPI (100%) para este processo
    if len(argv) < 2:
        print(f"escala atual: {current_scale()}%")
        return 0
    target = int(argv[1].rstrip("%"))
    if target not in SCALES:
        print(f"escala inválida: {target} (use uma de {SCALES})")
        return 2
    before = current_scale()
    after = set_scale(target)
    print(f"escala da tela principal: {before}% -> {after}%")
    return 0 if after == target else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
