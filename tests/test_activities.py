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
    assert status == RunStatus.FINISHED and "derrotas" in r.reason
    assert r.counters.defeats == 2


def test_time_limit(kb, params, inst):
    # o limite é conferido sempre que o bot está fora de uma atividade (telas iniciais);
    # dentro dela, termina a execução atual antes de parar
    status, r, _ = run(kb, params, inst, runs=0, limits=RunLimits(runs=0, max_minutes=0.5))
    assert status == RunStatus.FINISHED and "tempo máximo" in r.reason
    assert r.counters.completed >= 1 and r.counters.battles == r.counters.completed
    status, r, _ = run(kb, params, inst, runs=0, limits=RunLimits(runs=0, max_minutes=0.04))
    assert status == RunStatus.FINISHED and r.counters.battles == 0  # não entra em batalha nova


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


def test_failure_frame_saved(kb, params, inst):
    import numpy as np
    runner, client, *_rest, cleanup = simulated_activity(kb, params, inst, faults={"missing_button": "botao_iniciar"})
    saved = []
    runner.on_failure_frame = lambda f, why: saved.append(why)
    orig = client.read

    def read_with_frame():
        s = orig()
        s.frame = np.zeros((4, 4, 3), np.uint8)
        return s
    client.read = read_with_frame
    drive(runner)
    cleanup()
    assert saved and "botao_iniciar" in saved[0]


# ---------------------------------------------------------------- regressões da auditoria
def test_single_false_victory_frame_not_counted(kb, params, inst):
    """Um quadro de 'vitória' no meio da batalha não conta resultado nem reinicia o combate."""
    runner, client, engine, clock, cleanup = simulated_activity(kb, params, inst, runs=1)
    resets = []
    orig = runner.on_battle_start
    runner.on_battle_start = lambda: (resets.append(1), orig())
    # o quadro falso aparece logo depois do início da batalha
    client.faults["flash_at"] = (12, "vitoria")
    drive(runner)
    cleanup()
    assert runner.status == RunStatus.FINISHED
    assert runner.counters.completed == 1 and runner.counters.battles == 1 and len(resets) == 1


def test_limits_work_without_result_screen(kb, params, inst):
    """O jogo volta ao lobby sem tela de vitória/derrota: a execução conta como 'sem resultado'."""
    status, r, _ = run(kb, params, inst, runs=2, faults={"skip_result": True})
    assert status == RunStatus.FINISHED
    assert r.counters.completed == 2 and r.counters.unknown_results == 2


def test_focus_lost_pauses_instead_of_emergency(kb, params, inst):
    status, r, _ = run(kb, params, inst, runs=1, faults={"focus_lost_on": "botao_iniciar"})
    assert status == RunStatus.PAUSED and "frente" in r.reason


def test_window_minimized_pauses(kb, params, inst):
    status, r, _ = run(kb, params, inst, runs=1, faults={"window_gone_at": 4})
    assert status == RunStatus.PAUSED and "minimizada" in r.reason


def test_no_focus_waits_then_pauses(kb, params, inst):
    status, r, c = run(kb, params, inst, runs=1, faults={"no_focus_at": 4})
    assert status == RunStatus.PAUSED and "frente" in r.reason
    assert c.clicks == [("lobby", "botao_cais")] or len(c.clicks) <= 1  # nada clicado sem foco


def test_transient_read_errors_tolerated(kb, params, inst):
    status, r, _ = run(kb, params, inst, runs=1, faults={"read_error_at": {5, 9}})
    assert status == RunStatus.FINISHED and r.counters.completed == 1


def test_repeated_errors_pause(kb, params, inst):
    status, r, _ = run(kb, params, inst, runs=1, faults={"read_error_at": {5, 6, 7}})
    assert status == RunStatus.PAUSED and "erros repetidos" in r.reason


def test_ignored_click_is_retried(kb, params, inst):
    status, r, c = run(kb, params, inst, runs=1, faults={"ignore_first_click": "botao_iniciar"})
    assert status == RunStatus.FINISHED
    assert ("sala", "botao_iniciar:ignorado") in c.clicks and ("sala", "botao_iniciar") in c.clicks


def test_unknown_screen_never_sends_keys(kb, params, inst):
    status, r, c = run(kb, params, inst, runs=1, faults={"unknown_at": 2, "unknown_for": 10_000})
    assert status == RunStatus.PAUSED and c.keys == []  # nada de ESC às cegas


def test_recurring_popup_recovered_each_time(kb, params, inst):
    runner, client, engine, clock, cleanup = simulated_activity(kb, params, inst, runs=2)
    orig_read = client.read

    seen = set()

    def read_with_popups():
        # um aviso no Cais e outro na sala (antes: na 3ª e na 60ª leitura; com leituras mais frequentes a 60ª cai
        # na batalha, onde o X não é clicado de propósito)
        if client.screen in ("cais_expedicao", "sala") and client.screen not in seen and not client._popup:
            seen.add(client.screen)
            client._popup = True
        return orig_read()
    client.read = read_with_popups
    drive(runner)
    cleanup()
    assert runner.status == RunStatus.FINISHED and runner.counters.recoveries == 2


def test_paused_time_not_counted(kb, params, inst):
    runner, client, engine, clock, cleanup = simulated_activity(kb, params, inst, runs=0,
                                                                limits=RunLimits(runs=0, max_minutes=1))
    runner.status = RunStatus.RUNNING
    runner.pause()
    clock.advance(600)
    runner.resume()
    assert runner.counters.elapsed() < 1
    cleanup()


def test_pause_resume_race_does_not_resurrect_failed_run(kb, params, inst):
    runner, *_rest, cleanup = simulated_activity(kb, params, inst)
    runner.status = RunStatus.FAILED
    runner.pause()
    assert runner.status == RunStatus.FAILED
    cleanup()


def test_definition_rejects_path_names(tmp_path):
    with pytest.raises(ValueError):
        ActivityDef.from_raw({"id": "../x", "fluxo": {"v": [{"concluir": "vitoria"}]}})
    with pytest.raises(ValueError):
        ActivityDef.from_raw({"id": "x", "fluxo": {"lobby": [{"clicar": "../../segredo"}],
                                                  "v": [{"concluir": "vitoria"}]}})


def test_multistage_defeat_prevails(kb, params, inst):
    """Uma instância que mostra 'vitória' por etapa e 'derrota' no fim conta derrota."""
    runner, client, engine, clock, cleanup = simulated_activity(kb, params, inst, runs=1)
    runner._in_activity = True
    runner._pending_result = "vitoria"
    a_def = inst.flow["derrota"][0]
    runner._visit_done_actions = 0
    runner._run_actions("derrota", [a_def], client.read(), clock())
    assert runner._pending_result == "derrota"
    runner._run_actions("vitoria", [inst.flow["vitoria"][0]], client.read(), clock())
    assert runner._pending_result == "derrota"
    cleanup()


def test_action_condition_parses_and_round_trips():
    from ddbot.activities import Action
    a = Action.parse({"clicar": "botao_iniciar", "espera": 2.0, "se": "com_escolha"})
    assert a.when == "com_escolha" and Action.parse(a.to_raw()) == a
    assert Action.parse({"clicar": "botao_iniciar"}).when is None
    for bad in ({"clicar": "botao_iniciar", "se": "talvez"}, {"aguardar": 1.0, "se": "sem_escolha"}):
        with pytest.raises(ValueError):
            Action.parse(bad)
