"""Fluxo de demonstração: partidas e instâncias completas no cliente simulado (sem o jogo)."""
import time

import pytest

from ddbot.activities import RunStatus, activity_from_option
from ddbot.simulation import drive, simulated_activity


def run(kb, params, kind, runs, faults=None, max_steps=20000):
    d = activity_from_option(f"{kind}_teste", f"{kind} de demonstração", kind, "pve")
    events = []
    runner, client, engine, clock, cleanup = simulated_activity(kb, params, d, runs=runs, faults=faults)
    runner.on_event = lambda e: events.append(e)
    try:
        status = drive(runner, max_steps)
    finally:
        cleanup()
    return status, runner, client, events


def no_repeated_click(clicks):
    """O mesmo botão nunca é clicado duas vezes seguidas na mesma tela sem o jogo ter ignorado o clique."""
    return all(a != b for a, b in zip(clicks, clicks[1:]))


@pytest.mark.parametrize("kind,entry,menu", [("partida", "botao_partidas", "menu_partidas"),
                                             ("instancia", "botao_instancias", "menu_instancias")])
def test_one_complete_run(kb, params, kind, entry, menu):
    status, runner, client, events = run(kb, params, kind, 1)
    assert status == RunStatus.FINISHED, runner.reason
    assert client.clicks[:3] == [("lobby", entry), (menu, f"{kind}_teste"), ("sala", "botao_iniciar")]
    c = runner.counters
    assert c.completed == 1 and c.victories + c.defeats == 1 and client.battles_started == 1
    assert client.screen == "lobby"  # voltou ao lobby depois do resultado
    assert any(e.kind == "combate" or "disparo" in e.message for e in events) or client.world.state.log
    assert no_repeated_click(client.clicks)


def test_three_consecutive_matches(kb, params):
    status, runner, client, events = run(kb, params, "partida", 3)
    assert status == RunStatus.FINISHED, runner.reason
    assert runner.counters.completed == 3 and client.battles_started == 3
    assert [t for s, t in client.clicks].count("botao_partidas") == 3
    results = [e for e in events if e.kind == "resultado"]
    assert [e.message.endswith(f"({i}/3)") for i, e in enumerate(results, 1)] == [True] * 3
    assert no_repeated_click(client.clicks)


def test_continuous_matches_until_stopped(kb, params):
    d = activity_from_option("partida_teste", "Partida", "partida", "pve")
    runner, client, engine, clock, cleanup = simulated_activity(kb, params, d, runs=0)
    try:
        drive(runner, 400)
        assert runner.status == RunStatus.RUNNING and runner.counters.completed >= 3
        runner.request_stop("parado pelo usuário")
        assert not runner.run_once() and runner.status == RunStatus.IDLE
    finally:
        cleanup()


def test_match_stuck_in_lobby_warns_then_pauses(kb, params):
    """Sem o botão de partidas na tela, o bot avisa cedo e pausa com o motivo (sem laço infinito)."""
    status, runner, client, events = run(kb, params, "partida", 1, faults={"missing_button": "botao_partidas"})
    assert status == RunStatus.PAUSED and "botao_partidas" in runner.reason
    warns = [e.message for e in events if e.kind == "aviso" and e.message.startswith("procurando")]
    assert len(warns) == 1 and "lobby" in warns[0]
    assert client.clicks == []


def test_match_menu_without_option_pauses(kb, params):
    """Opção de partida que não está no menu de partidas: pausa explicando, não clica em outra coisa."""
    d = activity_from_option("partida_inexistente", "Outra", "partida", "pve")
    runner, client, engine, clock, cleanup = simulated_activity(kb, params, d, runs=1)
    client.option = "partida_teste"
    try:
        assert drive(runner, 5000) == RunStatus.PAUSED
        # a mensagem diz qual atividade não está no menu e que nenhuma outra foi escolhida no lugar
        assert "a opção Outra não foi encontrada no menu" in runner.reason and client.screen == "menu_partidas"
        assert "não escolhe outra atividade" in runner.reason
        assert client.clicks == [("lobby", "botao_partidas")]  # nada foi clicado no menu
    finally:
        cleanup()


def test_service_demo_match_reaches_result(home):
    """Pela camada usada pela interface (threads e esperas reais), a partida de demonstração termina."""
    from ddbot.service import BotService
    svc = BotService(home, start_hotkey=False)
    try:
        d = activity_from_option("partida_teste", "Partida de demonstração", "partida", "pve")
        ok, why = svc.start(d, 1, simulated=True)
        assert ok, why
        deadline = time.monotonic() + 90
        while svc.runner.alive and time.monotonic() < deadline:
            time.sleep(0.2)
        assert svc.status == RunStatus.FINISHED, svc.runner.reason
        msgs = [e.message for e in svc.history]
        assert "clicou em botao_partidas" in msgs and any("(1/1)" in m for m in msgs)
    finally:
        svc.close()
