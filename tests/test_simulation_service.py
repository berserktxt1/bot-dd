import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ddbot.activities import RunStatus, activity_from_option
from ddbot.automation.input import RecordingBackend
from ddbot.simulation import SimSettings, run_simulation

ROOT = Path(__file__).resolve().parents[1]


def test_calibration_improves_hit_rate(kb, params):
    s = SimSettings(seed=11)
    plain = run_simulation(kb, params, battles=6, settings=s, calibrate=False)
    learned = run_simulation(kb, params, battles=6, settings=s, calibrate=True)
    assert learned.mean_abs_error_second_half < plain.mean_abs_error_second_half
    assert learned.hit_rate > plain.hit_rate


def test_invisible_targets_handled(kb, params):
    r = run_simulation(kb, params, battles=4, settings=SimSettings(seed=4, hide_probability=0.4))
    assert r.shots > 0 and r.battles == 4


def test_service_simulated_run(home, monkeypatch):
    from ddbot.service import BotService
    svc = BotService(home, input_backend=RecordingBackend(), start_hotkey=False)
    # a área de trabalho de quem roda a suíte não pode entrar no teste: num PC com o DDTank (ou
    # outra janela com "DDTank" no título) aberto, o bot conectava nela e a recusa era pelas regras
    monkeypatch.setattr(svc, "inventory", lambda ranked=True: [])
    try:
        assert svc.paths.config_file.exists()
        d = svc.create_activity("instancia_teste", "Teste", "instancia", "pve")
        defs, errors = svc.activities()
        assert [x.key for x in defs] == [d.key] and not errors
        ok, why = svc.start(d, 0, simulated=True)
        assert ok, why
        time.sleep(1.0)
        svc.pause()
        assert svc.status == RunStatus.PAUSED
        svc.resume()
        t = time.monotonic()
        svc.stop()
        assert time.monotonic() - t < 3.5 and not svc.runner.alive
        kinds = {e.kind for e in svc.history}
        assert "etapa" in kinds
        # real sem janela: recusa com mensagem
        ok, why = svc.start(d, 1, simulated=False)
        assert not ok and "janela" in why
        # real com regras não confirmadas: recusa
        from ddbot.capture import ArraySource
        svc.set_source(ArraySource(None))
        ok, why = svc.start(d, 1, simulated=False)
        assert not ok and "regras" in why
        assert svc.recommend(10, 0).best is not None
    finally:
        svc.close()


def test_emergency_stop_service(home):
    from ddbot.service import BotService
    svc = BotService(home, start_hotkey=False)
    try:
        d = activity_from_option("instancia_teste", "T")
        assert svc.start(d, 0, simulated=True)[0]
        time.sleep(0.5)
        svc.emergency_stop()
        svc.runner.join(2)
        assert not svc.runner.alive
        assert svc.start(d, 1, simulated=True)[0]  # após emergência, novo início funciona
        svc.stop()
    finally:
        svc.close()


def test_selftest_cli(tmp_path):
    out = tmp_path / "self.json"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "DDBOT_SELFTEST_OUT": str(out)}
    res = subprocess.run([sys.executable, "-m", "ddbot", "--selftest", "--home", str(tmp_path / "h")],
                         env=env, capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, res.stdout + res.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["resultado"] == "OK"


def test_gui_smoke(tmp_path):
    pytest.importorskip("tkinter")
    if sys.platform != "win32" and not os.environ.get("DISPLAY"):
        pytest.skip("sem display")
    out = tmp_path / "smoke.json"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "DDBOT_SMOKE_OUT": str(out)}
    res = subprocess.run([sys.executable, "-m", "ddbot", "--gui-smoke", "8", "--home", str(tmp_path / "h")],
                         env=env, capture_output=True, text=True, timeout=120)
    report = json.loads(out.read_text(encoding="utf-8"))
    assert res.returncode == 0 and report["resultado"] == "OK", json.dumps(report, indent=1) + res.stderr


def test_service_real_start_order_with_game_found(home, monkeypatch):
    """Jogo encontrado e conectado, sem autorização: recusa pelas regras (e não finge que falta a janela).

    O modo demonstração continua sem precisar de janela nem de autorização (não envia nada ao jogo).
    """
    from ddbot.capture import ArraySource
    from ddbot.service import BotService
    svc = BotService(home, input_backend=RecordingBackend(), start_hotkey=False)
    monkeypatch.setattr(svc, "inventory", lambda ranked=True: [])
    try:
        d = svc.create_activity("instancia_teste", "Teste", "instancia", "pve")
        assert not svc.config.get("automation.server_rules_confirmed")
        ok, why = svc.start(d, 1, simulated=True)
        assert ok, why
        svc.stop()
        svc.set_source(ArraySource(None))
        ok, why = svc.start(d, 1, simulated=False)
        assert not ok and "regras" in why and "janela" not in why
    finally:
        svc.close()
