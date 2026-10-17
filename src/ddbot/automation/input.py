"""Envio de teclas e cliques somente pelos controles normais do cliente (SendInput)."""
from __future__ import annotations

import logging
import threading
import time

from .. import winapi
from .safety import Aborted, Cancelled, FocusLost, KillSwitch

log = logging.getLogger(__name__)


class InputBackend:
    """Interface de baixo nível (substituída por um falso nos testes)."""

    def key(self, key: str, up: bool):
        winapi.send_key(key, up)

    def click(self, x: int, y: int):
        winapi.mouse_click(x, y)


class RecordingBackend(InputBackend):
    def __init__(self):
        self.events: list[tuple] = []

    def key(self, key, up):
        self.events.append(("key", key, up))

    def click(self, x, y):
        self.events.append(("click", x, y))


class InputController:
    """Entrada com travas.

    - parada de emergência: verificada antes de cada envio e solta tudo que estiver pressionado;
    - foco: nada é enviado se a janela do jogo não estiver na frente (``FocusLost``);
    - ``cancel_check``: pausa/parada pedida pelo usuário interrompe entre uma tecla e outra
      (``Cancelled``). Uma carga de força já começada vai até o fim, porque soltar a tecla
      no meio também dispara.
    """

    def __init__(self, kill: KillSwitch, backend: InputBackend | None = None,
                 foreground_check=None, key_delay_s: float = 0.045, cancel_check=None, key_focus_check=None):
        self.kill = kill
        self.backend = backend or InputBackend()
        self.foreground_check = foreground_check  # callable -> bool (janela do jogo na frente)
        # callable -> bool: o foco do TECLADO está na área do jogo (e não num campo do launcher)
        self.key_focus_check = key_focus_check
        self.cancel_check = cancel_check          # callable -> str | None (motivo)
        self.key_delay_s = key_delay_s
        self._held: set[str] = set()
        self._lock = threading.RLock()
        kill.on_trigger(self.release_all)

    def _guard(self, allow_cancel=True):
        self.kill.check()
        if allow_cancel and self.cancel_check is not None:
            why = self.cancel_check()
            if why:
                raise Cancelled(why)
        if self.foreground_check is not None and not self.foreground_check():
            raise FocusLost("a janela do jogo não está na frente")

    def key_down(self, key):
        with self._lock:
            self._guard()
            if self.key_focus_check is not None and not self.key_focus_check():
                raise FocusLost("o foco do teclado não está na área do jogo (clique dentro do jogo)")
            self.backend.key(key, False)
            self._held.add(key)

    def key_up(self, key):
        with self._lock:
            if key in self._held:
                self.backend.key(key, True)
                self._held.discard(key)  # só depois de soltar: se falhar, release_all tenta de novo

    def release_all(self):
        with self._lock:
            for key in list(self._held):
                try:
                    self.backend.key(key, True)
                except Exception:
                    log.exception("falha ao soltar %s", key)
            self._held.clear()

    def sleep(self, seconds: float):
        """Espera interrompível por emergência e por pausa/parada."""
        end = time.monotonic() + seconds
        while True:
            self._guard_cancel_only()
            left = end - time.monotonic()
            if left <= 0:
                return
            self.kill.sleep(min(0.05, left))

    def _guard_cancel_only(self):
        self.kill.check()
        if self.cancel_check is not None:
            why = self.cancel_check()
            if why:
                raise Cancelled(why)

    def tap(self, key, times=1):
        for _ in range(times):
            self.key_down(key)
            try:
                self.kill.sleep(self.key_delay_s)
            finally:
                self.key_up(key)
            self.kill.sleep(self.key_delay_s)

    def hold(self, key, seconds: float, until=None, poll_s=0.01) -> bool:
        """Segura a tecla por ``seconds`` ou até ``until()``. Devolve True se ``until`` foi atingido."""
        self.key_down(key)
        reached = False
        try:
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                if until is not None and until():
                    reached = True
                    break
                self.kill.check()
                if self.foreground_check is not None and not self.foreground_check():
                    raise FocusLost("a janela do jogo perdeu o foco")
                if self.key_focus_check is not None and not self.key_focus_check():
                    raise FocusLost("o foco do teclado saiu da área do jogo")
                time.sleep(poll_s)
        finally:
            self.key_up(key)
        return reached

    def click(self, x, y):
        with self._lock:
            self._guard()
            self.backend.click(int(x), int(y))
        self.kill.sleep(self.key_delay_s)

    def close(self):
        self.release_all()


__all__ = ["InputController", "InputBackend", "RecordingBackend", "Aborted"]
