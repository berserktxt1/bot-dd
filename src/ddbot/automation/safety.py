"""Travas de segurança: parada de emergência, janela em foco, turno único e autorização."""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger(__name__)


class Aborted(RuntimeError):
    """Ação cancelada por uma trava de segurança."""


class KillSwitch:
    """Uma vez acionado, nenhuma entrada é enviada até ``reset()`` explícito."""

    def __init__(self):
        self._stop = threading.Event()
        self._callbacks: list = []
        self.reason = ""

    def on_trigger(self, cb):
        self._callbacks.append(cb)

    def trigger(self, reason="parada de emergência"):
        if self._stop.is_set():
            return
        self.reason = reason
        self._stop.set()
        log.warning("PARADA: %s", reason)
        for cb in list(self._callbacks):
            try:
                cb()
            except Exception:
                log.exception("erro ao executar callback de parada")

    def reset(self):
        self._stop.clear()
        self.reason = ""

    @property
    def triggered(self) -> bool:
        return self._stop.is_set()

    def sleep(self, seconds: float):
        """Espera interrompível; levanta ``Aborted`` se a parada for acionada."""
        if self._stop.wait(max(0.0, seconds)):
            raise Aborted(self.reason)

    def check(self):
        if self._stop.is_set():
            raise Aborted(self.reason)


class TurnGate:
    """Permite no máximo um disparo por turno detectado e respeita intervalo mínimo."""

    def __init__(self, min_interval_s: float = 3.0):
        self.min_interval_s = min_interval_s
        self.turn_id = 0
        self._was_my_turn = False
        self._shot_turn = -1
        self._last_shot = 0.0

    def update(self, my_turn: bool | None) -> int:
        if my_turn and not self._was_my_turn:
            self.turn_id += 1
        self._was_my_turn = bool(my_turn)
        return self.turn_id

    def can_shoot(self) -> tuple[bool, str]:
        if not self._was_my_turn:
            return False, "não é meu turno"
        if self._shot_turn == self.turn_id:
            return False, "já disparou neste turno"
        if time.monotonic() - self._last_shot < self.min_interval_s:
            return False, "intervalo mínimo entre disparos"
        return True, ""

    def mark_shot(self):
        self._shot_turn = self.turn_id
        self._last_shot = time.monotonic()


class HotkeyListener:
    """Tecla global de emergência (pynput). Funciona mesmo com o jogo em foco."""

    def __init__(self, hotkey: str, callback):
        self.hotkey = hotkey
        self.callback = callback
        self._listener = None

    def start(self) -> bool:
        try:
            from pynput import keyboard
        except Exception as exc:  # pragma: no cover - depende do sistema
            log.warning("tecla global indisponível: %s", exc)
            return False
        try:
            self._listener = keyboard.GlobalHotKeys({self.hotkey: self.callback})
            self._listener.daemon = True
            self._listener.start()
            log.info("tecla de emergência ativa: %s", self.hotkey)
            return True
        except Exception as exc:  # pragma: no cover
            log.warning("não foi possível registrar %s: %s", self.hotkey, exc)
            return False

    def stop(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
