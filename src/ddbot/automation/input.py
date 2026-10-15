"""Envio de teclas e cliques somente pelos controles normais do cliente (SendInput)."""
from __future__ import annotations

import logging
import threading
import time

from .. import winapi
from .safety import Aborted, KillSwitch

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
    def __init__(self, kill: KillSwitch, backend: InputBackend | None = None,
                 foreground_check=None, key_delay_s: float = 0.045):
        self.kill = kill
        self.backend = backend or InputBackend()
        self.foreground_check = foreground_check  # callable -> bool
        self.key_delay_s = key_delay_s
        self._held: set[str] = set()
        self._lock = threading.RLock()
        kill.on_trigger(self.release_all)

    def _guard(self):
        self.kill.check()
        if self.foreground_check is not None and not self.foreground_check():
            raise Aborted("janela do jogo não está em foco")

    def key_down(self, key):
        with self._lock:
            self._guard()
            self.backend.key(key, False)
            self._held.add(key)

    def key_up(self, key):
        with self._lock:
            if key in self._held:
                self.backend.key(key, True)
                self._held.discard(key)

    def release_all(self):
        with self._lock:
            for key in list(self._held):
                try:
                    self.backend.key(key, True)
                except Exception:
                    log.exception("falha ao soltar %s", key)
            self._held.clear()

    def tap(self, key, times=1):
        for _ in range(times):
            self.key_down(key)
            try:
                self.kill.sleep(self.key_delay_s)
            finally:
                self.key_up(key)
            self.kill.sleep(self.key_delay_s)

    def hold(self, key, seconds: float, until=None, poll_s=0.01):
        """Segura a tecla por ``seconds`` ou até ``until()`` retornar True."""
        self.key_down(key)
        try:
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                if until is not None and until():
                    break
                self.kill.check()
                if self.foreground_check is not None and not self.foreground_check():
                    raise Aborted("janela do jogo perdeu o foco")
                time.sleep(poll_s)
        finally:
            self.key_up(key)

    def click(self, x, y):
        with self._lock:
            self._guard()
            self.backend.click(int(x), int(y))
        self.kill.sleep(self.key_delay_s)
