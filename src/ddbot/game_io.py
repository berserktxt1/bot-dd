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
        # atraso de reação (captura + SendInput) compensado em pontos de força; calibrável
        force = max(1.0, force - float(self.config.get("automation.power_offset", 0.0)))
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
        try:
            self.set_angle(angle, obs.current_angle)
        except Aborted:
            # sem confirmar o ângulo não atira; passa o turno se houver tecla configurada
            pass_key = self._keys().get("pass_turn")
            if pass_key and not self.inp.kill.triggered:
                log.warning("ângulo não confirmado: passando o turno")
                self.inp.tap(pass_key)
            raise
        self.charge_and_fire(force)
        self.inp.kill.sleep(float(self.config.get("automation.post_shot_wait_s", 4.0)))
        return ShotOutcome()  # impacto real é marcado pelo usuário ou por detector futuro


# ------------------------------------------------------------ atividades (telas e botões)
from .activities import Actor, ScreenReader, ScreenState  # noqa: E402
from .vision.templates import TemplateLibrary  # noqa: E402


class VisionScreenReader(ScreenReader):
    """Identifica a tela atual pelos modelos ``estado_*``."""

    def __init__(self, source: FrameSource, perception: Perception):
        self.source = source
        self.perception = perception
        self.last: ScreenState | None = None

    def read(self) -> ScreenState:
        frame = self.source.grab()
        if frame is None:
            self.last = ScreenState("desconhecido", 0.0, None)
            return self.last
        snap = Snapshot(width=frame.shape[1], height=frame.shape[0])
        self.perception.classify_state(frame, snap)
        self.last = ScreenState(snap.state, snap.state_confidence, frame)
        return self.last


class GameActor(Actor):
    """Clica em botões localizados por modelo de imagem, só com a janela do jogo em foco.

    Proteções: limiar de confiança, intervalo mínimo entre cliques no mesmo botão e
    conversão de coordenadas pela posição atual da janela (nunca coordenadas fixas).
    """

    def __init__(self, inp: InputController, source: FrameSource, templates: TemplateLibrary, config,
                 min_repeat_s: float = 1.0, clock=time.monotonic):
        self.inp = inp
        self.source = source
        self.templates = templates
        self.config = config
        self.min_repeat_s = min_repeat_s
        self.clock = clock
        self._last_click: dict[str, float] = {}

    def threshold(self) -> float:
        return float(self.config.get("thresholds.template", 0.8))

    def find(self, template: str, frame):
        if frame is None or not self.templates.has(template):
            return None
        m = self.templates.best(template, frame)
        return m if m and m.score >= self.threshold() else None

    def click(self, template: str, frame) -> bool:
        m = self.find(template, frame)
        if m is None:
            return False
        now = self.clock()
        if now - self._last_click.get(template, -1e9) < self.min_repeat_s:
            log.info("clique em %s ignorado (repetido rápido demais)", template)
            return False
        ox, oy = self.source.origin
        cx, cy = m.center
        self._last_click[template] = now
        log.info("clicando em %s (%.2f) em %d,%d", template, m.score, cx, cy)
        self.inp.click(ox + cx, oy + cy)
        return True

    def press(self, key: str):
        self.inp.tap(key)
