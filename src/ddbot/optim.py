"""Otimizador Nelder-Mead mínimo (evita depender do SciPy no executável)."""
from __future__ import annotations

import numpy as np


def nelder_mead(func, x0, step=None, max_iter=2000, tol=1e-9):
    x0 = np.asarray(x0, dtype=float)
    n = len(x0)
    step = np.asarray(step if step is not None else np.maximum(np.abs(x0) * 0.1, 1e-3), dtype=float)
    simplex = [x0] + [x0 + np.eye(n)[i] * step[i] for i in range(n)]
    values = [func(s) for s in simplex]
    for _ in range(max_iter):
        order = np.argsort(values)
        simplex = [simplex[i] for i in order]
        values = [values[i] for i in order]
        if abs(values[-1] - values[0]) < tol:
            break
        centroid = np.mean(simplex[:-1], axis=0)
        worst = simplex[-1]
        xr = centroid + (centroid - worst)
        fr = func(xr)
        if fr < values[0]:
            xe = centroid + 2.0 * (centroid - worst)
            fe = func(xe)
            simplex[-1], values[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < values[-2]:
            simplex[-1], values[-1] = xr, fr
        else:
            xc = centroid + 0.5 * (worst - centroid)
            fc = func(xc)
            if fc < values[-1]:
                simplex[-1], values[-1] = xc, fc
            else:
                best = simplex[0]
                simplex = [best] + [best + 0.5 * (s - best) for s in simplex[1:]]
                values = [values[0]] + [func(s) for s in simplex[1:]]
    i = int(np.argmin(values))
    return simplex[i], float(values[i])
