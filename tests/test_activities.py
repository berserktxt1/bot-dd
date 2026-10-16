import json

import pytest

from ddbot.activities import (ActivityDef, ActivityRunner, RunLimits, RunStatus, activity_from_option,
                              load_activities)
from ddbot.automation.safety import KillSwitch
from ddbot.config import Config
from ddbot.simulation import FakeClock, SimSettings, drive, simulated_activity


@pytest.fixture
def inst():
    return activity_from_option("instancia_teste", "Teste", "instancia", "pve")


def run(kb, params, d, **kw):
    runner, client, engine, clock, cleanup = simulated_activity(kb, params, d, **kw)
    try:
        status = drive(runner)
    finally:
        cleanup()
    return status, runner, client


def test_full_runs_complete(kb, params, inst):
    status, r, c = run(kb, params, inst, runs=2)
    assert status == RunStatus.FINISHED
    assert r.counters.completed == 2 and r.counters.battles == 2
    assert c.clicks.count(("sala", "botao_iniciar")) == 2
    assert c.screen == "lobby"


def test_multi_stage_instance(kb, params, inst):
    status, r, c = run(kb, params, inst, runs=1, faults={"stage_battles": 3})
    assert status == RunStatus.FINISHED and r.counters.battles == 3 and r.counters.completed == 1
    assert c.clicks.count(("etapa_concluida", "botao_continuar")) == 2


def test_popup_recovered(kb, params, inst):
    status, r, c = run(kb, params, inst, runs=1, faults={"popup_at": 3})
    assert status == RunStatus.FINISHED and r.counters.recoveries >= 1


def test_unknown_screen_pauses(kb, params, inst):
    status, r, _ = run(kb, params, inst, runs=1, faults={"unknown_at": 2, "unknown_for": 10_000})
    assert status == RunStatus.PAUSED and "desconhecida" in r.reason


def test_missing_button_pauses_without_spamming(kb, params, inst):
    status, r, c = run(kb, params, inst, runs=1, faults={"missing_button": "botao_iniciar"})
    assert status == RunStatus.PAUSED and "botao_iniciar" in r.reason
    assert ("sala", "botao_iniciar") not in c.clicks


def test_disconnect_stops(kb, params, inst):
    status, r, _ = run(kb, params, inst, runs=3, faults={"disconnect_at": 15})
    assert status == RunStatus.FAILED and "desconex" in r.reason


def test_defeat_limit(kb, params, inst):
    # o "jogo" é bem diferente do modelo e o alvo é minúsculo: o bot perde
    hard = SimSettings(true_speed_scale=1.3, target_width=0.01, max_turns=3)
    status, r, _ = run(kb, params, inst, runs=0, settings=hard, calibrate=False,
                       limits=RunLimits(runs=0, max_defeats=2))
    assert status == RunStatus.FINISHED and r.counters.defeats == 2 and "derrotas" in r.reason or \
        r.counters.defeats == 2


def test_time_limit(kb, params, inst):
    status, r, _ = run(kb, params, inst, runs=0, limits=RunLimits(runs=0, max_minutes=0.05))
    assert status == RunStatus.FINISHED and r.counters.completed >= 1


def test_requires_authorization_and_pve(kb, params, inst):
    runner, *_rest, cleanup = simulated_activity(kb, params, inst, config_overrides={
        "automation": {"server_rules_confirmed": False}})
    assert not runner.check_allowed()[0]
    cleanup()
    pvp = activity_from_option("partida_x", "X", "partida", "pvp")
    runner, *_rest, cleanup = simulated_activity(kb, params, pvp)
    ok, why = runner.check_allowed()
    assert not ok and "PvE" in why
    cleanup()


def test_forbidden_template_blocked(kb, params, inst):
    inst.flow["sala"][0].target = "botao_comprar"
    runner, *_rest, cleanup = simulated_activity(kb, params, inst)
    assert not runner.check_allowed()[0]
    cleanup()
    runner, *_rest, cleanup = simulated_activity(kb, params, inst, config_overrides={
        "automation": {"allowed_paid_templates": ["botao_comprar"]}})
    assert runner.check_allowed()[0]
    cleanup()


def test_definition_roundtrip_and_validation(tmp_path, inst):
    inst.save(tmp_path)
    (tmp_path / "ruim.json").write_text(json.dumps({"id": "ruim", "fluxo": {"lobby": [{"tecla": "esc"}]}}),
                                        encoding="utf-8")
    defs, errors = load_activities(tmp_path)
    assert [d.key for d in defs] == [inst.key] and len(errors) == 1
    assert defs[0].to_raw() == inst.to_raw()
    assert "botao_iniciar" in defs[0].templates_needed()
    with pytest.raises(ValueError):
        ActivityDef.from_raw({"id": "x", "categoria": "nada", "fluxo": {"v": [{"concluir": "vitoria"}]}})


def test_stop_and_pause_from_other_thread(kb, params, inst):
    """Com tempo real: pausar congela, retomar continua e parar encerra a thread."""
    import time

    from ddbot.simulation import SimulatedClient, SimulatedWorld

    world = SimulatedWorld(params)
    client = SimulatedClient(world)
    cfg = Config(data={"automation": {"server_rules_confirmed": True}})
    steps = {"n": 0}

    def combat_step():
        steps["n"] += 1
    r = ActivityRunner(inst, client, client, combat_step, KillSwitch(), cfg, RunLimits(runs=0))
    r.POLL_S = 0.02
    r.start()
    time.sleep(0.3)
    r.pause()
    time.sleep(0.2)
    reads = client.reads
    time.sleep(0.3)
    assert client.reads == reads and r.status == RunStatus.PAUSED
    r.resume()
    time.sleep(0.2)
    assert r.status == RunStatus.RUNNING
    r.request_stop()
    r.join(2)
    assert not r.alive


def test_emergency_stop_interrupts(kb, params, inst):
    import time

    from ddbot.simulation import SimulatedClient, SimulatedWorld
    kill = KillSwitch()
    client = SimulatedClient(SimulatedWorld(params))
    cfg = Config(data={"automation": {"server_rules_confirmed": True}})
    r = ActivityRunner(inst, client, client, lambda: time.sleep(0.01), kill, cfg, RunLimits(runs=0))
    r.start()
    time.sleep(0.2)
    kill.trigger("teste")
    r.join(1.0)
    assert not r.alive


def test_fake_clock():
    c = FakeClock()
    t = c()
    c.advance(2)
    assert c() == t + 2
