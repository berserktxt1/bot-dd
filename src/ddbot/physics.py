"""Modelo físico do projétil.

Estrutura baseada no modelo público "caderno-de-tiro" (gravidade + arrasto linear +
vento como aceleração horizontal constante). As constantes são ajustadas às tabelas
públicas por ``tools/fit_model.py`` e depois refinadas com disparos observados
(ver ``calibration.py``).

Convenções (coordenadas do modelo):
- O atirador está em x=0 e sempre atira para +x.
- Distâncias em "unidades de régua" (largura visível da tela / 10).
- ``dy`` é a altura do alvo em relação ao atirador (positivo = alvo mais alto).
- ``wind`` é o vento relativo ao disparo (positivo = a favor).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import numpy as np


@dataclass
class PhysicsParams:
    speed_k: float = 0.2      # velocidade inicial = speed_k * força
    gravity: float = 1.0      # aceleração vertical (fixa como escala de tempo)
    drag: float = 0.05        # arrasto linear (1/tempo)
    wind_k: float = 0.02      # aceleração horizontal por unidade de vento
    launch_h: float = 0.0     # altura do ponto de disparo acima dos pés

    FITTED = ("speed_k", "drag", "wind_k", "launch_h")

    def to_vector(self) -> np.ndarray:
        return np.array([getattr(self, n) for n in self.FITTED], dtype=float)

    def with_vector(self, vec) -> "PhysicsParams":
        data = asdict(self)
        for name, value in zip(self.FITTED, vec):
            data[name] = float(value)
        return PhysicsParams(**data)

    @classmethod
    def load(cls, path: Path) -> "PhysicsParams":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        names = {f.name for f in fields(cls)}
        return cls(**{k: float(v) for k, v in data.get("params", data).items() if k in names})

    def save(self, path: Path, extra: dict | None = None) -> None:
        payload = {"params": asdict(self)}
        if extra:
            payload.update(extra)
        Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _state(t, vx0, vy0, a, p: PhysicsParams):
    """Posição (x, y) no tempo t com solução analítica do arrasto linear."""
    b, g = p.drag, p.gravity
    if b < 1e-9:
        x = vx0 * t + 0.5 * a * t * t
        y = p.launch_h + vy0 * t - 0.5 * g * t * t
        return x, y
    e = -np.expm1(-b * t) / b  # (1 - e^{-bt}) / b
    x = (a / b) * t + (vx0 - a / b) * e
    y = p.launch_h - (g / b) * t + (vy0 + g / b) * e
    return x, y


def _velocities(angle_deg, force, p: PhysicsParams):
    rad = np.radians(np.asarray(angle_deg, dtype=float))
    v = p.speed_k * np.asarray(force, dtype=float)
    return v * np.cos(rad), v * np.sin(rad)


def impact_time(angle_deg, force, wind, dy, p: PhysicsParams):
    """Tempo em que o projétil cruza a altura ``dy`` descendo (NaN se nunca alcança)."""
    angle_deg, force, wind, dy = np.broadcast_arrays(
        np.asarray(angle_deg, float), np.asarray(force, float),
        np.asarray(wind, float), np.asarray(dy, float))
    vx0, vy0 = _velocities(angle_deg, force, p)
    a = p.wind_k * wind
    b, g = p.drag, p.gravity
    vy_pos = np.maximum(vy0, 0.0)
    if b < 1e-9:
        t_apex = vy_pos / g
    else:
        t_apex = np.log1p(b * vy_pos / g) / b
    _, y_apex = _state(t_apex, vx0, vy0, a, p)
    reachable = y_apex >= dy

    lo = t_apex.copy()
    hi = t_apex + 1.0
    for _ in range(60):  # expande até ficar abaixo de dy
        _, yh = _state(hi, vx0, vy0, a, p)
        need = reachable & (yh > dy)
        if not need.any():
            break
        hi = np.where(need, hi * 2.0 + 1.0, hi)
    for _ in range(60):  # bisseção
        mid = 0.5 * (lo + hi)
        _, ym = _state(mid, vx0, vy0, a, p)
        above = ym > dy
        lo = np.where(above, mid, lo)
        hi = np.where(above, hi, mid)
    t = 0.5 * (lo + hi)
    return np.where(reachable, t, np.nan)


def landing_x(angle_deg, force, wind, dy, p: PhysicsParams):
    """Posição horizontal em que o projétil atinge a altura ``dy`` (descendo)."""
    t = impact_time(angle_deg, force, wind, dy, p)
    vx0, vy0 = _velocities(angle_deg, force, p)
    a = p.wind_k * np.asarray(wind, float)
    x, _ = _state(np.nan_to_num(t), vx0, vy0, a, p)
    return np.where(np.isnan(t), np.nan, x)


def trajectory(angle_deg, force, wind, p: PhysicsParams, t_max=None, n=200):
    """Pontos (x, y) da trajetória até cair 30 unidades abaixo do disparo."""
    if t_max is None:
        t_end = impact_time(angle_deg, force, wind, -30.0, p)
        t_max = float(t_end) if np.isfinite(t_end) else 50.0
    t = np.linspace(0.0, t_max, n)
    vx0, vy0 = _velocities(angle_deg, force, p)
    x, y = _state(t, vx0, vy0, p.wind_k * wind, p)
    return np.stack([x, y], axis=1)


def solve_force(angle_deg, distance, wind, dy, p: PhysicsParams, f_min=0.0, f_max=100.0):
    """Força que faz o projétil cair em ``distance`` (NaN se impossível). Vetorizado."""
    angle_deg, distance, wind, dy = np.broadcast_arrays(
        np.asarray(angle_deg, float), np.asarray(distance, float),
        np.asarray(wind, float), np.asarray(dy, float))
    lo = np.full(angle_deg.shape, f_min)
    hi = np.full(angle_deg.shape, f_max)
    x_hi = np.nan_to_num(landing_x(angle_deg, hi, wind, dy, p), nan=-np.inf)
    ok = x_hi >= distance
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        xm = np.nan_to_num(landing_x(angle_deg, mid, wind, dy, p), nan=-np.inf)
        short = xm < distance
        lo = np.where(short, mid, lo)
        hi = np.where(short, hi, mid)
    return np.where(ok, 0.5 * (lo + hi), np.nan)
