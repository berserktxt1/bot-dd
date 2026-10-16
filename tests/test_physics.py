import numpy as np
import pytest

from ddbot.physics import PhysicsParams, impact_time, landing_x, solve_force, trajectory


def test_solve_force_inverts_landing(params):
    rng = np.random.default_rng(3)
    n = 500
    a = rng.uniform(10, 89, n)
    d = rng.uniform(0.5, 20, n)
    w = rng.uniform(-3, 3, n)
    dy = rng.uniform(-2, 2, n)
    f = solve_force(a, d, w, dy, params)
    ok = np.isfinite(f)
    assert ok.mean() > 0.6
    x = landing_x(a[ok], f[ok], w[ok], dy[ok], params)
    assert np.max(np.abs(x - d[ok])) < 0.02


def test_impossible_target_is_nan(params):
    # alvo muito alto e perto com ângulo baixo: não existe força que pouse nele descendo
    assert np.isnan(solve_force(20, 0.5, 0, 3.0, params))


def test_tailwind_goes_farther(params):
    base = float(landing_x(50, 50, 0, 0, params))
    assert float(landing_x(50, 50, 2, 0, params)) > base
    assert float(landing_x(50, 50, -2, 0, params)) < base


def test_more_force_goes_farther(params):
    xs = landing_x(45, np.array([30, 50, 70, 90.0]), 0, 0, params)
    assert np.all(np.diff(xs) > 0)


def test_higher_target_needs_more_force(params):
    assert float(solve_force(50, 8, 0, 1.0, params)) > float(solve_force(50, 8, 0, -1.0, params))


def test_no_drag_matches_ballistic():
    p = PhysicsParams(speed_k=1.0, gravity=1.0, drag=0.0, wind_k=0.0, launch_h=0.0)
    # alcance de um projétil sem arrasto: v² sin(2θ) / g
    assert float(landing_x(45, 3.0, 0, 0, p)) == pytest.approx(9.0, rel=1e-4)
    assert float(impact_time(30, 2.0, 0, 0, p)) == pytest.approx(2.0, rel=1e-4)


def test_trajectory_starts_at_shooter(params):
    pts = trajectory(60, 60, 1, params)
    assert pts[0, 0] == pytest.approx(0.0)
    assert pts[0, 1] == pytest.approx(params.launch_h)
    assert pts[-1, 1] < 0


def test_params_roundtrip(tmp_path, params):
    path = tmp_path / "p.json"
    params.save(path, {"x": 1})
    assert PhysicsParams.load(path) == params
