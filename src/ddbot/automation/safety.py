"""Travas de segurança: parada de emergência, janela em foco, turno único e autorização."""
from __future__ import annotations

import logging
import threading
import time
import weakref

log = logging.getLogger(__name__)


class Aborted(RuntimeError):
    """Ação cancelada por uma trava de segurança."""


class FocusLost(Aborted):
    """A janela do jogo não está na frente (Alt+Tab, minimizada, outra janela por cima)."""


class Cancelled(Aborted):
    """Pausa ou parada pedida pelo usuário no meio de uma ação."""


class InputBlocked(Aborted):
    """O Windows recusou o envio de teclas/cliques (ex.: jogo aberto como administrador)."""


class NeedsAttention(Aborted):
    """A estratégia não deve continuar sozinha (estado do chefe, etapa ou falta de progresso): pausa."""


class KillSwitch:
    """Uma vez acionado, nenhuma entrada é enviada até ``reset()`` explícito."""

    def __init__(self):
        self._stop = threading.Event()
        self._callbacks: list = []
        self._lock = threading.Lock()
        self.reason = ""

    def on_trigger(self, cb):
        """Registra ``cb``; métodos ligados são guardados por referência fraca (sem vazamento)."""
        ref = weakref.WeakMethod(cb) if hasattr(cb, "__self__") else (lambda cb=cb: cb)
        with self._lock:
            self._callbacks.append(ref)

    def trigger(self, reason="parada de emergência"):
        if self._stop.is_set():
            return
        self.reason = reason
        self._stop.set()
        log.warning("PARADA: %s", reason)
        with self._lock:
            refs = list(self._callbacks)
            self._callbacks = [r for r in refs if r() is not None]
        for ref in refs:
            cb = ref()
            if cb is None:
                continue
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
    """No máximo um disparo por turno, com o turno confirmado por leituras seguidas.

    - ``None`` (leitura falhou) mantém o estado anterior;
    - o turno só começa depois de ``confirm`` leituras True seguidas e só termina
      depois de ``confirm`` leituras False seguidas. Uma oscilação de um quadro não
      cria um turno novo (o que permitiria um segundo disparo).
    """

    def __init__(self, min_interval_s: float = 3.0, confirm: int = 2, clock=time.monotonic):
        self.min_interval_s = min_interval_s
        self.confirm = max(1, int(confirm))
        self.clock = clock
        self.turn_id = 0
        self._was_my_turn = False
        self._streak_value: bool | None = None
        self._streak = 0
        self._shot_turn = -1
        self._last_shot = -1e9

    def update(self, my_turn: bool | None) -> int:
        if my_turn is None:
            return self.turn_id
        if my_turn == self._streak_value:
            self._streak += 1
        else:
            self._streak_value, self._streak = my_turn, 1
        if self._streak >= self.confirm and my_turn != self._was_my_turn:
            self._was_my_turn = my_turn
            if my_turn:
                self.turn_id += 1
        return self.turn_id

    @property
    def my_turn(self) -> bool:
        return self._was_my_turn

    def can_shoot(self) -> tuple[bool, str]:
        if not self._was_my_turn:
            return False, "não é meu turno"
        if self._shot_turn == self.turn_id:
            return False, "já disparou neste turno"
        if self.clock() - self._last_shot < self.min_interval_s:
            return False, "intervalo mínimo entre disparos"
        return True, ""

    def mark_shot(self):
        self._shot_turn = self.turn_id
        self._last_shot = self.clock()

    def mark_done(self):
        """Chamado quando o disparo termina: o intervalo conta a partir do fim da ação."""
        self._last_shot = self.clock()

    def reset(self):
        self.turn_id = 0
        self._was_my_turn = False
        self._streak_value, self._streak = None, 0
        self._shot_turn = -1


class HotkeyListener:
    """Tecla global de emergência (pynput). Funciona mesmo com o jogo em foco."""

    def __init__(self, hotkey: str, callback):
        self.hotkey = hotkey
        self.callback = callback
        self._listener = None
        self.error = ""

    @staticmethod
    def validate(hotkey: str) -> str | None:
        """Mensagem de erro se a combinação for inválida; None se estiver ok."""
        if not hotkey or not isinstance(hotkey, str):
            return "informe uma tecla, por exemplo <f12>"
        try:
            from pynput import keyboard
        except Exception:
            return None  # sem pynput aqui (ex.: Linux de desenvolvimento): não dá para validar
        try:
            keyboard.HotKey.parse(hotkey)
        except Exception:
            return f"tecla inválida: {hotkey} (use o formato <f12> ou <ctrl>+<alt>+p)"
        return None

    def start(self) -> bool:
        try:
            from pynput import keyboard
        except Exception as exc:  # pragma: no cover - depende do sistema
            self.error = f"pynput indisponível: {exc}"
            log.warning("tecla global indisponível: %s", exc)
            return False
        try:
            self._listener = keyboard.GlobalHotKeys({self.hotkey: self.callback})
            self._listener.daemon = True
            self._listener.start()
            log.info("tecla de emergência ativa: %s", self.hotkey)
            return True
        except Exception as exc:  # pragma: no cover
            self.error = str(exc)
            log.warning("não foi possível registrar %s: %s", self.hotkey, exc)
            return False

    def stop(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
