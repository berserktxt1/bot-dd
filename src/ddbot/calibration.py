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
from dataclasses import asdict, dataclass, field
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
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
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

    def all(self, source: str | None = None, limit: int | None = None) -> list[ShotRecord]:
        q = "SELECT id,timestamp,angle,force,wind,distance,dy,impact_x,hit,method,weapon,predicted_x,source,mode,note FROM shots"
        args: list = []
        if source:
            q += " WHERE source=?"
            args.append(source)
        q += " ORDER BY id DESC"
        if limit:
            q += f" LIMIT {int(limit)}"
        with self._lock:
            rows = self._conn.execute(q, args).fetchall()
        out = []
        for r in rows:
            out.append(ShotRecord(id=r[0], timestamp=r[1], angle=r[2], force=r[3], wind=r[4],
                                  distance=r[5], dy=r[6], impact_x=r[7],
                                  hit=None if r[8] is None else bool(r[8]), method=r[9], weapon=r[10],
                                  predicted_x=r[11], source=r[12], mode=r[13], note=r[14] or ""))
        return out

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


def _features(distance, wind, dy):
    return np.array([1.0, distance / 10.0, wind, dy], dtype=float)


class Calibrator:
    """Mantém o modelo de correção e as estatísticas de precisão."""

    MIN_SHOTS_OFFSET = 3
    MIN_SHOTS_REFIT = 15
    RIDGE = 2.0

    def __init__(self, store: ShotStore, params: PhysicsParams, sources=("observado",)):
        self.store = store
        self.params = params
        self.sources = sources
        self._models: dict[str, tuple[np.ndarray, float, int]] = {}
        self._lock = threading.Lock()
        self.rebuild()

    def _usable(self) -> list[ShotRecord]:
        recs = []
        for s in self.sources:
            recs += [r for r in self.store.all(source=s) if r.impact_x is not None]
        return recs

    def rebuild(self):
        recs = self._usable()
        groups: dict[str, list[ShotRecord]] = {"*": recs}
        for r in recs:
            groups.setdefault(r.method, []).append(r)
        models = {}
        for key, rows in groups.items():
            if len(rows) < self.MIN_SHOTS_OFFSET:
                continue
            X = np.array([_features(r.distance, r.wind, r.dy) for r in rows])
            pred = landing_x([r.angle for r in rows], [r.force for r in rows],
                             [r.wind for r in rows], [r.dy for r in rows], self.params)
            y = np.array([r.impact_x for r in rows]) - pred
            ok = np.isfinite(y)
            X, y = X[ok], y[ok]
            if len(y) < self.MIN_SHOTS_OFFSET:
                continue
            reg = self.RIDGE * np.eye(X.shape[1])
            reg[0, 0] = self.RIDGE * 0.25  # o viés constante é o que mais aprende
            coef = np.linalg.solve(X.T @ X + reg, X.T @ y)
            resid = y - X @ coef
            dof = max(1, len(y) - 1)
            sigma = float(np.sqrt(np.sum(resid ** 2) / dof))
            models[key] = (coef, sigma, len(y))
        with self._lock:
            self._models = models

    def predict_offset(self, method, angle, force, wind, dy, distance):
        """Retorna (erro_previsto, sigma_extra, n_disparos)."""
        with self._lock:
            model = self._models.get(method) or self._models.get("*")
        if model is None:
            return 0.0, 0.0, 0
        coef, sigma, n = model
        offset = float(_features(distance, wind, dy) @ coef)
        # incerteza decresce com mais dados; limitada para não paralisar a mira
        return offset, min(sigma, 1.0) / max(1.0, np.sqrt(n / 5)), n

    def record(self, rec: ShotRecord) -> int:
        if rec.predicted_x is None:
            rec.predicted_x = float(landing_x(rec.angle, rec.force, rec.wind, rec.dy, self.params))
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
        measured = [r for r in recs if r.impact_x is not None and r.predicted_x is not None]
        errs = np.array([r.impact_x - r.distance for r in measured]) if measured else np.array([])
        return {
            "disparos": len(recs),
            "avaliados": len(judged),
            "acertos": sum(1 for r in judged if r.hit),
            "taxa_acerto": (sum(1 for r in judged if r.hit) / len(judged)) if judged else None,
            "erro_medio": float(np.mean(errs)) if len(errs) else None,
            "erro_abs_medio": float(np.mean(np.abs(errs))) if len(errs) else None,
            "modelos": {k: {"n": v[2], "sigma": round(v[1], 3)} for k, v in self._models.items()},
        }

    def refit_params(self, table_rows=None, max_iter=400) -> tuple[PhysicsParams, dict] | None:
        """Reajusta as constantes físicas com os impactos observados."""
        from .optim import nelder_mead

        recs = self._usable()
        if len(recs) < self.MIN_SHOTS_REFIT:
            return None
        a = np.array([r.angle for r in recs]); f = np.array([r.force for r in recs])
        w = np.array([r.wind for r in recs]); dy = np.array([r.dy for r in recs])
        x = np.array([r.impact_x for r in recs])
        base = self.params

        def loss(vec):
            if vec[0] <= 0 or vec[1] < 0:
                return 1e9
            p = base.with_vector(vec)
            pred = landing_x(a, f, w, dy, p)
            err = np.nan_to_num(pred - x, nan=20.0)
            # regularização: não se afastar demais do modelo documentado
            prior = np.sum(((vec - base.to_vector()) / (np.abs(base.to_vector()) + 1e-3)) ** 2)
            return float(np.mean(err ** 2) + 0.05 * prior)

        before = loss(base.to_vector())
        vec, after = nelder_mead(loss, base.to_vector(), max_iter=max_iter)
        new = base.with_vector(vec)
        return new, {"perda_antes": before, "perda_depois": after, "n": len(recs)}

    def export_json(self, path: Path):
        rows = [asdict(r) for r in self.store.all()]
        Path(path).write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
