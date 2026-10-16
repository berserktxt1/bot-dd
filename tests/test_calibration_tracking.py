import numpy as np
import pytest

from ddbot.calibration import Calibrator, ShotRecord, ShotStore
from ddbot.physics import landing_x
from ddbot.tracking import Decision, TargetTracker, hit_probability_uniform


def test_store_crud(tmp_path):
    s = ShotStore(tmp_path / "s.sqlite3")
    sid = s.add(ShotRecord(angle=65, force=56, wind=0, distance=10))
    s.update_result(sid, 10.2, True, "ok")
    r = s.all()[0]
    assert (r.id, r.impact_x, r.hit, r.note) == (sid, 10.2, True, "ok")
    s.clear()
    assert s.all() == []
    s.close()


def test_offset_learns_systematic_error(tmp_path, params):
    cal = Calibrator(ShotStore(tmp_path / "c.sqlite3"), params)
    assert cal.predict_offset("a65", 65, 56, 0, 0, 10)[2] == 0
    rng = np.random.default_rng(0)
    for _ in range(12):
        d = rng.uniform(4, 16)
        f = 30 + 3 * d
        x = float(landing_x(65, f, 0, 0, params)) + 0.8  # o jogo sempre cai 0,8 além
        cal.record(ShotRecord(angle=65, force=f, wind=0, distance=d, impact_x=x, method="a65"))
    off, sigma, n = cal.predict_offset("a65", 65, 56, 0, 0, 10)
    assert n == 12 and off == pytest.approx(0.8, abs=0.15) and sigma < 0.3
    st = cal.stats()
    assert st["disparos"] == 12 and "a65" in st["modelos"]


def test_refit_recovers_speed(tmp_path, params):
    from dataclasses import replace
    true = replace(params, speed_k=params.speed_k * 1.04)
    cal = Calibrator(ShotStore(tmp_path / "r.sqlite3"), params)
    rng = np.random.default_rng(1)
    for _ in range(20):
        a, f, w = rng.uniform(30, 80), rng.uniform(30, 90), rng.uniform(-2, 2)
        cal.store.add(ShotRecord(angle=a, force=f, wind=w, distance=5, impact_x=float(landing_x(a, f, w, 0, true))))
    new, info = cal.refit_params(max_iter=300)
    assert info["perda_depois"] < info["perda_antes"] * 0.3
    assert new.speed_k > params.speed_k


def test_hidden_target_uncertainty_grows():
    tr = TargetTracker(max_move_per_turn=1.0, max_uncertainty=2.5)
    tr.observe("boss", 10.0, 0.0, turn=1)
    tr.observe("boss", 10.4, 0.0, turn=2)
    tr.mark_hidden("boss", 3)
    e3, e5 = tr.estimate("boss", 3), tr.estimate("boss", 5)
    assert 0 < e3.radius < e5.radius
    assert e3.turns_hidden == 1
    # a última posição não é tratada como certeza
    assert tr.decide("boss", 3).decision == Decision.SHOOT and tr.decide("boss", 3).estimate.radius > 0
    assert tr.decide("boss", 5).decision in (Decision.WAIT, Decision.ASK_USER)


def test_area_attack_and_unknown_target():
    tr = TargetTracker(max_move_per_turn=0.5, area_attack_radius=1.0)
    assert tr.decide("x", 1).decision == Decision.ASK_USER
    tr.observe("x", 5, 0, 1)
    tr.observe("x", 5, 0, 2)
    tr.mark_hidden("x", 3)
    assert tr.decide("x", 3, has_area_attack=True).decision == Decision.AREA_ATTACK
    tr.observe("x", 6, 0, 4)
    assert tr.decide("x", 4).decision == Decision.SHOOT


def test_single_observation_waits():
    tr = TargetTracker()
    tr.observe("x", 5, 0, 1)
    tr.mark_hidden("x", 2)
    assert tr.decide("x", 2).decision == Decision.WAIT


def test_uniform_hit_probability():
    assert hit_probability_uniform(0, 0.3) == 1.0
    assert hit_probability_uniform(1.0, 0.25) == 0.25
