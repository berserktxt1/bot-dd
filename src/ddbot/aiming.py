"""Motor de mira: gera candidatos (tabelas, fórmulas, busca física) e escolhe o de
maior probabilidade estimada de acerto."""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

from .knowledge import KnowledgeBase
from .physics import PhysicsParams, landing_x, solve_force, trajectory


@dataclass
class Weapon:
    name: str = "padrao"
    force_scale: float = 1.0     # multiplica a velocidade inicial
    drag_scale: float = 1.0      # multiplica o arrasto
    angle_offset: float = 0.0    # graus somados ao ângulo executado
    blast_radius: float = 0.25   # raio de dano em unidades de régua


@dataclass
class ShotContext:
    distance: float              # distância horizontal até o alvo (régua, >= 0)
    dy: float = 0.0              # altura do alvo em relação ao atirador (+ = mais alto)
    wind: float = 0.0            # vento relativo ao disparo (+ = a favor)
    target_width: float = 0.35   # largura aparente do alvo em unidades de régua
    terrain: np.ndarray | None = None  # perfil (N,2) x,y do terreno no sentido do disparo
    weapon: Weapon = field(default_factory=Weapon)
    sigma_distance: float = 0.10  # incerteza da medição da distância
    sigma_dy: float = 0.10
    sigma_wind: float = 0.10
    angle_min: int = 0
    angle_max: int = 90
    allowed_methods: tuple[str, ...] | None = None


@dataclass
class Candidate:
    method: str
    angle: int
    force: float
    predicted_x: float
    corrected_target: float
    sigma_x: float
    hit_probability: float
    basis: list[str]
    blocked: bool = False

    def as_dict(self):
        return {"metodo": self.method, "angulo": self.angle, "forca": round(self.force, 1),
                "prob_acerto": round(self.hit_probability, 3), "sigma": round(self.sigma_x, 3),
                "base": self.basis, "bloqueado": self.blocked}


@dataclass
class Recommendation:
    best: Candidate | None
    candidates: list[Candidate]
    context: ShotContext
    reason: str = ""

    @property
    def confidence(self) -> float:
        return self.best.hit_probability if self.best else 0.0


def _phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


class Aimer:
    FORCE_EXEC_SIGMA = 0.6   # erro típico ao soltar a barra de força

    def __init__(self, kb: KnowledgeBase, params: PhysicsParams, calibrator=None,
                 model_sigma_force: float = 1.0):
        self.kb = kb
        self.params = params
        self.calibrator = calibrator
        self.model_sigma_force = model_sigma_force

    # ------------------------------------------------------------------ helpers
    def weapon_params(self, weapon: Weapon) -> PhysicsParams:
        return replace(self.params, speed_k=self.params.speed_k * weapon.force_scale,
                       drag=self.params.drag * weapon.drag_scale)

    def _correction(self, method, angle, force, ctx):
        if self.calibrator is None:
            return 0.0, 0.0, 0
        return self.calibrator.predict_offset(method, angle, force, ctx.wind, ctx.dy, ctx.distance)

    def _sigma(self, angle, force, ctx, p, extra_sigma):
        """Propaga incertezas (força, vento, medição, modelo) para o ponto de impacto."""
        a, f, w, dy = float(angle), float(force), ctx.wind, ctx.dy
        x0 = float(landing_x(a, f, w, dy, p))
        h = 0.5
        dxdf = (float(landing_x(a, f + h, w, dy, p)) - x0) / h
        dxdw = (float(landing_x(a, f, w + 0.2, dy, p)) - x0) / 0.2
        dxdy = (float(landing_x(a, f, w, dy + 0.2, p)) - x0) / 0.2
        if not all(np.isfinite([dxdf, dxdw, dxdy])):
            return float("inf")
        var = ((dxdf * self.FORCE_EXEC_SIGMA) ** 2 + (dxdf * self.model_sigma_force) ** 2
               + (dxdw * ctx.sigma_wind) ** 2 + (dxdy * ctx.sigma_dy) ** 2
               + ctx.sigma_distance ** 2 + extra_sigma ** 2)
        return math.sqrt(var)

    def _blocked(self, angle, force, ctx, p, x_end):
        if ctx.terrain is None or len(ctx.terrain) < 2:
            return False
        pts = trajectory(angle, force, ctx.wind, p, n=300)
        tx, ty = ctx.terrain[:, 0], ctx.terrain[:, 1]
        margin = ctx.target_width / 2 + 0.1
        sel = (pts[:, 0] > 0.3) & (pts[:, 0] < x_end - margin)
        if not sel.any():
            return False
        ground = np.interp(pts[sel, 0], tx, ty, left=-np.inf, right=-np.inf)
        return bool(np.any(pts[sel, 1] < ground))

    def _evaluate(self, method, angle, force, ctx, p, basis, documented=False):
        angle_exec = int(round(angle))
        if not (ctx.angle_min <= angle_exec <= ctx.angle_max) or not (0 < force <= 100):
            return None
        offset, extra_sigma, n_obs = self._correction(method, angle_exec, force, ctx)
        corrected_target = ctx.distance - offset
        # reajusta a força para o ângulo inteiro e para o alvo corrigido
        model_force = float(solve_force(angle_exec + ctx.weapon.angle_offset, corrected_target,
                                        ctx.wind, ctx.dy, p))
        if documented and np.isfinite(model_force):
            # mantém a força documentada e aplica só o delta do modelo para
            # arredondamento do ângulo, altura e correção de calibração
            nominal = float(solve_force(angle + ctx.weapon.angle_offset, ctx.distance,
                                        ctx.wind, 0.0, p))
            if np.isfinite(nominal):
                force = force + (model_force - nominal)
        elif np.isfinite(model_force):
            force = model_force
        if not np.isfinite(force) or not (0 < force <= 100):
            return None
        force = round(force, 1)
        pred = float(landing_x(angle_exec + ctx.weapon.angle_offset, force, ctx.wind, ctx.dy, p)) + offset
        if not np.isfinite(pred):
            return None
        sigma = self._sigma(angle_exec + ctx.weapon.angle_offset, force, ctx, p, extra_sigma)
        half = ctx.target_width / 2 + ctx.weapon.blast_radius
        bias = pred - ctx.distance
        prob = _phi((half - bias) / sigma) - _phi((-half - bias) / sigma) if np.isfinite(sigma) else 0.0
        blocked = self._blocked(angle_exec + ctx.weapon.angle_offset, force, ctx, p, pred - offset)
        if blocked:
            prob = 0.0
        basis = list(basis)
        if n_obs:
            basis.append(f"correção por {n_obs} disparos observados")
        return Candidate(method, angle_exec, force, pred, corrected_target, sigma, prob, basis, blocked)

    # --------------------------------------------------------------- interface
    def candidates(self, ctx: ShotContext) -> list[Candidate]:
        p = self.weapon_params(ctx.weapon)
        out: list[Candidate] = []
        allowed = ctx.allowed_methods

        def ok(key):
            return allowed is None or key in allowed

        for key, m in self.kb.table_methods.items():
            if not ok(key):
                continue
            if m.forces:
                f = m.force_for(ctx.distance)
                if f is None:
                    continue
                c = self._evaluate(key, m.angle_for(ctx.wind), f, ctx, p,
                                   [f"tabela documentada ({m.source})", "modelo ajustado às tabelas"],
                                   documented=True)
            else:
                angle = m.base_angle
                f = float(solve_force(angle, ctx.distance, ctx.wind, ctx.dy, p))
                if not np.isfinite(f):
                    continue
                c = self._evaluate(key, angle, f, ctx, p, ["estimativa do modelo (sem tabela pública)"])
            if c:
                out.append(c)
        for key, m in self.kb.formula_methods.items():
            if not ok(key):
                continue
            angle = m.angle_for(ctx.distance, ctx.wind)
            if angle is None:
                continue
            c = self._evaluate(key, angle, m.fixed_force, ctx, p, [f"fórmula documentada ({m.source})"],
                               documented=True)
            if c:
                out.append(c)
        if ok("fisica"):
            angles = np.arange(max(ctx.angle_min, 10), min(ctx.angle_max, 89) + 1, dtype=float)
            forces = solve_force(angles + ctx.weapon.angle_offset, ctx.distance, ctx.wind, ctx.dy, p)
            # avalia só alguns ângulos promissores para manter rápido
            valid = [(a, f) for a, f in zip(angles, forces) if np.isfinite(f) and 0 < f <= 100]
            for a, f in valid[:: max(1, len(valid) // 16)]:
                c = self._evaluate("fisica", a, f, ctx, p, ["busca no modelo físico"])
                if c:
                    out.append(c)
        out.sort(key=lambda c: c.hit_probability, reverse=True)
        return out

    def recommend(self, ctx: ShotContext) -> Recommendation:
        if ctx.distance <= 0:
            return Recommendation(None, [], ctx, "distância inválida")
        cands = self.candidates(ctx)
        if not cands:
            return Recommendation(None, [], ctx, "nenhuma combinação alcança o alvo")
        best = cands[0]
        reason = f"{best.method}: {best.angle}° / {best.force:.1f} (P≈{best.hit_probability:.0%})"
        if best.hit_probability <= 0:
            reason = "todas as trajetórias parecem bloqueadas ou incertas"
        return Recommendation(best, cands, ctx, reason)
