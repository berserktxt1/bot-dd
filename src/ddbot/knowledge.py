"""Base de conhecimento local: tabelas documentadas, fórmulas de vento e fontes.

Os dados vivem em ``data/knowledge/*.json`` e podem ser editados sem mexer no código.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class TableMethod:
    key: str
    name: str
    base_angle: float
    wind_angle_factor: float
    forces: list[float] | None  # índice 0 = distância 1
    source: str

    def force_for(self, distance: float) -> float | None:
        """Interpolação linear na tabela (distâncias 1..N)."""
        if not self.forces:
            return None
        d = np.arange(1, len(self.forces) + 1, dtype=float)
        if distance < 0.5 or distance > d[-1] + 0.5:
            return None
        if distance < 1:  # extrapola até d=0 com força 0 proporcional
            return float(self.forces[0] * distance)
        if distance > d[-1]:  # até meia unidade além da tabela, pela inclinação do fim
            slope = self.forces[-1] - self.forces[-2]
            return float(self.forces[-1] + slope * (distance - d[-1]))
        return float(np.interp(distance, d, self.forces))

    def angle_for(self, wind: float) -> float:
        return self.base_angle + self.wind_angle_factor * wind


@dataclass
class FormulaMethod:
    key: str
    name: str
    fixed_force: float
    distance_factor: float  # ângulo = 90 - distance_factor * d + 2 * vento
    wind_angle_factor: float
    valid_distance: tuple[float, float]
    source: str

    def angle_for(self, distance: float, wind: float) -> float | None:
        if not (self.valid_distance[0] <= distance <= self.valid_distance[1]):
            return None
        return 90.0 - self.distance_factor * distance + self.wind_angle_factor * wind


class KnowledgeBase:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        kdir = self.data_dir / "knowledge"
        self.tables_raw = json.loads((kdir / "angle_tables.json").read_text(encoding="utf-8-sig"))
        self.sources = json.loads((kdir / "sources.json").read_text(encoding="utf-8-sig"))["sources"]
        self.mechanics = json.loads((kdir / "mechanics.json").read_text(encoding="utf-8-sig"))["mechanics"]
        self.table_methods: dict[str, TableMethod] = {}
        self.formula_methods: dict[str, FormulaMethod] = {}
        for key, m in self.tables_raw["methods"].items():
            if "base_angle" in m:
                self.table_methods[key] = TableMethod(
                    key, m["nome"], float(m["base_angle"]), float(m["wind_angle_factor"]),
                    m.get("force_by_distance"), m.get("source", ""))
            elif "fixed_force" in m:
                factor = 2.0 if "2*d" in m["angle_formula"].replace(" ", "") else 1.0
                vd = m.get("valid_distance", [1, 20])
                self.formula_methods[key] = FormulaMethod(
                    key, m["nome"], float(m["fixed_force"]), factor, 2.0,
                    (float(vd[0]), float(vd[1])), m.get("source", ""))

    def documented_cells(self):
        """Células (ângulo, distância, força) das tabelas com vento 0 e mesma altura."""
        cells = []
        for m in self.table_methods.values():
            if m.forces:
                for i, f in enumerate(m.forces):
                    cells.append((m.base_angle, float(i + 1), float(f), m.key))
        return cells

    def source(self, source_id: str) -> dict | None:
        return next((s for s in self.sources if s["id"] == source_id), None)
