"""Acompanhamento de alvos, incluindo alvos que ficaram invisíveis.

Regras (ver docs/RESEARCH.md):
- Só usamos o que a interface mostra. Nada de ler memória ou tráfego para revelar o alvo.
- A última posição conhecida NÃO é tratada como posição atual: a incerteza cresce com
  cada turno sem observação, de acordo com o deslocamento máximo configurado.
- Se a incerteza ficar grande demais, a decisão é aguardar ou pedir intervenção.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum


class Visibility(str, Enum):
    VISIBLE = "visivel"
    HIDDEN = "invisivel"
    UNKNOWN = "desconhecido"


@dataclass
class Observation:
    x: float                 # posição em coordenadas de tela normalizadas pela régua
    y: float
    turn: int
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0


@dataclass
class TrackedTarget:
    target_id: str
    history: list[Observation] = field(default_factory=list)
    visibility: Visibility = Visibility.UNKNOWN
    hidden_since_turn: int | None = None

    @property
    def last(self) -> Observation | None:
        return self.history[-1] if self.history else None


@dataclass
class HiddenEstimate:
    center_x: float
    center_y: float
    radius: float            # meia-largura da região provável (régua)
    turns_hidden: int
    based_on: str


class Decision(str, Enum):
    SHOOT = "atirar"
    AREA_ATTACK = "ataque_de_area"
    WAIT = "aguardar"
    ASK_USER = "pedir_intervencao"


@dataclass
class TargetDecision:
    decision: Decision
    estimate: HiddenEstimate | None
    reason: str


class TargetTracker:
    def __init__(self, max_move_per_turn: float = 1.5, max_history: int = 50,
                 area_attack_radius: float = 1.0, max_uncertainty: float = 2.5):
        self.max_move_per_turn = max_move_per_turn
        self.max_history = max_history
        self.area_attack_radius = area_attack_radius
        self.max_uncertainty = max_uncertainty
        self.targets: dict[str, TrackedTarget] = {}

    def reset(self):
        self.targets.clear()

    def observe(self, target_id: str, x: float, y: float, turn: int, confidence: float = 1.0):
        t = self.targets.setdefault(target_id, TrackedTarget(target_id))
        t.history.append(Observation(x, y, turn, confidence=confidence))
        del t.history[:-self.max_history]
        t.visibility = Visibility.VISIBLE
        t.hidden_since_turn = None

    def mark_hidden(self, target_id: str, turn: int):
        """Chamado quando o alvo deixou de ser visto (efeito de invisibilidade, saída da tela)."""
        t = self.targets.setdefault(target_id, TrackedTarget(target_id))
        if t.visibility != Visibility.HIDDEN:
            t.hidden_since_turn = turn
        t.visibility = Visibility.HIDDEN

    def _typical_move(self, t: TrackedTarget) -> float:
        """Deslocamento médio observado por turno (limitado pelo máximo configurado)."""
        moves = []
        for a, b in zip(t.history, t.history[1:]):
            dt = max(1, b.turn - a.turn)
            moves.append(abs(b.x - a.x) / dt)
        if not moves:
            return self.max_move_per_turn
        return min(self.max_move_per_turn, max(0.3, sum(moves) / len(moves) * 1.5))

    def estimate(self, target_id: str, turn: int) -> HiddenEstimate | None:
        t = self.targets.get(target_id)
        if t is None or t.last is None:
            return None
        last = t.last
        if turn < last.turn:
            return None  # contador de turno reiniciado: a posição guardada não vale
        turns = turn - last.turn
        if t.visibility == Visibility.VISIBLE and turns == 0:
            return HiddenEstimate(last.x, last.y, 0.0, 0, "observação atual")
        step = self._typical_move(t)
        # sem dados de direção, o centro fica na última posição e a incerteza é simétrica
        drift = 0.0
        if len(t.history) >= 3:
            recent = t.history[-3:]
            dx = (recent[-1].x - recent[0].x) / max(1, recent[-1].turn - recent[0].turn)
            drift = max(-step, min(step, dx)) * 0.5 * turns
        # o raio usa o deslocamento MÁXIMO por turno: parado enquanto visível não prova que
        # continuou parado depois de sumir; a média observada só ajusta o centro
        radius = self.max_move_per_turn * turns + 0.2
        return HiddenEstimate(last.x + drift, last.y, radius, turns,
                              f"última posição no turno {last.turn} + {turns} turno(s) de deslocamento possível")

    def decide(self, target_id: str, turn: int, has_area_attack: bool = False,
               min_history: int = 2) -> TargetDecision:
        t = self.targets.get(target_id)
        if t is None or t.last is None:
            return TargetDecision(Decision.ASK_USER, None, "alvo nunca foi observado")
        if t.visibility == Visibility.VISIBLE and t.last.turn == turn:
            return TargetDecision(Decision.SHOOT, self.estimate(target_id, turn), "alvo visível")
        est = self.estimate(target_id, turn)
        if est is None:
            return TargetDecision(Decision.ASK_USER, None, "contagem de turnos reiniciada; aguardando o alvo")
        if len(t.history) < min_history:
            return TargetDecision(Decision.WAIT, est, "histórico insuficiente para estimar a região")
        if est.radius <= self.area_attack_radius and has_area_attack:
            return TargetDecision(Decision.AREA_ATTACK, est,
                                  f"região provável ±{est.radius:.1f} cabe no ataque de área")
        if est.radius <= self.max_uncertainty / 2:
            return TargetDecision(Decision.SHOOT, est,
                                  f"incerteza baixa (±{est.radius:.1f}); disparo no centro estimado")
        if est.radius <= self.max_uncertainty:
            return TargetDecision(Decision.WAIT, est,
                                  f"incerteza moderada (±{est.radius:.1f}); aguardar reaparição")
        return TargetDecision(Decision.ASK_USER, est,
                              f"incerteza alta (±{est.radius:.1f}); intervenção manual recomendada")


def hit_probability_uniform(radius: float, effective_half_width: float) -> float:
    """Probabilidade de acerto se o alvo estiver uniformemente na região ±radius."""
    if radius <= 0:
        return 1.0
    return min(1.0, effective_half_width / radius) if math.isfinite(radius) else 0.0
