"""Registro de disparos e calibração a partir de resultados observados no cliente.

Cada disparo guarda ângulo, força, vento, posição do alvo e o ponto de impacto observado.
A correção é feita em duas camadas:

1. ``predict_offset``: regressão ridge (por método) do erro observado
   ``impacto_real - impacto_previsto`` em função de distância, vento e altura.
2. ``refit_params``: reajuste das constantes físicas com os disparos observados
   somados às tabelas documentadas (quando houver dados suficientes).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import numpy as np

from .physics import PhysicsParams, landing_x


@dataclass
class ShotRecord:
    angle: float
    force: float
    wind: float
    distance: float              # posição do alvo (régua)
    dy: float = 0.0
    impact_x: float | None = None  # ponto de impacto observado (régua), se medido
    hit: bool | None = None
    method: str = "manual"
    weapon: str = "padrao"
    predicted_x: float | None = None
    source: str = "observado"    # observado | simulado
    mode: str = "assistido"
    note: str = ""
    timestamp: float = field(default_factory=time.time)
    id: int | None = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS shots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL, angle REAL, force REAL, wind REAL, distance REAL, dy REAL,
    impact_x REAL, hit INTEGER, method TEXT, weapon TEXT, predicted_x REAL,
    source TEXT, mode TEXT, note TEXT
);
"""


class ShotStore:
    """Persistência SQLite (segura para várias threads)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=10)
        self._conn.execute(SCHEMA)
        self._conn.commit()

    def add(self, rec: ShotRecord) -> int:
        d = asdict(rec)
        d.pop("id")
        d["hit"] = None if rec.hit is None else int(rec.hit)
        cols = ",".join(d)
        with self._lock:
            cur = self._conn.execute(f"INSERT INTO shots ({cols}) VALUES ({','.join('?' * len(d))})",
                                     list(d.values()))
            self._conn.commit()
            return int(cur.lastrowid)

    def update_result(self, shot_id: int, impact_x: float | None, hit: bool | None, note: str = ""):
        with self._lock:
            self._conn.execute("UPDATE shots SET impact_x=?, hit=?, note=? WHERE id=?",
                               (impact_x, None if hit is None else int(hit), note, shot_id))
            self._conn.commit()

    COLS = "id,timestamp,angle,force,wind,distance,dy,impact_x,hit,method,weapon,predicted_x,source,mode,note"

    def _query(self, where: str, args: list, suffix: str = "") -> list[ShotRecord]:
        with self._lock:
            rows = self._conn.execute(f"SELECT {self.COLS} FROM shots{where}{suffix}", args).fetchall()
        return [ShotRecord(id=r[0], timestamp=r[1], angle=r[2], force=r[3], wind=r[4], distance=r[5], dy=r[6],
                           impact_x=r[7], hit=None if r[8] is None else bool(r[8]), method=r[9], weapon=r[10],
                           predicted_x=r[11], source=r[12], mode=r[13], note=r[14] or "") for r in rows]

    def all(self, source: str | None = None, limit: int | None = None) -> list[ShotRecord]:
        where, args = ("", []) if not source else (" WHERE source=?", [source])
        suffix = " ORDER BY id DESC" + (f" LIMIT {int(limit)}" if limit else "")
        return self._query(where, args, suffix)

    def get(self, shot_id: int) -> ShotRecord | None:
        rows = self._query(" WHERE id=?", [int(shot_id)])
        return rows[0] if rows else None

    def clear(self, source: str | None = None):
        with self._lock:
            if source:
                self._conn.execute("DELETE FROM shots WHERE source=?", (source,))
            else:
                self._conn.execute("DELETE FROM shots")
            self._conn.commit()

    def close(self):
        with self._lock:
            self._conn.close()


def _features(distance, wind, dy, angle):
    return np.array([1.0, distance / 10.0, wind, dy, angle / 90.0], dtype=float)


class Calibrator:
    """Mantém o modelo de correção e as estatísticas de precisão.

    O erro de cada disparo é ``impacto_real - previsto``, calculado com a arma e o ângulo
    efetivos daquele disparo. Há um modelo por (arma, método) e, para métodos com poucos
    disparos, um modelo geral da arma que só corrige o viés (sem inclinação), para não
    aplicar a tendência de uma trajetória (ex.: tiro alto) a outra (ex.: 20°).
    """

    MIN_SHOTS_OFFSET = 3
    MIN_SHOTS_REFIT = 15
    RIDGE = 2.0

    def __init__(self, store: ShotStore, params: PhysicsParams, sources=("observado",), weapon_lookup=None):
        self.store = store
        self.params = params
        self.sources = sources
        self.weapon_lookup = weapon_lookup  # nome -> Weapon (force_scale, drag_scale, angle_offset)
        self._models: dict[str, tuple] = {}
        self._lock = threading.Lock()
        self.rebuild()

    # ------------------------------------------------------------------ util
    def _effective(self, weapon_name: str, params: PhysicsParams | None = None):
        p = params or self.params
        w = self.weapon_lookup(weapon_name) if self.weapon_lookup else None
        if w is None:
            return p, 0.0
        return replace(p, speed_k=p.speed_k * w.force_scale, drag=p.drag * w.drag_scale), float(w.angle_offset)

    def predict_x(self, rec: "ShotRecord", params: PhysicsParams | None = None) -> float:
        p, off = self._effective(rec.weapon, params)
        return float(landing_x(rec.angle + off, rec.force, rec.wind, rec.dy, p))

    def _usable(self) -> list[ShotRecord]:
        recs = []
        for s in self.sources:
            recs += [r for r in self.store.all(source=s) if r.impact_x is not None]
        return recs

    @staticmethod
    def _fit(X, y, bias_only=False):
        R = Calibrator.RIDGE * np.eye(X.shape[1])
        R[0, 0] = Calibrator.RIDGE * 0.25  # o viés constante é o que mais aprende
        if bias_only:
            X = X[:, :1]
            R = R[:1, :1]
        A = X.T @ X + R
        coef = np.linalg.solve(A, X.T @ y)
        resid = y - X @ coef
        dof = max(1, len(y) - X.shape[1])
        s2 = float(np.sum(resid ** 2) / dof)
        return coef, s2, np.linalg.inv(A), bias_only

    def rebuild(self):
        recs = self._usable()
        groups: dict[str, list[ShotRecord]] = {}
        for r in recs:
            groups.setdefault(f"{r.weapon}|*", []).append(r)
            groups.setdefault(f"{r.weapon}|{r.method}", []).append(r)
        models = {}
        for key, rows in groups.items():
            if len(rows) < self.MIN_SHOTS_OFFSET:
                continue
            X = np.array([_features(r.distance, r.wind, r.dy, r.angle) for r in rows])
            y = np.array([r.impact_x - self.predict_x(r) for r in rows])
            ok = np.isfinite(y)
            X, y = X[ok], y[ok]
            if len(y) < self.MIN_SHOTS_OFFSET:
                continue
            coef, s2, cov, bias_only = self._fit(X, y, bias_only=key.endswith("|*") or len(y) < 8)
            models[key] = (coef, s2, cov, bias_only, len(y))
        with self._lock:
            self._models = models

    def predict_offset(self, method, angle, force, wind, dy, distance, weapon="padrao"):
        """Retorna (erro_previsto, sigma_extra, n_disparos)."""
        with self._lock:
            model = self._models.get(f"{weapon}|{method}") or self._models.get(f"{weapon}|*")
        if model is None:
            return 0.0, 0.0, 0
        coef, s2, cov, bias_only, n = model
        x = _features(distance, wind, dy, angle)
        if bias_only:
            x = x[:1]
        offset = float(x @ coef)
        # incerteza preditiva: ruído por disparo + incerteza dos coeficientes (não some com n grande)
        sigma = float(np.sqrt(max(0.0, s2) * (1.0 + float(x @ cov @ x))))
        return offset, min(sigma, 1.5), n

    def record(self, rec: ShotRecord) -> int:
        if rec.predicted_x is None:
            rec.predicted_x = self.predict_x(rec)
        shot_id = self.store.add(rec)
        if rec.impact_x is not None:
            self.rebuild()
        return shot_id

    def set_result(self, shot_id: int, impact_x: float | None, hit: bool | None, note: str = ""):
        self.store.update_result(shot_id, impact_x, hit, note)
        self.rebuild()

    def stats(self) -> dict:
        recs = []
        for s in self.sources:
            recs += self.store.all(source=s)
        judged = [r for r in recs if r.hit is not None]
        measured = [r for r in recs if r.impact_x is not None]
        to_target = np.array([r.impact_x - r.distance for r in measured]) if measured else np.array([])
        to_pred = np.array([r.impact_x - r.predicted_x for r in measured if r.predicted_x is not None])
        with self._lock:
            models = {k: {"n": v[4], "sigma": round(float(np.sqrt(v[1])), 3)} for k, v in self._models.items()}
        return {
            "disparos": len(recs),
            "avaliados": len(judged),
            "acertos": sum(1 for r in judged if r.hit),
            "taxa_acerto": (sum(1 for r in judged if r.hit) / len(judged)) if judged else None,
            "erro_medio": float(np.mean(to_target)) if len(to_target) else None,       # impacto - alvo
            "erro_abs_medio": float(np.mean(np.abs(to_target))) if len(to_target) else None,
            "erro_previsao_abs_medio": float(np.mean(np.abs(to_pred))) if len(to_pred) else None,
            "modelos": models,
        }

    # limites físicos dos parâmetros reajustados (speed_k, drag, wind_k, launch_h)
    BOUNDS = ((1e-3, 1.0), (0.0, 1.0), (0.0, 0.5), (0.0, 1.5))

    def refit_params(self, table_rows=None, max_iter=400) -> tuple[PhysicsParams, dict] | None:
        """Reajusta as constantes físicas com os impactos observados.

        ``table_rows`` (ângulo, distância, força) das tabelas documentadas entram com peso
        pequeno para o modelo não "esquecer" o que já se sabia com poucos disparos.
        """
        from .optim import nelder_mead
        from .physics import solve_force

        recs = [r for r in self._usable() if r.weapon == "padrao" or self.weapon_lookup]
        if len(recs) < self.MIN_SHOTS_REFIT:
            return None
        base = self.params
        x = np.array([r.impact_x for r in recs])
        rows = list(table_rows or [])

        def loss(vec):
            for v, (lo, hi) in zip(vec, self.BOUNDS):
                if not lo <= v <= hi:
                    return 1e9
            p = base.with_vector(vec)
            pred = np.array([self.predict_x(r, p) for r in recs])
            err = pred - x
            err = np.where(np.isfinite(err), err, 5.0)  # tiro que "não chega" conta como erro grande
            # regularização em escala absoluta (parâmetros pequenos não ficam congelados)
            scale = np.array([0.02, 0.02, 0.01, 0.1])
            prior = np.sum(((vec - base.to_vector()) / scale) ** 2)
            total = float(np.mean(err ** 2) + 0.01 * prior)
            if rows:
                a = np.array([r[0] for r in rows]); d = np.array([r[1] for r in rows]); f = np.array([r[2] for r in rows])
                fe = np.nan_to_num(solve_force(a, d, 0.0, 0.0, p, f_max=130.0) - f, nan=20.0)
                total += 0.002 * float(np.mean(fe ** 2))
            return total

        before = loss(base.to_vector())
        vec, after = nelder_mead(loss, base.to_vector(), max_iter=max_iter)
        new = base.with_vector(vec)
        return new, {"perda_antes": before, "perda_depois": after, "n": len(recs)}

    def export_json(self, path: Path):
        rows = [asdict(r) for r in self.store.all()]
        Path(path).write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
