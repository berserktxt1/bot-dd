"""Fluxo de combate: percepção -> mira -> (execução opcional) -> registro -> calibração.

Componentes trocáveis:
- ``BattleView``: fornece observações (visão real ou simulação).
- ``Shooter``: executa ângulo/força (teclado real ou simulação).
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum

from .aiming import Aimer, Recommendation, ShotContext, Weapon
from .automation.safety import Aborted, Cancelled, FocusLost, InputBlocked, KillSwitch, NeedsAttention, TurnGate
from .calibration import Calibrator, ShotRecord
from .strategy import HIGH_ARC_MIN_ANGLE
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
    me_y: float | None = None
    wind_screen: float | None = None    # vento como aparece na tela (+ = para a direita)
    wind_confidence: float = 1.0
    confidence: float = 0.0             # confiança mínima entre leituras usadas
    current_angle: float | None = None
    battle_over: str | None = None      # "vitoria" | "derrota" | None
    # estratégia da instância (``strategy.Plan``): etapa, espera, pausa e tiro alto obrigatório
    stage: str | None = None
    wait_reason: str | None = None      # não atira neste turno (alvo imune, nenhum alvo da etapa...)
    pause_reason: str | None = None     # pede intervenção (pavio aceso, etapa fora do escopo...)
    high_arc: bool = False              # só tiro por cima (ângulo >= 60)
    target_missing: bool = False        # a espera é porque nenhum alvo da etapa foi encontrado
    turn_score: float | None = None     # semelhança do indicador de turno (mostrada quando o turno não aparece)
    weak_reads: list[str] = field(default_factory=list)  # leituras abaixo da confiança mínima, com o valor
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
                 tracker: TargetTracker, kill: KillSwitch, config, on_event=None, source="observado",
                 cancel_check=None):
        self.view = view
        self.shooter = shooter
        self.aimer = aimer
        self.calibrator = calibrator
        self.tracker = tracker
        self.kill = kill
        self.config = config
        self.on_event = on_event or (lambda e: None)
        self.source = source
        self.cancel_check = cancel_check  # callable -> motivo (pausa/parada pedida) ou None
        self.planner = None  # strategy.StrategyPlanner da instância (opcional)
        self.context: dict = {}  # instância, dificuldade e atividade (vão para o registro de cada disparo)
        self.mode = Mode.ASSIST
        self.gate = self._new_gate()
        self._bad_reads = 0
        self._bad_since: float | None = None
        self._over_candidate: str | None = None
        self._over_reads = 0
        self.last_recommendation: Recommendation | None = None
        self.last_observation: BattleObservation | None = None
        self.paused = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._recommended_turn = -1
        self._cache_key: tuple | None = None
        self._steady: tuple | None = None  # (turno, método, ângulo) da recomendação mantida no turno
        self.shots_this_battle = 0
        # o bot não fica parado em silêncio: turno ilegível ou turnos seus sem mira viram aviso e, no automático,
        # pausa com o motivo (a janela do JonFlow volta à frente)
        self.clock = time.monotonic
        self._noturn_since: float | None = None
        self._noturn_warned = False
        self._stuck_turn: int | None = None
        self._stuck_message = ""
        self._stuck_turns = 0
        # confirmação do disparo: depois dele o turno precisa passar; se continuar seu, o jogo não recebeu as teclas
        self._confirm: tuple[int, float] | None = None  # (turno do disparo, quando a espera pós-disparo acabou)
        self._unconfirmed = 0

    STALL_WARN_S = 20.0    # batalha na tela sem conseguir ler de quem é o turno: avisa
    STALL_PAUSE_S = 60.0   # ... e, no automático, pausa explicando
    # o indicador é lido, mas o seu turno nunca aparece (modelo que não casa com o jogo): avisa e pausa. Mais
    # tempo que acima, porque os turnos dos adversários (várias formigas, por exemplo) passam antes do seu
    NO_TURN_WARN_S = 60.0
    NO_TURN_PAUSE_S = 150.0
    LOST_TURNS_PAUSE = 2   # turnos seus seguidos sem disparar (sem mira, leitura ruim, disparo cancelado): pausa
    WAIT_TURNS_PAUSE = 3   # turnos seus seguidos sem nenhum alvo da etapa na tela: pausa
    # depois da espera pós-disparo, o turno precisa ter passado até aqui; curto para o relógio do turno do jogo
    # não "confirmar" sozinho um disparo que não aconteceu (o tempo do turno no DDClássico não foi medido)
    SHOT_CONFIRM_S = 5.0
    UNCONFIRMED_PAUSE = 2  # disparos seguidos sem o turno passar: pausa (as teclas não chegam ao jogo)

    # diferença mínima de chance para trocar de ângulo no mesmo turno: leituras que oscilam um pouco não fazem
    # a recomendação pular entre dois ângulos (menos teclas e um número estável na tela)
    STEADY_MARGIN = 0.05

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

    def _new_gate(self) -> TurnGate:
        return TurnGate(float(self.config.get("automation.min_seconds_between_shots", 3.0)),
                        confirm=int(self.config.get("automation.turn_confirm_reads", 2)))

    def _watch_turn(self, obs: BattleObservation, allow_fire: bool):
        """Batalha na tela sem o seu turno aparecer: avisa e, no automático, pausa explicando.

        Turno ilegível (indicador não calibrado) pausa em ``STALL_PAUSE_S``. Indicador lido que nunca reconhece o
        seu turno pausa em ``NO_TURN_PAUSE_S``: sem isso o bot ficava parado até o limite da batalha (15 min) sem
        dizer nada, como se o turno fosse sempre dos adversários.
        """
        if self.gate.my_turn:
            self._noturn_since, self._noturn_warned = None, False
            return
        now = self.clock()
        if self._noturn_since is None:
            self._noturn_since = now
            return
        waited = now - self._noturn_since
        if obs.my_turn is None:
            why = ("a batalha está na tela, mas o bot não consegue ler se é o seu turno: confira o modelo \"Indicador "
                   "de que é o seu turno\" e a região do indicador de turno (Calibração; o Diagnóstico mostra a "
                   "leitura)")
            warn_s, pause_s = self.STALL_WARN_S, self.STALL_PAUSE_S
        else:
            score = "" if obs.turn_score is None else (
                f" (semelhança do indicador de turno {obs.turn_score:.2f}, mínimo "
                f"{float(self.config.get('thresholds.template', 0.8)):.2f})").replace(".", ",")
            why = (f"há {waited:.0f} s na batalha sem reconhecer o seu turno{score}: se já foi a sua vez nesse tempo, "
                   "capture de novo o \"Indicador de que é o seu turno\" no seu turno e confira a região do indicador "
                   "(Calibração; o Diagnóstico mostra a leitura)")
            warn_s, pause_s = self.NO_TURN_WARN_S, self.NO_TURN_PAUSE_S
        if waited >= pause_s and self.mode == Mode.AUTO and allow_fire:
            self._noturn_since, self._noturn_warned = None, False
            raise NeedsAttention(why)
        if waited >= warn_s and not self._noturn_warned:
            self._noturn_warned = True
            self._emit("aviso", f"{why}; sem isso o bot não dispara")

    def _check_shot_confirmed(self, allow_fire: bool):
        """O disparo só conta como feito quando o turno passa; turno seu muito depois dele = teclas não chegaram."""
        if self._confirm is None:
            return
        shot_turn, since = self._confirm
        if self.gate.turn_id != shot_turn or not self.gate.my_turn:
            self._confirm, self._unconfirmed = None, 0
            self._emit("turno", "disparo confirmado: o turno passou")
            return
        if self.clock() - since < self.SHOT_CONFIRM_S:
            return
        self._confirm = None
        self._unconfirmed += 1
        why = ("o disparo não foi confirmado: o turno continua seu depois dele. O jogo pode não ter recebido as teclas "
               "(confira as teclas em Configurações e se o jogo está em foco; use Calibração > Testar teclas do "
               "ângulo)")
        self._emit("aviso", why)
        if self._unconfirmed >= self.UNCONFIRMED_PAUSE and self.mode == Mode.AUTO and allow_fire:
            self._unconfirmed = 0
            raise NeedsAttention(f"{self.UNCONFIRMED_PAUSE} disparos seguidos sem confirmação: {why}")

    @staticmethod
    def _why_no_distance(obs: BattleObservation) -> str:
        snap = obs.snapshot
        if snap is not None and getattr(snap, "me", 1) is None:
            return "seu personagem não foi encontrado (Calibração > Modelos: marcador do seu personagem)"
        if snap is not None and not getattr(snap, "enemies", [1]):
            return "nenhum inimigo foi encontrado (marcador de um inimigo ou os alvos da instância em Calibração)"
        if snap is not None and not getattr(snap, "unit_px", 1):
            return "a régua não está calibrada (Calibração > Regiões: área de jogo)"
        return "a distância até o alvo não pôde ser calculada"

    @staticmethod
    def _why_no_target(obs: BattleObservation) -> str:
        snap = obs.snapshot
        if snap is not None and not getattr(snap, "enemies", [1]):
            return (f"{obs.wait_reason}: nenhum inimigo foi encontrado na tela (Calibração > Modelos: marcador de um "
                    "inimigo, ou os alvos da instância em Calibração > Alvos)")
        return (f"{obs.wait_reason}: os inimigos vistos não são alvos desta etapa (confira os alvos da instância em "
                "Calibração > Alvos)")

    def _lose_turn(self, turn: int, message: str, why: str, allow_fire: bool, limit: int | None = None):
        """Seu turno sem disparo: avisa uma vez por turno; turnos seguidos assim pausam no automático.

        Vale para mira impossível, leitura ruim, disparo cancelado e nenhum alvo na tela: antes, só a falta de
        mira contava, e as outras causas se repetiam a cada turno sem pausar nem mudar a mensagem.
        """
        limit = limit or self.LOST_TURNS_PAUSE
        if self._stuck_turn == turn:
            if message != self._stuck_message:  # outro motivo no mesmo turno: diz, mas não conta de novo
                self._stuck_message = message
                self._emit("aviso", message)
            return None
        self._stuck_turn, self._stuck_message = turn, message
        self._stuck_turns += 1
        self._emit("aviso", message)
        if self._stuck_turns >= limit and self.mode == Mode.AUTO and allow_fire:
            n, self._stuck_turns = self._stuck_turns, 0
            raise NeedsAttention(f"{n} turnos seus seguidos sem disparar: {why}")
        return None

    def _cannot_aim(self, turn: int, why: str, allow_fire: bool):
        """Seu turno, mas sem mira (personagem, inimigo ou régua)."""
        return self._lose_turn(turn, f"seu turno, mas sem mira: {why}", why, allow_fire)

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

    def _sigma_wind(self, obs: BattleObservation) -> float:
        base = float(self.config.get("aim.sigma_wind", 0.1))
        if obs.wind is None:
            return base + 0.5
        # leitura duvidosa do vento aumenta a incerteza em proporção ao valor lido
        doubt = max(0.0, 1.0 - float(obs.wind_confidence))
        return base + doubt * max(0.3, abs(obs.wind))

    def build_context(self, obs: BattleObservation, distance: float, extra_sigma_distance: float = 0.0
                      ) -> ShotContext:
        allowed = self.config.get("aim.allowed_methods")
        return ShotContext(
            distance=distance, dy=obs.dy, wind=obs.wind or 0.0,
            target_width=float(self.config.get("aim.target_width", 0.35)),
            weapon=self.weapon(),
            sigma_wind=self._sigma_wind(obs),
            sigma_distance=float(self.config.get("aim.sigma_distance", 0.1)) + extra_sigma_distance,
            allowed_methods=tuple(allowed) if allowed else None,
            angle_min=HIGH_ARC_MIN_ANGLE if obs.high_arc else 0)

    def reset_battle(self):
        """Esquece alvos e cache ao começar uma nova batalha."""
        self.tracker.reset()
        self.shots_this_battle = 0
        self._cache_key = None
        self.last_recommendation = None
        self._recommended_turn = -1
        self._steady = None
        self._bad_reads = 0
        self._bad_since = None
        self._noturn_since, self._noturn_warned = None, False
        self._confirm, self._unconfirmed = None, 0  # a batalha acabou: o último disparo teve efeito
        old_gate, self.gate = self.gate, self._new_gate()  # o turno da batalha anterior não vale mais
        self.gate._last_shot = old_gate._last_shot  # o intervalo mínimo entre disparos continua valendo
        for part in (self.shooter, self.view):
            reset = getattr(part, "reset", None)
            if callable(reset):
                reset()

    # -------------------------------------------------------------- um passo
    def step(self, allow_fire: bool = True) -> Recommendation | None:
        """Um passo. ``allow_fire=False`` só observa e sugere (ex.: tela da batalha incerta)."""
        self.kill.check()
        obs = self.view.observe()
        self.last_observation = obs
        if obs.battle_over:
            # um quadro de explosão parecido com a tela de vitória não pode zerar o turno (abriria
            # um segundo disparo): o fim só vale depois de leituras seguidas iguais
            if obs.battle_over == self._over_candidate:
                self._over_reads += 1
            else:
                self._over_candidate, self._over_reads = obs.battle_over, 1
            if self._over_reads < int(self.config.get("automation.battle_over_confirm_reads", 2)):
                return None
            self._over_candidate, self._over_reads = None, 0
            self._emit("fim", f"batalha encerrada: {obs.battle_over}", result=obs.battle_over)
            self.reset_battle()
            return None
        self._over_candidate, self._over_reads = None, 0
        if not obs.in_battle:
            return None
        prev_turn = self.gate.turn_id
        turn = self.gate.update(obs.my_turn)
        if turn != prev_turn:
            self._bad_reads = 0
            self._bad_since = None
        self._check_shot_confirmed(allow_fire)
        self._watch_turn(obs, allow_fire)
        if not self.gate.my_turn or not obs.my_turn:
            return None
        if obs.pause_reason:
            if self.mode == Mode.AUTO and allow_fire:
                raise NeedsAttention(obs.pause_reason)
            if self._recommended_turn != turn:
                self._recommended_turn = turn
                self._emit("aviso", obs.pause_reason)
            return None
        if obs.wait_reason:
            if obs.target_missing:
                # nenhum alvo da etapa na tela: antes esperava turno após turno até o limite da batalha, sem pausar
                return self._lose_turn(turn, f"aguardando: {obs.wait_reason}", self._why_no_target(obs), allow_fire,
                                       self.WAIT_TURNS_PAUSE)
            if self._recommended_turn != turn:
                self._recommended_turn = turn
                self._emit("aviso", f"aguardando: {obs.wait_reason}")
            return None
        extra_sigma = 0.0

        # rastreamento do alvo (inclui invisibilidade)
        if obs.target_visible and obs.target_x is not None:
            self.tracker.observe(obs.target_id, obs.target_x, obs.target_y or 0.0, turn, obs.confidence)
            distance = obs.distance
        else:
            self.tracker.mark_hidden(obs.target_id, turn)
            decision = self.tracker.decide(obs.target_id, turn, has_area_attack=False)
            seen = self.tracker.targets.get(obs.target_id)
            if decision.estimate is None and (seen is None or seen.last is None):
                # nenhum alvo nesta batalha até agora: não é "alvo escondido", é inimigo não encontrado
                return self._cannot_aim(turn, self._why_no_distance(obs), allow_fire)
            if decision.decision == Decision.ASK_USER:
                why = f"alvo oculto: {decision.reason}"
                return self._lose_turn(turn, why, why, allow_fire, self.WAIT_TURNS_PAUSE)
            if decision.decision == Decision.WAIT or decision.estimate is None:
                if self._recommended_turn != turn:
                    self._emit("aviso", f"alvo oculto: {decision.reason}", decisao=decision.decision.value)
                    self._recommended_turn = turn
                return None
            if obs.me_x is None:
                return self._cannot_aim(turn, "seu personagem não foi encontrado (Calibração > Modelos: "
                                              "marcador do seu personagem)", allow_fire)
            est = decision.estimate
            dx = est.center_x - obs.me_x
            # direção, vento e altura vêm da região estimada (o alvo não está visível)
            obs.direction = 1 if dx >= 0 else -1
            distance = abs(dx)
            if obs.wind_screen is not None:
                obs.wind = obs.wind_screen * obs.direction
            if obs.me_y is not None:
                obs.dy = obs.me_y - est.center_y
            extra_sigma = est.radius / 3 ** 0.5  # desvio de uma posição uniforme em ±raio
            obs.notes.append(f"posição estimada ({decision.reason})")

        if distance is None or distance <= 0:
            return self._cannot_aim(turn, self._why_no_distance(obs), allow_fire)
        # reaproveita o cálculo enquanto a leitura não muda de forma relevante no turno
        key = (turn, round(distance / 0.05), round((obs.wind or 0.0) / 0.1), round(obs.dy / 0.05),
               obs.wind is None, obs.high_arc)
        if key == self._cache_key and self.last_recommendation is not None:
            rec = self.last_recommendation
        else:
            rec = self.keep_steady(self.aimer.recommend(self.build_context(obs, distance, extra_sigma)), turn)
            self.last_recommendation, self._cache_key = rec, key
        if self._recommended_turn != turn:
            self._recommended_turn = turn
            msg = rec.reason if rec.best else f"sem recomendação: {rec.reason}"
            self._emit("recomendacao", msg, rec=rec, obs=obs)

        if self.mode == Mode.AUTO and rec.best and allow_fire:
            self._auto_fire(rec, obs)
        elif self.mode != Mode.AUTO and rec.best:
            self._stuck_turns = 0  # mira assistida: a sugestão está na tela
        return rec

    def keep_steady(self, rec: Recommendation, turn: int) -> Recommendation:
        """No mesmo turno, mantém o ângulo já recomendado enquanto ele continuar quase tão bom quanto o melhor."""
        if rec.best is None:
            return rec
        prev = self._steady
        if prev is not None and prev[0] == turn and (prev[1], prev[2]) != (rec.best.method, rec.best.angle):
            same = next((c for c in rec.candidates if (c.method, c.angle) == (prev[1], prev[2])), None)
            if same is not None and not same.blocked and \
                    rec.best.hit_probability - same.hit_probability < self.STEADY_MARGIN:
                rec.best = same
                rec.reason = f"{same.method}: {same.angle}° / {same.force:.1f} (P≈{same.hit_probability:.0%})"
        self._steady = (turn, rec.best.method, rec.best.angle)
        return rec

    def _auto_fire(self, rec: Recommendation, obs: BattleObservation):
        ok, why = self.gate.can_shoot()
        if not ok:
            return
        min_conf = float(self.config.get("thresholds.vision_min_confidence", 0.7))
        min_p = float(self.config.get("thresholds.auto_min_hit_probability", 0.3))
        problem = None
        if obs.confidence < min_conf:
            # diz QUAL leitura está ruim (antes só o número, igual em todo turno): é o que o usuário recalibra
            weak = f": {', '.join(obs.weak_reads)}" if obs.weak_reads else ""
            problem = f"confiança visual baixa ({obs.confidence:.2f} < {min_conf}){weak}"
        elif rec.best.hit_probability < min_p:
            problem = f"probabilidade estimada baixa ({rec.best.hit_probability:.0%})"
        if problem:
            # leituras ruins no começo do turno são comuns (câmera se movendo, números animando):
            # só desiste do turno depois de algumas leituras E de alguns segundos seguidos assim
            self._bad_reads += 1
            now = time.monotonic()
            if self._bad_since is None:
                self._bad_since = now
            if self._bad_reads >= int(self.config.get("automation.bad_reads_per_turn", 3)) and \
                    now - self._bad_since >= float(self.config.get("automation.bad_read_seconds", 5.0)):
                self.gate.mark_shot()
                self._lose_turn(self.gate.turn_id, f"{problem}; disparo não executado neste turno", problem, True)
            return
        self._bad_since = None
        allowed, why = self.auto_allowed()
        if not allowed:
            self._emit("aviso", why)
            return
        b = rec.best
        self.gate.mark_shot()  # marca ANTES de executar: evita disparo duplicado se algo falhar
        try:
            outcome = self.shooter.shoot(b.angle, b.force, obs.direction, obs)
        except (FocusLost, Cancelled, InputBlocked):
            raise  # a rotina decide (pausar); não é um "disparo cancelado" comum
        except Aborted as exc:
            if self.kill.triggered:
                raise
            self.gate.mark_done()
            why = f"disparo cancelado: {exc}"
            self._lose_turn(self.gate.turn_id, why, why, True)
            return
        self._stuck_turns = 0
        # registra antes de esperar a animação: uma parada durante a espera não perde o disparo
        self.record(rec, obs, outcome, mode=Mode.AUTO.value)
        self._wait_after_shot()
        self.gate.mark_done()
        self._confirm = (self.gate.turn_id, self.clock())  # o turno precisa passar (_check_shot_confirmed)
        stalled = self.planner.on_shot() if self.planner is not None else None
        if stalled:
            raise NeedsAttention(stalled)

    def _wait_after_shot(self):
        end = time.monotonic() + float(self.config.get("automation.post_shot_wait_s", 4.0))
        while time.monotonic() < end:
            if self.cancel_check is not None and self.cancel_check():
                return
            self.kill.sleep(min(0.05, max(0.0, end - time.monotonic())))

    def record(self, rec: Recommendation, obs: BattleObservation, outcome: ShotOutcome | None, mode: str):
        b = rec.best
        ctx = self.context
        shot = ShotRecord(angle=b.angle, force=b.force, wind=rec.context.wind, distance=rec.context.distance,
                          dy=rec.context.dy, impact_x=outcome.impact_x if outcome else None,
                          hit=outcome.hit if outcome else None, method=b.method, weapon=rec.context.weapon.name,
                          source=self.source, mode=mode, instance=ctx.get("instancia", ""),
                          difficulty=ctx.get("dificuldade", ""), stage=obs.stage or "",
                          target=obs.target_id.rsplit("_", 1)[0] if obs.target_id else "")
        shot_id = self.calibrator.record(shot)
        self._cache_key = None  # a calibração pode ter mudado
        self.shots_this_battle += 1
        res = "acerto" if shot.hit else ("erro" if shot.hit is False else "resultado pendente")
        self._emit("disparo", f"disparo #{shot_id}: {b.angle}°/{b.force:.1f} ({b.method}) -> {res}",
                   shot_id=shot_id, shot=shot)
        return shot_id

    # ---------------------------------------------------------------- laço
    def run(self, interval_s: float = 0.25):
        """Laço da mira assistida: só observa e sugere. Erros passageiros não o matam."""
        self._emit("turno", f"combate iniciado em modo {self.mode.value}")
        errors = 0
        try:
            while not self.kill.triggered and not self._stop.is_set():
                if self.paused.is_set():
                    self.kill.sleep(0.2)
                    continue
                try:
                    self.step()
                    errors = 0
                except Aborted:
                    raise
                except Exception as exc:
                    errors += 1
                    log.exception("erro no passo de combate")
                    if errors >= 5:
                        self._emit("aviso", f"mira assistida parada após erros repetidos: {exc}")
                        break
                    self._emit("aviso", f"erro na leitura do combate: {exc}; tentando de novo")
                    self.kill.sleep(2.0)
                self.kill.sleep(interval_s)
        except Aborted:
            pass
        finally:
            hook = getattr(self, "on_thread_exit", None)
            if callable(hook):
                hook()
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
