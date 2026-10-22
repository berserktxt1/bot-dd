"""Atividades pré-cadastradas (catálogo), disponibilidade no cliente e as estratégias de cada dificuldade.

Tudo aqui é simulação ou imagem sintética: prova a lógica (escolha da opção e da dificuldade, pausa
quando a atividade não está no menu, pontuação, papéis a evitar), não o funcionamento no DDClássico.
"""
import json
import re
from pathlib import Path

import numpy as np
import pytest

from ddbot.activities import RunStatus
from ddbot.catalog import AVAILABLE, MISSING, UNVERIFIED, USER_OFF, AvailabilityStore, build_activity, load_catalog
from ddbot.simulation import SimSettings, drive, simulated_activity
from ddbot.strategy import GENERIC_ROLE, StrategyPlanner, load_profiles, match_profile
from ddbot.vision.perception import Character

ROOT = Path(__file__).resolve().parents[1]
SIX = ["formigueiro_facil", "formigueiro_normal", "galinheiro_facil", "galinheiro_normal", "galinheiro_dificil",
       "olimpiadas_bugou_normal"]
ME = Character(0.0, 0.0, 0.95, "eu", "teste")


@pytest.fixture(scope="module")
def catalog():
    cat, errors = load_catalog(ROOT / "data" / "knowledge" / "catalogo.json")
    assert not errors
    return cat


@pytest.fixture(scope="module")
def profiles():
    ps, errors = load_profiles(ROOT / "data" / "knowledge" / "instances.json")
    assert not errors
    return ps


def enemy(kind, x, y=0.0):
    return Character(x, y, 0.95, kind, "teste")


# ------------------------------------------------------------------ catálogo
def test_six_priority_activities_in_order_and_castle_out_of_main_list(catalog, profiles):
    assert [e.key for e in catalog.entries] == SIX
    names = [e.name for e in catalog.entries]
    assert names == ["Formigueiro — Fácil", "Formigueiro — Normal", "Galinheiro — Fácil", "Galinheiro — Normal",
                     "Galinheiro — Difícil", "Olimpíadas Bugou — Normal"]
    assert not any("Castelo" in n for n in names)
    out = {x["id"]: x for x in catalog.replaced}
    assert out["castelo_bugou_normal"]["estrategia"] == "bugou_normal" and "Olimpíadas" in out["castelo_bugou_normal"]["motivo"]
    for e in catalog.entries:
        p = profiles[e.strategy]
        assert p.runnable, e.key
        # a dificuldade da atividade é a do perfil (nada de estratégia de outra dificuldade)
        assert [catalog.difficulties[e.difficulty].name] == list(p.difficulties), e.key


def test_olimpiadas_bugou_is_not_the_bugou_castle(catalog, profiles):
    olim = catalog.get("olimpiadas_bugou_normal")
    assert olim.option == "instancia_olimpiadas_bugou" and olim.strategy == "olimpiadas_bugou_normal"
    castle = profiles["bugou_normal"]
    assert olim.option != "instancia_bugou_normal" and profiles[olim.strategy].model_key != castle.model_key
    # o nome dado a uma atividade capturada também não confunde as duas instâncias
    assert match_profile("Olimpíadas Bugou Normal", profiles).key == "olimpiadas_bugou_normal"
    assert match_profile("Castelo do Reino de Bugou Normal", profiles).key == "bugou_normal"
    assert match_profile("Bugou Normal", profiles) is None
    assert match_profile("Olimpíadas Boom", profiles) is None  # sem dificuldade no nome: não chuta


def test_built_activity_selects_option_then_difficulty(catalog):
    d = build_activity(catalog.get("galinheiro_dificil"), catalog)
    acts = d.flow["menu_instancias"]
    assert [(a.kind, a.target) for a in acts][:2] == [("clicar", "instancia_galinheiro"),
                                                      ("clicar", "dificuldade_dificil")]
    assert d.builtin and d.instance == "galinheiro" and d.difficulty == "dificil" and d.auto_allowed
    # as dificuldades da mesma instância usam a mesma opção do menu (uma captura só)
    assert build_activity(catalog.get("galinheiro_facil"), catalog).option == d.option


def test_difficulties_share_target_captures(profiles):
    a, b = profiles["formigueiro_facil"], profiles["formigueiro_normal"]
    assert a.role_template("rainha") == b.role_template("rainha") == "alvo_formigueiro_rainha"
    assert profiles["galinheiro_dificil"].role_template("chefe") == "alvo_galinheiro_chefe"


def test_difficulty_profiles_follow_their_sources(profiles):
    stages = {k: [s.key for s in profiles[k].stages] for k in SIX}
    assert stages["formigueiro_facil"] == stages["formigueiro_normal"] == ["formigas", "rainha"]
    assert stages["galinheiro_facil"] == ["pintinhos", "chefe"]
    assert stages["galinheiro_normal"] == ["pintinhos", "construcao", "chefe"]
    assert stages["galinheiro_dificil"][0] == "pintinhos" and len(stages["galinheiro_dificil"]) == 4
    assert stages["olimpiadas_bugou_normal"] == ["baloes", "corrida", "boxiador"]
    kinds = [s.kind for s in profiles["olimpiadas_bugou_normal"].stages]
    assert kinds == ["pontuacao", "corrida", "combate"]  # não é uma instância comum de "escolher e atirar"


def test_catalog_with_errors_keeps_valid_entries(tmp_path):
    bad = {"dificuldades": {"facil": {"nome": "Fácil", "modelo": "dificuldade_facil"}},
           "atividades": [{"id": "ok", "instancia": "x", "dificuldade": "facil"},
                          {"id": "../fora", "instancia": "x"}, {"id": "sem_nivel", "instancia": "x", "dificuldade": "zz"}]}
    path = tmp_path / "c.json"
    path.write_text(json.dumps(bad), "utf-8")
    cat, errors = load_catalog(path)
    assert [e.key for e in cat.entries] == ["ok"] and len(errors) == 2


# ------------------------------------------------------------ disponibilidade
def test_availability_store_persists_and_tolerates_bad_file(tmp_path):
    path = tmp_path / "estado.json"
    store = AvailabilityStore(path)
    assert store.status("formigueiro_facil") == UNVERIFIED
    assert store.set("formigueiro_facil", MISSING, "não encontrada no menu") is True
    assert store.set("formigueiro_facil", MISSING, "não encontrada no menu") is False  # nada mudou
    again = AvailabilityStore(path)
    assert again.status("formigueiro_facil") == MISSING and "não encontrada" in again.detail("formigueiro_facil")
    with pytest.raises(ValueError):
        again.set("x", "talvez")
    path.write_text("{lixo", "utf-8")
    assert AvailabilityStore(path).status("formigueiro_facil") == UNVERIFIED


def test_service_lists_six_before_connecting_and_protects_builtins(home, monkeypatch):
    from ddbot.service import BotService
    svc = BotService(home, start_hotkey=False)
    monkeypatch.setattr(svc, "inventory", lambda ranked=True: [])
    try:
        assert svc.window is None  # nada conectado
        defs, errors = svc.activities()
        assert [d.key for d in defs[:6]] == SIX and not errors
        d = defs[0]
        with pytest.raises(ValueError):
            svc.delete_activity(d)
        with pytest.raises(ValueError):
            svc.set_strategy(d, "galinheiro")
        # o usuário ajusta o fluxo para o cliente dele: a versão dele substitui a pré-cadastrada
        mine = build_activity(svc.catalog.get("formigueiro_facil"), svc.catalog)
        mine.builtin = False
        mine.flow["sala"][0].seconds = 3.0
        mine.save(svc.paths.instances)
        defs, _ = svc.activities()
        assert [x.key for x in defs].count("formigueiro_facil") == 1
        custom = next(x for x in defs if x.key == "formigueiro_facil")
        assert not custom.builtin and custom.flow["sala"][0].seconds == 3.0 and custom.strategy == "formigueiro_facil"
        # opção vista numa captura do menu: as duas dificuldades da instância ficam disponíveis
        assert set(svc.mark_options_seen(["instancia_formigueiro"])) == {"Formigueiro — Fácil", "Formigueiro — Normal"}
        assert svc.availability_of(defs[1])[0] == AVAILABLE
        svc.set_availability(defs[1], USER_OFF, "marcada por você")
        assert svc.mark_options_seen(["instancia_formigueiro"]) == ["Formigueiro — Fácil"]  # a escolha do usuário fica
    finally:
        svc.close()


def test_readiness_explains_option_and_difficulty(home, monkeypatch):
    from ddbot.service import BotService
    svc = BotService(home, start_hotkey=False)
    try:
        d = next(x for x in svc.activities()[0] if x.key == "olimpiadas_bugou_normal")
        missing = {m.label: m for m in svc.readiness(d)}
        opt = missing["opção Olimpíadas Bugou no menu"]
        assert opt.required and opt.where == "Calibração > Menu" and opt.key == "instancia_olimpiadas_bugou"
        diff = missing["botão da dificuldade Normal"]
        assert diff.required and "todas as instâncias" in diff.how
        # sem os balões verdes e o juiz, as etapas especiais não agem: são obrigatórios
        required_targets = {m.key for m in missing.values() if m.where.endswith("Alvos da instância") and m.required}
        assert {"alvo_olimpiadas_bugou_balao_verde", "alvo_olimpiadas_bugou_juiz",
                "alvo_olimpiadas_bugou_bugou_rival"} <= required_targets
        assert all(m.how for m in missing.values())  # cada pendência diz como fazer
        # português: "Deixe o jogo na tela principal", e não "em a tela principal" (texto da 0.5.0 em desenvolvimento)
        assert not [m.how for m in missing.values() if re.search(r"\bem (a|o|as|os) ", m.how)]
        assert "Deixe o jogo na tela principal" in missing["tela Lobby"].how
    finally:
        svc.close()


# ------------------------------------------------- execução simulada do catálogo
@pytest.mark.parametrize("key", SIX)
def test_catalog_activity_completes_in_simulation_with_its_own_choice(kb, params, catalog, profiles, key):
    e = catalog.get(key)
    d = build_activity(e, catalog)
    r, client, eng, clock, cleanup = simulated_activity(kb, params, d, runs=1, profile=profiles[e.strategy],
                                                        settings=SimSettings(seed=4, max_turns=40,
                                                                             distance_range=(4.0, 12.0)))
    try:
        assert drive(r) == RunStatus.FINISHED, r.reason
        assert r.counters.victories == 1 and r.counters.battles == len(profiles[e.strategy].stages)
        menu = [t for screen, t in client.clicks if screen == "menu_instancias"]
        assert menu == [e.option, catalog.difficulties[e.difficulty].template]  # nada além da própria escolha
        world = client.world
        assert world.bad_hits == 0 and world.avoid_hits == 0
    finally:
        cleanup()


def test_instance_goes_through_the_dock_and_chooses_inside_the_room_every_run(kb, params, catalog, profiles):
    """Caminho do DDClássico: lobby -> Cais de Expedição -> Criar sala -> na sala, escolher a instância -> Iniciar.
    A sala volta com a instância anterior escolhida: mesmo assim cada ida escolhe de novo antes de Iniciar."""
    d = build_activity(catalog.get("formigueiro_normal"), catalog)
    assert d.start_states == ("lobby", "cais_expedicao", "sala", "menu_instancias", "menu_dificuldade")
    r, client, eng, clock, cleanup = simulated_activity(kb, params, d, runs=2, profile=profiles["formigueiro_normal"],
                                                        settings=SimSettings(seed=4, max_turns=40,
                                                                             distance_range=(4.0, 12.0)))
    client.back_to_room = True
    try:
        assert drive(r) == RunStatus.FINISHED, r.reason
        assert r.counters.completed == 2 and r.counters.victories == 2
        out = [(s, t) for s, t in client.clicks if s in ("lobby", "cais_expedicao", "sala", "menu_instancias")]
        choose = [("sala", "botao_escolher_instancia"), ("menu_instancias", "instancia_formigueiro"),
                  ("menu_instancias", "dificuldade_normal"), ("sala", "botao_iniciar")]
        assert out == [("lobby", "botao_cais"), ("cais_expedicao", "botao_criar_sala")] + choose + choose
    finally:
        cleanup()


def test_start_in_a_room_without_instance_never_clicks_start_first(kb, params, catalog, profiles):
    d = build_activity(catalog.get("galinheiro_facil"), catalog)
    r, client, eng, clock, cleanup = simulated_activity(kb, params, d, runs=1, profile=profiles["galinheiro_facil"])
    client.screen = "sala"  # o usuário já estava numa sala vazia
    try:
        assert drive(r) == RunStatus.FINISHED, r.reason
        assert client.clicks[0] == ("sala", "botao_escolher_instancia")
        assert client.clicks.index(("sala", "botao_iniciar")) > client.clicks.index(("menu_instancias",
                                                                                      "dificuldade_facil"))
    finally:
        cleanup()


def test_solo_warning_pauses_without_permission_and_continues_after_it(kb, params, catalog, profiles):
    """Aviso de instância difícil (um jogador) depois de Iniciar: sem permissão o bot pausa e explica, sem clicar
    em nada; com a permissão, Retomar confirma o aviso e a mesma ida segue para a batalha (sem reiniciar)."""
    d = build_activity(catalog.get("formigueiro_facil"), catalog)
    r, client, eng, clock, cleanup = simulated_activity(kb, params, d, runs=1, profile=profiles["formigueiro_facil"],
                                                        faults={"solo_warning": True})
    try:
        assert drive(r, 5000) == RunStatus.PAUSED
        assert r.blocked == "aviso_sozinho" and "difícil para um jogador" in r.reason
        assert client.screen == "aviso_sozinho" and not [t for s, t in client.clicks if s == "aviso_sozinho"]
        clicks_before = len(client.clicks)
        r.config.set("instances.confirm_solo_warning", True)
        r.resume()
        assert r.blocked is None
        assert drive(r) == RunStatus.FINISHED, r.reason
        after = client.clicks[clicks_before:]
        assert after[0] == ("aviso_sozinho", "botao_confirmar_aviso")
        assert ("lobby", "botao_cais") not in after  # continuou da mesma tela, não recomeçou
        assert r.counters.completed == 1 and r.counters.victories == 1
    finally:
        cleanup()


def test_solo_warning_permission_does_not_unlock_forbidden_buttons(kb, params, catalog, profiles):
    d = build_activity(catalog.get("formigueiro_facil"), catalog)
    r, client, eng, clock, cleanup = simulated_activity(kb, params, d, runs=1, profile=profiles["formigueiro_facil"],
                                                        faults={"solo_warning": True},
                                                        config_overrides={
                                                            "instances": {"confirm_solo_warning": True},
                                                            "automation": {"forbidden_templates":
                                                                           ["botao_confirmar_aviso"]}})
    try:
        ok, why = r.check_allowed()
        assert not ok and "botao_confirmar_aviso" in why
    finally:
        cleanup()


def test_option_missing_from_menu_pauses_and_marks_unavailable(home, monkeypatch):
    """Olimpíadas Bugou não aparece no menu deste cliente: pausa explicando; nunca clica em outra opção."""
    import time
    from ddbot.service import BotService
    svc = BotService(home, start_hotkey=False)
    try:
        d = next(x for x in svc.activities()[0] if x.key == "olimpiadas_bugou_normal")
        runner, engine = svc.build_runner(d, 1, simulated=True, faults={"menu_hides": ["instancia_olimpiadas_bugou"]})
        from ddbot.simulation import FakeClock
        clock = FakeClock()
        runner.clock = clock
        runner._sleep = lambda s: clock.advance(max(s, 0.05))
        svc.runner, svc.simulated = runner, False  # como no jogo real: a disponibilidade é registrada
        assert drive(runner, 5000) == RunStatus.PAUSED
        assert "a opção Olimpíadas Bugou não foi encontrada no menu" in runner.reason
        assert "não escolhe outra atividade" in runner.reason
        client = runner.reader
        assert [t for s, t in client.clicks if s == "menu_instancias"] == []
        assert svc.availability_of(d)[0] == MISSING
        assert any("não encontrada no menu" in e.message for e in svc.history)
        time.sleep(0)
    finally:
        svc.runner = None
        svc.close()


def test_difficulty_missing_pauses_without_trying_another(kb, params, catalog, profiles):
    d = build_activity(catalog.get("galinheiro_dificil"), catalog)
    r, client, eng, clock, cleanup = simulated_activity(kb, params, d, runs=1, profile=profiles["galinheiro_dificil"],
                                                        faults={"menu_hides": ["dificuldade_dificil"]})
    try:
        assert drive(r, 5000) == RunStatus.PAUSED
        assert "a dificuldade dificil" in r.reason or "dificuldade" in r.reason
        assert [t for s, t in client.clicks if s == "menu_instancias"] == ["instancia_galinheiro"]
        assert client.screen == "menu_instancias"
    finally:
        cleanup()


def test_demo_does_not_change_availability(home):
    from ddbot.service import BotService
    svc = BotService(home, start_hotkey=False)
    try:
        d = next(x for x in svc.activities()[0] if x.key == "formigueiro_facil")
        runner, engine = svc.build_runner(d, 1, simulated=True, faults={"menu_hides": ["instancia_formigueiro"]})
        from ddbot.simulation import FakeClock
        clock = FakeClock()
        runner.clock = clock
        runner._sleep = lambda s: clock.advance(max(s, 0.05))
        svc.runner, svc.simulated = runner, True
        assert drive(runner, 5000) == RunStatus.PAUSED
        assert svc.availability_of(d)[0] == UNVERIFIED  # a demonstração não diz nada sobre o cliente
    finally:
        svc.runner = None
        svc.close()


# -------------------------------------------- recusa de opção ambígua no clique
def test_actor_refuses_option_that_looks_like_another(tmp_path):
    from ddbot.automation.input import InputController, RecordingBackend
    from ddbot.automation.safety import KillSwitch
    from ddbot.capture import ArraySource
    from ddbot.config import Config
    from ddbot.game_io import GameActor
    from ddbot.vision.templates import TemplateLibrary
    rng = np.random.default_rng(7)
    frame = rng.integers(0, 255, (300, 400, 3), dtype=np.uint8)
    lib = TemplateLibrary(tmp_path / "t")
    tile = frame[100:160, 50:170].copy()
    lib.add("instancia_olimpiadas_bugou", tile)
    lib.add("instancia_bugou_normal", tile.copy())  # duas capturas iguais: não dá para saber qual é qual
    rec = RecordingBackend()
    actor = GameActor(InputController(KillSwitch(), rec), ArraySource(frame), lib, Config(data={}),
                      window_at=lambda x, y: 1, contains=lambda a, b: True)
    assert actor.click("instancia_olimpiadas_bugou", frame) is False
    assert "também se parece com instancia_bugou_normal" in actor.last_refusal and not rec.events
    lib.remove_key("instancia_bugou_normal")
    lib.add("instancia_bugou_normal", frame[200:260, 250:370].copy())  # outra opção, em outro lugar
    assert actor.click("instancia_olimpiadas_bugou", frame) is True and actor.last_refusal == ""


# ------------------------------------------------------ estratégia: novos tipos
def planner(profile, known=lambda name: True):
    return StrategyPlanner(profile, has_template=known, reach=0.6, avoid_radius=1.0)


def test_balloons_pick_best_value_and_never_a_green_one(profiles):
    pl = planner(profiles["olimpiadas_bugou_normal"])
    pl.on_battle_start()
    red_alone = enemy("balao_vermelho", 8.0)
    red_by_green = enemy("balao_vermelho", 4.0)
    greens = [enemy("balao_verde", 4.3), enemy("balao_verde", 6.0)]
    plan = pl.update([red_by_green, red_alone] + greens, [], ME, 1.0)
    assert plan.target is red_alone and "pontos esperados" in plan.reason  # o perto do verde perde pontos
    double = enemy("balao_dobro", 9.0)
    assert pl.update([red_alone, double] + greens, [], ME, 1.0).target is double
    plan = pl.update(greens, [], ME, 1.0)  # só verdes: não atira
    assert plan.target is None and plan.pause is None and "nenhum alvo que some" in plan.reason


def test_balloons_pause_without_the_models_that_tell_them_apart(profiles):
    known = lambda name: not name.endswith("balao_verde")  # noqa: E731
    pl = planner(profiles["olimpiadas_bugou_normal"], known)
    pl.on_battle_start()
    plan = pl.update([enemy("balao_vermelho", 5.0)], [], ME, 1.0)
    assert plan.target is None and plan.pause and "Balão verde" in plan.pause and "não atira" in plan.pause


def test_boxer_stage_never_aims_near_the_judge(profiles):
    pl = planner(profiles["olimpiadas_bugou_normal"])
    pl.on_battle_start()
    pl.index = 2
    boxer, judge = enemy("boxiador", 6.0), enemy("juiz", 6.5)
    plan = pl.update([boxer, judge], [], ME, 1.0)
    assert plan.target is None and "Juiz" in plan.reason and plan.pause is None
    judge.x = 9.0
    assert pl.update([boxer, judge], [], ME, 1.0).target is boxer
    assert not any(p.target is judge for p in [pl.update([judge], [], ME, 1.0)])
    # sem o modelo do juiz, a etapa não age (o marcador genérico poderia ser o juiz)
    blind = planner(profiles["olimpiadas_bugou_normal"], lambda name: not name.endswith("_juiz"))
    blind.on_battle_start()
    blind.index = 2
    assert blind.update([enemy(GENERIC_ROLE, 6.0)], [], ME, 1.0).pause


def test_race_targets_rival_bugous_where_they_bunch_up(profiles):
    pl = planner(profiles["olimpiadas_bugou_normal"], lambda name: not name.endswith("_meka"))
    pl.on_battle_start()
    pl.on_battle_start()
    assert pl.stage.key == "corrida"
    rivals = [enemy("bugou_rival", 3.0), enemy("bugou_rival", 7.0), enemy("bugou_rival", 7.4),
              enemy("bugou_rival", 7.8)]
    # o grupo de três (um disparo fere vários), não o rival sozinho mais perto
    assert pl.update(rivals, [], ME, 1.0).target.x >= 7.0
    nothing = planner(profiles["olimpiadas_bugou_normal"], lambda name: False)
    nothing.on_battle_start()
    nothing.on_battle_start()
    assert nothing.update(rivals, [], ME, 1.0).pause  # sem reconhecer os rivais, a corrida não vira combate


def test_stage_follows_the_screen_even_out_of_order(profiles):
    """Galinheiro Difícil: as fontes não garantem a ordem; a etapa é a que a tela mostra."""
    pl = planner(profiles["galinheiro_dificil"])
    pl.on_battle_start()
    for _ in range(3):
        plan = pl.update([enemy("construcao", 6.0)], [], ME, 1.0)
    assert pl.stage.key == "construcao" and plan.target.kind == "construcao"
    for _ in range(3):
        pl.update([enemy("chefe", 5.0), enemy("gaiola", 7.0)], [], ME, 1.0)
    assert pl.stage.key == "chefe"
    # o chefe ainda na tela: não volta para a construção por causa de um alvo dela
    for _ in range(4):
        pl.update([enemy("chefe", 5.0), enemy("construcao", 8.0)], [], ME, 1.0)
    assert pl.stage.key == "chefe"
