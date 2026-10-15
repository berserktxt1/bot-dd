"""Implementações reais de BattleView (captura + visão) e Shooter (teclado)."""
from __future__ import annotations

import logging
import time

from .automation.input import InputController
from .automation.safety import Aborted
from .capture import FrameSource
from .combat import BattleObservation, BattleView, Shooter, ShotOutcome
from .vision.perception import Perception, Snapshot, to_ruler

log = logging.getLogger(__name__)


class VisionBattleView(BattleView):
    def __init__(self, source: FrameSource, perception: Perception, config):
        self.source = source
        self.perception = perception
        self.config = config
        self.last_frame = None
        self.last_snapshot: Snapshot | None = None

    def observe(self) -> BattleObservation:
        frame = self.source.grab()
        if frame is None:
            return BattleObservation(False, None, notes=["sem imagem da janela"])
        snap = self.perception.analyze(frame)
        self.last_frame, self.last_snapshot = frame, snap
        over = snap.state if snap.state in ("vitoria", "derrota") else None
        # a batalha é considerada ativa pelo modelo de estado OU pela leitura do turno
        in_battle = snap.state == "batalha" or bool(snap.my_turn)
        obs = BattleObservation(in_battle=in_battle, my_turn=snap.my_turn, battle_over=over, snapshot=snap,
                                current_angle=snap.angle, notes=list(snap.warnings))
        target = self.perception.target(snap)
        conv = to_ruler(snap, target, snap.wind)
        confs = [snap.turn_confidence if snap.my_turn else 1.0]
        if snap.me:
            obs.me_x = snap.me.x / snap.unit_px
            confs.append(snap.me.confidence)
        if conv is not None:
            distance, dy, wind_rel, direction = conv
            obs.distance, obs.dy, obs.wind, obs.direction = distance, dy, wind_rel, direction
            obs.target_x, obs.target_y = target.x / snap.unit_px, target.y / snap.unit_px
            obs.target_visible = True
            confs.append(target.confidence)
            confs.append(snap.wind_confidence if snap.wind is not None else 0.0)
        else:
            obs.target_visible = False
        obs.confidence = float(min(confs)) if confs else 0.0
        return obs


class KeyboardShooter(Shooter):
    """Ajusta ângulo com as setas e segura a tecla de disparo pelo tempo/força desejados.

    Todos os parâmetros (teclas, tempo de carga total, leitura visual da barra) vêm da
    configuração e devem ser validados no cliente (Calibração > Teste de controles).
    """

    def __init__(self, inp: InputController, view: VisionBattleView, config):
        self.inp = inp
        self.view = view
        self.config = config
        self.assumed_angle: float | None = None
        self.assumed_facing: int | None = None

    def _keys(self):
        return self.config.get("automation.keys", {})

    def _read_angle(self):
        frame = self.view.source.grab()
        if frame is None:
            return None
        snap = Snapshot()
        self.view.perception.read_angle(frame, snap)
        return snap.angle if snap.angle_confidence >= 0.5 else None

    def face(self, direction: int):
        keys = self._keys()
        if self.assumed_facing == direction or not keys.get("face_left"):
            return
        self.inp.tap(keys["face_left"] if direction < 0 else keys["face_right"])
        self.assumed_facing = direction

    def set_angle(self, target: int, current: float | None):
        keys = self._keys()
        max_presses = int(self.config.get("automation.max_angle_presses", 120))
        for attempt in range(3):
            if current is None:
                current = self._read_angle() if attempt else None
            if current is None:
                current = self.assumed_angle
            if current is None:
                raise Aborted("ângulo atual desconhecido: treine a leitura do ângulo")
            diff = int(round(target - current))
            if diff == 0:
                break
            if abs(diff) > max_presses:
                raise Aborted(f"ajuste de ângulo excessivo ({diff})")
            self.inp.tap(keys.get("angle_up", "up") if diff > 0 else keys.get("angle_down", "down"), abs(diff))
            current = None
            self.assumed_angle = target
            read = self._read_angle()
            if read is None:
                break  # sem leitura: confia na contagem de toques
            current = read
            if int(round(read)) == target:
                break
        self.assumed_angle = target

    def charge_and_fire(self, force: float):
        fire = self._keys().get("fire", "space")
        full = float(self.config.get("automation.power_full_time_s", 4.0))
        if self.config.get("automation.power_mode") == "visual" and self.config.get("regions.power_bar"):
            def reached():
                frame = self.view.source.grab()
                if frame is None:
                    return False
                snap = Snapshot()
                self.view.perception.read_power(frame, snap)
                return snap.power is not None and snap.power >= force - 0.5
            self.inp.hold(fire, full * 1.2, until=reached, poll_s=0.005)
        else:
            self.inp.hold(fire, full * force / 100.0)

    def shoot(self, angle, force, direction, obs) -> ShotOutcome:
        log.info("executando disparo: ângulo %s, força %.1f, direção %s", angle, force, direction)
        self.face(direction)
        self.set_angle(angle, obs.current_angle)
        self.charge_and_fire(force)
        self.inp.kill.sleep(float(self.config.get("automation.post_shot_wait_s", 4.0)))
        return ShotOutcome()  # impacto real é marcado pelo usuário ou por detector futuro
