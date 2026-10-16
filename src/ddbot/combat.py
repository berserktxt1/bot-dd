"""Fluxo de combate: percepção -> mira -> (execução opcional) -> registro -> calibração.

Componentes trocáveis:
- ``BattleView``: fornece observações (visão real ou simulação).
- ``Shooter``: executa ângulo/força (teclado real ou simulação).
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum

from .aiming import Aimer, Recommendation, ShotContext, Weapon
from .automation.safety import Aborted, KillSwitch, TurnGate
from .calibration import Calibrator, ShotRecord
from .tracking import Decision, TargetTracker

log = logging.getLogger(__name__)


class Mode(str, Enum):
    ASSIST = "assistido"
    AUTO = "automatico"


@dataclass
class BattleObservation:
    in_battle: bool
    my_turn: bool | None
    distance: float | None = None       # régua
    dy: float = 0.0
    wind: float | None = None           # relativo ao disparo
    direction: int = 1                  # +1 inimigo à direita, -1 à esquerda
    target_id: str = "alvo"
    target_visible: bool = True
    target_x: float | None = None       # posição absoluta (régua) para o rastreador
    target_y: float | None = None
    me_x: float | None = None
    confidence: float = 0.0             # confiança mínima entre leituras usadas
    current_angle: float | None = None
    battle_over: str | None = None      # "vitoria" | "derrota" | None
    notes: list[str] = field(default_factory=list)
    snapshot: object = None


@dataclass
class ShotOutcome:
    impact_x: float | None = None        # régua, relativo ao atirador, no sentido do disparo
    hit: bool | None = None


class BattleView:
    def observe(self) -> BattleObservation:
        raise NotImplementedError


class Shooter:
    def shoot(self, angle: int, force: float, direction: int, obs: BattleObservation) -> ShotOutcome:
        raise NotImplementedError


@dataclass
class CombatEvent:
    kind: str           # recomendacao | disparo | aviso | turno | fim
    message: str
    data: dict = field(default_factory=dict)


class CombatEngine:
    def __init__(self, view: BattleView, shooter: Shooter | None, aimer: Aimer, calibrator: Calibrator,
                 tracker: TargetTracker, kill: KillSwitch, config, on_event=None, source="observado"):
        self.view = view
        self.shooter = shooter
        self.aimer = aimer
        self.calibrator = calibrator
        self.tracker = tracker
        self.kill = kill
        self.config = config
        self.on_event = on_event or (lambda e: None)
        self.source = source
        self.mode = Mode.ASSIST
        self.gate = TurnGate(float(config.get("automation.min_seconds_between_shots", 3.0)))
        self.last_recommendation: Recommendation | None = None
        self.last_observation: BattleObservation | None = None
        self.paused = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._recommended_turn = -1
        self._cache_key: tuple | None = None
        self.shots_this_battle = 0

    # ------------------------------------------------------------- autorização
    def auto_allowed(self) -> tuple[bool, str]:
        if not self.config.get("automation.server_rules_confirmed", False):
            return False, "automação não autorizada: confirme as regras do servidor nas Configurações"
        if self.shooter is None:
            return False, "nenhum executor de disparo disponível"
        return True, ""

    def set_mode(self, mode: Mode) -> tuple[bool, str]:
        if mode == Mode.AUTO:
            ok, why = self.auto_allowed()
            if not ok:
                return False, why
        self.mode = mode
        log.info("modo de combate: %s", mode.value)
        return True, ""

    def _emit(self, kind, message, **data):
        if kind == "aviso":
            log.warning(message)
        else:
            log.info(message)
        self.on_event(CombatEvent(kind, message, data))

    def weapon(self) -> Weapon:
        name = self.config.get("aim.weapon", "padrao")
        w = self.config.get(f"weapons.{name}", {}) or {}
        return Weapon(name=name, **{k: float(v) for k, v in w.items()
                                    if k in ("force_scale", "drag_scale", "angle_offset", "blast_radius")})

    def build_context(self, obs: BattleObservation, distance: float) -> ShotContext:
        allowed = self.config.get("aim.allowed_methods")
        return ShotContext(
            distance=distance, dy=obs.dy, wind=obs.wind or 0.0,
            target_width=float(self.config.get("aim.target_width", 0.35)),
            weapon=self.weapon(),
            sigma_wind=float(self.config.get("aim.sigma_wind", 0.1)) + (0.5 if obs.wind is None else 0.0),
            sigma_distance=float(self.config.get("aim.sigma_distance", 0.1)),
            allowed_methods=tuple(allowed) if allowed else None)

    def reset_battle(self):
        """Esquece alvos e cache ao começar uma nova batalha."""
        self.tracker.reset()
        self.shots_this_battle = 0
        self._cache_key = None
        self.last_recommendation = None

    # -------------------------------------------------------------- um passo
    def step(self) -> Recommendation | None:
        self.kill.check()
        obs = self.view.observe()
        self.last_observation = obs
        if obs.battle_over:
            self._emit("fim", f"batalha encerrada: {obs.battle_over}", result=obs.battle_over)
            self.reset_battle()
            return None
        if not obs.in_battle:
            return None
        turn = self.gate.update(obs.my_turn)
        if not obs.my_turn:
            return None

        # rastreamento do alvo (inclui invisibilidade)
        if obs.target_visible and obs.target_x is not None:
            self.tracker.observe(obs.target_id, obs.target_x, obs.target_y or 0.0, turn, obs.confidence)
            distance = obs.distance
        else:
            self.tracker.mark_hidden(obs.target_id, turn)
            decision = self.tracker.decide(obs.target_id, turn, has_area_attack=False)
            if decision.decision in (Decision.WAIT, Decision.ASK_USER) or decision.estimate is None:
                if self._recommended_turn != turn:
                    self._emit("aviso", f"alvo oculto: {decision.reason}", decisao=decision.decision.value)
                    self._recommended_turn = turn
                return None
            if obs.me_x is None:
                return None
            distance = abs(decision.estimate.center_x - obs.me_x)
            obs.notes.append(f"posição estimada ({decision.reason})")

        if distance is None or distance <= 0:
            return None
        # reaproveita o cálculo enquanto a leitura não muda de forma relevante no turno
        key = (turn, round(distance / 0.05), round((obs.wind or 0.0) / 0.1), round(obs.dy / 0.05),
               obs.wind is None)
        if key == self._cache_key and self.last_recommendation is not None:
            rec = self.last_recommendation
        else:
            rec = self.aimer.recommend(self.build_context(obs, distance))
            self.last_recommendation, self._cache_key = rec, key
        if self._recommended_turn != turn:
            self._recommended_turn = turn
            msg = rec.reason if rec.best else f"sem recomendação: {rec.reason}"
            self._emit("recomendacao", msg, rec=rec, obs=obs)

        if self.mode == Mode.AUTO and rec.best:
            self._auto_fire(rec, obs)
        return rec

    def _auto_fire(self, rec: Recommendation, obs: BattleObservation):
        ok, why = self.gate.can_shoot()
        if not ok:
            return
        min_conf = float(self.config.get("thresholds.vision_min_confidence", 0.7))
        min_p = float(self.config.get("thresholds.auto_min_hit_probability", 0.3))
        if obs.confidence < min_conf:
            self._emit("aviso", f"confiança visual baixa ({obs.confidence:.2f} < {min_conf}); disparo não executado")
            self.gate.mark_shot()  # não tenta de novo neste turno
            return
        if rec.best.hit_probability < min_p:
            self._emit("aviso", f"probabilidade estimada baixa ({rec.best.hit_probability:.0%}); disparo não executado")
            self.gate.mark_shot()
            return
        allowed, why = self.auto_allowed()
        if not allowed:
            self._emit("aviso", why)
            return
        b = rec.best
        self.gate.mark_shot()  # marca ANTES de executar: evita disparo duplicado se algo falhar
        try:
            outcome = self.shooter.shoot(b.angle, b.force, obs.direction, obs)
        except Aborted as exc:
            self._emit("aviso", f"disparo cancelado: {exc}")
            return
        self.record(rec, obs, outcome, mode=Mode.AUTO.value)

    def record(self, rec: Recommendation, obs: BattleObservation, outcome: ShotOutcome | None, mode: str):
        b = rec.best
        shot = ShotRecord(angle=b.angle, force=b.force, wind=rec.context.wind, distance=rec.context.distance,
                          dy=rec.context.dy, impact_x=outcome.impact_x if outcome else None,
                          hit=outcome.hit if outcome else None, method=b.method, weapon=rec.context.weapon.name,
                          source=self.source, mode=mode)
        shot_id = self.calibrator.record(shot)
        self._cache_key = None  # a calibração pode ter mudado
        self.shots_this_battle += 1
        res = "acerto" if shot.hit else ("erro" if shot.hit is False else "resultado pendente")
        self._emit("disparo", f"disparo #{shot_id}: {b.angle}°/{b.force:.1f} ({b.method}) -> {res}",
                   shot_id=shot_id, shot=shot)
        return shot_id

    # ---------------------------------------------------------------- laço
    def run(self, interval_s: float = 0.25):
        self._emit("turno", f"combate iniciado em modo {self.mode.value}")
        try:
            while not self.kill.triggered and not self._stop.is_set():
                if self.paused.is_set():
                    self.kill.sleep(0.2)
                    continue
                try:
                    self.step()
                except Aborted:
                    raise
                except Exception as exc:
                    log.exception("erro no passo de combate")
                    self._emit("aviso", f"erro no combate: {exc}; pausando")
                    self.paused.set()
                self.kill.sleep(interval_s)
        except Aborted:
            pass
        self._emit("fim", "combate parado")

    def stop(self):
        self._stop.set()

    def start(self, interval_s=0.25):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self.run, args=(interval_s,), daemon=True, name="combate")
        self._thread.start()

    def join(self, timeout=None):
        if self._thread:
            self._thread.join(timeout)
