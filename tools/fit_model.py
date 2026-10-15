"""Ajusta as constantes do modelo físico às tabelas documentadas.

Uso: python tools/fit_model.py  -> grava data/knowledge/model_params.json
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ddbot.knowledge import KnowledgeBase  # noqa: E402
from ddbot.optim import nelder_mead  # noqa: E402
from ddbot.physics import PhysicsParams, solve_force  # noqa: E402


def build_targets(kb: KnowledgeBase):
    """Linhas (ângulo, distância, vento, força_esperada, peso, grupo)."""
    rows = []
    for angle, d, f, key in kb.documented_cells():
        rows.append((angle, d, 0.0, f, 1.0, key))
    # regras de vento: ângulo ajustado + força da tabela deve acertar a mesma distância
    for key in ("a50", "a65", "a30"):
        m = kb.table_methods[key]
        for d in (5.0, 10.0, 15.0):
            for w in (-2.0, -1.0, 1.0, 2.0):
                rows.append((m.angle_for(w), d, w, m.force_for(d), 0.5, f"{key}_vento"))
    hs = kb.formula_methods["high"]
    for d in range(2, 21, 2):
        rows.append((hs.angle_for(d, 0.0), float(d), 0.0, hs.fixed_force, 0.5, "alto"))
    md = kb.formula_methods["medium"]
    for d in range(2, 13, 2):
        rows.append((md.angle_for(d, 0.0), float(d), 0.0, md.fixed_force, 0.3, "medio"))
    return rows


def residuals(params: PhysicsParams, rows):
    a = np.array([r[0] for r in rows]); d = np.array([r[1] for r in rows])
    w = np.array([r[2] for r in rows]); f = np.array([r[3] for r in rows])
    pred = solve_force(a, d, w, 0.0, params, f_max=130.0)
    return np.nan_to_num(pred - f, nan=50.0)


def fit(kb: KnowledgeBase, start: PhysicsParams | None = None):
    rows = build_targets(kb)
    weights = np.array([r[4] for r in rows])
    base = start or PhysicsParams()

    def loss(vec):
        if vec[0] <= 0 or vec[1] < 0 or vec[3] < 0 or vec[3] > 2:
            return 1e9
        r = residuals(base.with_vector(vec), rows)
        return float(np.sum(weights * r * r) / weights.sum())

    best_vec, best = None, np.inf
    for sk in (0.1, 0.2, 0.4):
        for dr in (0.01, 0.1, 0.3):
            vec, val = nelder_mead(loss, [sk, dr, 0.02, 0.2], max_iter=600)
            if val < best:
                best_vec, best = vec, val
    best_vec, best = nelder_mead(loss, best_vec, max_iter=3000, tol=1e-12)
    params = base.with_vector(best_vec)
    res = residuals(params, rows)
    groups = {}
    for r, row in zip(res, rows):
        groups.setdefault(row[5], []).append(r)
    stats = {g: {"rmse_forca": float(np.sqrt(np.mean(np.square(v)))),
                 "max_abs": float(np.max(np.abs(v))), "n": len(v)} for g, v in groups.items()}
    table_res = np.concatenate([groups[k] for k in ("a30", "a50", "a65")])
    stats["tabelas_total"] = {"rmse_forca": float(np.sqrt(np.mean(table_res ** 2))),
                              "dentro_2": int(np.sum(np.abs(table_res) <= 2)), "n": len(table_res)}
    return params, stats


def main():
    kb = KnowledgeBase(ROOT / "data")
    params, stats = fit(kb)
    out = ROOT / "data" / "knowledge" / "model_params.json"
    params.save(out, {"origem": "ajuste às tabelas documentadas (tools/fit_model.py)",
                      "tipo": "documentado", "estatisticas": stats})
    print(params)
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
