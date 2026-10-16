import numpy as np
import pytest

from ddbot.aiming import Aimer, ShotContext, Weapon
from ddbot.physics import solve_force


def test_tables_loaded(kb):
    assert set(kb.table_methods) >= {"a20", "a30", "a50", "a65"}
    assert kb.table_methods["a20"].forces[0] == 10
    assert kb.table_methods["a65"].force_for(10) == 56.0
    assert kb.table_methods["a65"].force_for(10.5) == pytest.approx(57.0)
    assert kb.table_methods["a30"].force_for(25) is None
    for m in kb.table_methods.values():
        assert m.source and all(kb.source(s) for s in m.source.split(";"))


def test_wind_rules(kb):
    assert kb.table_methods["a65"].angle_for(1.5) == 68.0
    assert kb.table_methods["a50"].angle_for(-2.5) == 45.0
    assert kb.table_methods["a30"].angle_for(2) == 32.0
    assert kb.table_methods["a20"].angle_for(3) == 20.0
    high = kb.formula_methods["high"]
    assert high.fixed_force == 95
    assert high.angle_for(10, -1.5) == 77.0  # exemplo da ddladora
    assert kb.formula_methods["medium"].angle_for(5, 1) == 82.0


def test_model_fits_documented_tables(kb, params):
    errs = [float(solve_force(a, d, 0, 0, params)) - f for a, d, f, _ in kb.documented_cells()]
    assert np.sqrt(np.mean(np.square(errs))) < 1.3
    assert np.max(np.abs(errs)) < 3.0


def test_recommend_documented_cell(kb, params):
    aimer = Aimer(kb, params)
    rec = aimer.recommend(ShotContext(distance=10, wind=0))
    assert rec.best is not None and rec.best.hit_probability > 0.3
    a65 = next(c for c in rec.candidates if c.method == "a65")
    assert a65.angle == 65 and abs(a65.force - 56) < 1.5
    # todo candidato deve prever um impacto perto do alvo
    for c in rec.candidates[:5]:
        assert abs(c.predicted_x - 10) < 0.3


def test_wind_changes_documented_angle(kb, params):
    aimer = Aimer(kb, params)
    rec = aimer.recommend(ShotContext(distance=10, wind=2, allowed_methods=("a65",)))
    assert rec.best.angle == 69


def test_allowed_methods_and_invalid_distance(kb, params):
    aimer = Aimer(kb, params)
    rec = aimer.recommend(ShotContext(distance=8, allowed_methods=("high",)))
    assert {c.method for c in rec.candidates} == {"high"}
    assert aimer.recommend(ShotContext(distance=0)).best is None


def test_terrain_blocks_flat_shots(kb, params):
    aimer = Aimer(kb, params)
    wall = np.array([[0, -5], [4.9, -5], [5.0, 6], [5.6, 6], [5.7, -5], [30, -5]], float)
    rec = aimer.recommend(ShotContext(distance=10, terrain=wall))
    assert rec.best is not None and not rec.best.blocked
    blocked = [c for c in rec.candidates if c.blocked]
    assert blocked and all(c.angle < rec.best.angle for c in blocked)


def test_weapon_scale_reduces_force(kb, params):
    aimer = Aimer(kb, params)
    normal = aimer.recommend(ShotContext(distance=10, allowed_methods=("fisica",)))
    strong = aimer.recommend(ShotContext(distance=10, allowed_methods=("fisica",), weapon=Weapon(force_scale=1.2)))
    by_angle = {c.angle: c.force for c in normal.candidates}
    common = [c for c in strong.candidates if c.angle in by_angle]
    assert common and all(c.force < by_angle[c.angle] for c in common)
