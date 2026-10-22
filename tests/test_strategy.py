"""Estratégias por instância (Formigueiro, Galinheiro, Bugou Normal).

Tudo aqui é simulação ou imagem sintética: prova a lógica de etapas, prioridade, imunidade,
pausa e sem progresso, não o funcionamento no cliente real do jogo.
"""
import json
from pathlib import Path

import numpy as np
import pytest

from ddbot.activities import ActivityDef, RunStatus, activity_from_option
from ddbot.automation.safety import NeedsAttention
from ddbot.combat import BattleObservation
from ddbot.simulation import SimSettings, drive, scenario_for, simulated_activity
from ddbot.strategy import GENERIC_ROLE, StrategyPlanner, load_profiles, match_profile
from ddbot.vision.perception import Character

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ("formigueiro", "galinheiro", "bugou_normal")  # perfis gerais (atividades capturadas até a 0.4.x)
# perfis das seis atividades pré-cadastradas (uma por instância e dificuldade)
CATALOG = ("formigueiro_facil", "formigueiro_normal", "galinheiro_facil", "galinheiro_normal", "galinheiro_dificil",
           "olimpiadas_bugou_normal")
PRIORITY = ORIGINAL + CATALOG


@pytest.fixture(scope="module")
def profiles():
    ps, errors = load_profiles(ROOT / "data" / "knowledge" / "instances.json")
    assert not errors
    return ps


def enemy(kind, x, y=0.0):
    return Character(x, y, 0.95, kind, "teste")


ME = Character(0.0, 0.0, 0.95, "eu", "teste")


def planner(profile, known=True, events=None):
    return StrategyPlanner(profile, has_template=lambda name: known,
                           on_event=lambda k, m: events.append((k, m)) if events is not None else None)


# ------------------------------------------------------------------ perfis
def test_profiles_load_and_cite_registered_sources(profiles):
    sources = {s["id"] for s in json.loads((ROOT / "data/knowledge/sources.json").read_text("utf-8"))["sources"]}
    for key in PRIORITY:
        p = profiles[key]
        assert p.runnable and len(p.stages) >= 2 and scenario_for(p) is not None
    for p in profiles.values():
        assert p.sources and set(p.sources) <= sources, (p.key, set(p.sources) - sources)
    # as de pesquisa não jogam sozinhas
    assert not any(profiles[k].runnable for k in ("covil_dragao", "tribo_piatan", "castelo_sombrio",
                                                    "olimpiadas_bugou", "ilha_enamorados", "redemoinho",
                                                    "arena_guerreiros"))


def test_profile_matched_by_name_respecting_difficulty(profiles):
    assert match_profile("Formigueiro", profiles).key == "formigueiro"
    assert match_profile("Pintinho Corre Rápido (Galinheiro)", profiles).key == "galinheiro"
    assert match_profile("Castelo do Reino de Bugou Normal", profiles).key == "bugou_normal"
    assert match_profile("Castelo de Bugou Avançado", profiles) is None  # tem uma etapa a mais
    assert match_profile("Opção 3", profiles) is None


def test_invalid_profile_rejected(tmp_path):
    bad = {"instancias": [{"id": "x", "suporte": "implementado", "papeis": [{"id": "a"}],
                           "etapas": [{"id": "e", "alvos": ["b"]}], "fontes": ["f"]}]}
    path = tmp_path / "i.json"
    path.write_text(json.dumps(bad), "utf-8")
    ps, errors = load_profiles(path)
    assert not ps and "desconhecidos" in errors[0]


def test_activity_strategy_roundtrip(tmp_path):
    d = activity_from_option("instancia_formigueiro", "Formigueiro", strategy="formigueiro")
    d.save(tmp_path)
    back = ActivityDef.from_raw(json.loads(d.path.read_text("utf-8")))
    assert back.strategy == "formigueiro"
    raw = d.to_raw()
    raw["estrategia"] = "../fora"
    with pytest.raises(ValueError):
        ActivityDef.from_raw(raw)
    assert activity_from_option("partida_x", "X", "partida", strategy="formigueiro").strategy is None


# ------------------------------------------------------------- Formigueiro
def test_formigueiro_ants_then_only_queen(profiles):
    ev = []
    pl = planner(profiles["formigueiro"], events=ev)
    pl.on_battle_start()
    ants = [enemy("formiga", 3.0), enemy("formiga", 8.0), enemy("formiga", 8.6), enemy("formiga", 9.1)]
    plan = pl.update(ants, [], ME, 1.0)
    assert plan.stage.key == "formigas" and plan.target.x == 8.6  # onde há mais formigas juntas
    # a rainha aparece: só depois de leituras seguidas a etapa muda
    seen = ants + [enemy("rainha", 6.0)]
    assert pl.update(seen, [], ME, 1.0).stage.key == "formigas"
    pl.update(seen, [], ME, 1.0)
    plan = pl.update(seen, [], ME, 1.0)
    assert plan.stage.key == "rainha" and plan.target.kind == "rainha"
    assert any("Rainha" in m for k, m in ev if k == "etapa")
    # rainha fora de vista com formigas na tela: não atira nas formigas
    plan = pl.update(ants, [], ME, 1.0)
    assert plan.target is None and plan.hidden_role == "rainha"


def test_missing_role_template_falls_back_to_any_enemy_and_warns(profiles):
    ev = []
    pl = planner(profiles["formigueiro"], known=False, events=ev)
    pl.on_battle_start()
    pl.index = 1  # etapa da rainha, mas o modelo da rainha não foi capturado
    plan = pl.update([enemy(GENERIC_ROLE, 4.0), enemy(GENERIC_ROLE, 7.0)], [], ME, 1.0)
    assert plan.target is not None and plan.target.x == 4.0
    pl.update([enemy(GENERIC_ROLE, 4.0)], [], ME, 1.0)
    warns = [m for k, m in ev if k == "aviso"]
    assert len(warns) == 1 and "sem o modelo de Rainha" in warns[0]


# -------------------------------------------------------------- Galinheiro
def test_galinheiro_shoots_the_closest_threat_first(profiles):
    pl = planner(profiles["galinheiro"])
    pl.on_battle_start()
    plan = pl.update([enemy("frango", 9.0), enemy("frango", 2.5), enemy("frango", 2.7)], [], ME, 1.0)
    assert plan.target.x == 2.5


# ------------------------------------------------------------------- Bugou
def test_bugou_baron_immune_from_the_front(profiles):
    pl = planner(profiles["bugou_normal"])
    pl.on_battle_start()
    pl.on_battle_start()  # 2ª batalha da execução: etapa do Barão
    assert pl.stage.key == "barao"
    baron, minion = enemy("barao", 6.0, -1.0), enemy("bugou", 4.0)
    shield = Character(6.1, -1.4, 0.9, "barao_escudo", "teste")
    plan = pl.update([baron, minion], [shield], ME, 1.0)
    assert plan.target is minion  # Barão imune: ataca o que dá
    plan = pl.update([baron], [shield], ME, 1.0)
    assert plan.target is None and "imune" in plan.reason
    plan = pl.update([baron], [], ME, 1.0)
    assert plan.target is baron
    # estado longe do chefe (outro lugar da tela) não vale
    plan = pl.update([baron], [Character(1.0, -1.0, 0.9, "barao_escudo", "teste")], ME, 1.0)
    assert plan.target is baron


def test_bugou_midas_shield_forces_high_arc(profiles, kb, params, tmp_path):
    from ddbot.aiming import Aimer
    from ddbot.automation.safety import KillSwitch
    from ddbot.calibration import Calibrator, ShotStore
    from ddbot.combat import BattleView, CombatEngine
    from ddbot.config import Config
    from ddbot.strategy import apply_plan
    from ddbot.tracking import TargetTracker
    pl = planner(profiles["bugou_normal"])
    pl.on_battle_start()
    pl.index = 2
    midas = enemy("midas_vermelho", 7.0)
    plan = pl.update([midas], [Character(7.0, -0.5, 0.9, "midas_escudo", "teste")], ME, 1.0)
    assert plan.target is midas and plan.high_arc

    class View(BattleView):
        def observe(self):
            o = BattleObservation(True, True, distance=7.0, wind=0.0, confidence=0.95, me_x=0.0, target_x=7.0,
                                  target_y=0.0)
            apply_plan(o, plan)
            return o
    store = ShotStore(tmp_path / "s.sqlite3")
    cal = Calibrator(store, params)
    eng = CombatEngine(View(), None, Aimer(kb, params, cal), cal, TargetTracker(), KillSwitch(), Config(data={}))
    eng.step()
    rec = eng.step()
    assert rec.best is not None and rec.best.angle >= 60
    store.close()


def test_matias_fuse_pauses_only_after_consecutive_reads(profiles):
    pl = planner(profiles["bugou_normal"])
    pl.on_battle_start()
    pl.index = 3
    matias = enemy("matias", 6.0)
    fuse = Character(6.0, -0.3, 0.9, "matias_pavio", "teste")
    assert pl.update([matias], [fuse], ME, 1.0).pause is None  # um quadro só não pausa
    assert "gelo" in pl.update([matias], [fuse], ME, 1.0).pause


def test_no_progress_asks_for_help(profiles):
    pl = planner(profiles["formigueiro"])
    pl.on_battle_start()
    ants = [enemy("formiga", 4.0), enemy("formiga", 6.0)]
    pl.update(ants, [], ME, 1.0)
    msgs = [pl.on_shot() for _ in range(pl.stage.max_shots)]
    assert msgs[-1] and "sem diminuir" in msgs[-1] and not any(msgs[:-1])
    # um inimigo a menos conta como progresso
    for _ in range(pl.stage.max_shots - 1):
        assert pl.on_shot() is None
    for _ in range(StrategyPlanner.COUNT_WINDOW):  # menos inimigos de forma estável (não um quadro só)
        pl.update(ants[:1], [], ME, 1.0)
    assert pl.on_shot() is None


def test_hidden_boss_waits_then_retargets(profiles):
    pl = planner(profiles["bugou_normal"])
    pl.on_battle_start()
    pl.index = 1
    baron, minion = enemy("barao", 6.0), enemy("bugou", 3.0)
    assert pl.update([baron, minion], [], ME, 1.0).target is baron
    waits = [pl.update([minion], [], ME, 1.0) for _ in range(StrategyPlanner.HIDE_GRACE_READS - 1)]
    assert all(p.target is None and p.hidden_role == "barao" for p in waits)
    assert pl.update([minion], [], ME, 1.0).target is minion  # sumiu de vez: mira o que está visível


# -------------------------------------------- visão: papéis em imagem sintética
def test_perception_roles_and_status_on_synthetic_frame(profiles, tmp_path):
    from ddbot.config import Config
    from ddbot.game_io import VisionBattleView
    from ddbot.capture import ArraySource
    from ddbot.vision.perception import Perception
    from ddbot.vision.templates import TemplateLibrary
    rng = np.random.default_rng(7)
    frame = np.full((600, 1000, 3), 60, np.uint8)
    tpls = {k: rng.integers(0, 255, (26, 26, 3), dtype=np.uint8) for k in ("eu", "inimigo", "rainha", "formiga")}

    def put(t, x, y):
        frame[y - 13:y + 13, x - 13:x + 13] = tpls[t]
    put("eu", 100, 400)
    put("rainha", 700, 380)
    put("inimigo", 700, 330)        # marcador genérico sobre a rainha: o mesmo inimigo
    put("formiga", 400, 400)
    put("formiga", 820, 400)
    battle = rng.integers(0, 255, (20, 60, 3), dtype=np.uint8)
    frame[5:25, 5:65] = battle
    lib = TemplateLibrary(tmp_path / "tpl")
    lib.add("estado_batalha", battle)
    lib.add("marcador_eu", tpls["eu"])
    lib.add("marcador_inimigo", tpls["inimigo"])
    lib.add("alvo_formigueiro_rainha", tpls["rainha"])
    lib.add("alvo_formigueiro_formiga", tpls["formiga"])
    per = Perception(Config(data={}), lib, tmp_path / "tpl")
    per.profile = profiles["formigueiro"]
    snap = per.analyze(frame)
    assert sorted(e.kind for e in snap.enemies) == ["formiga", "formiga", "rainha"]
    pl = StrategyPlanner(profiles["formigueiro"], has_template=lib.has)
    pl.on_battle_start()
    pl.index = 1
    view = VisionBattleView(ArraySource(frame), per, Config(data={}), planner=pl)
    obs = view.observe()
    assert obs.target_id.startswith("rainha_") and abs(obs.distance - 6.0) < 0.1 and obs.stage == "Rainha"


# ------------------------------------------------ ponta a ponta (simulação)
@pytest.mark.parametrize("key", PRIORITY)
@pytest.mark.parametrize("runs", [1, 3])
def test_instance_runs_complete_in_simulation(kb, params, profiles, key, runs):
    d = activity_from_option(f"instancia_{key}", profiles[key].name, strategy=key)
    ev = []
    r, client, eng, clock, cleanup = simulated_activity(
        kb, params, d, runs=runs, profile=profiles[key], settings=SimSettings(seed=3, max_turns=40,
                                                                              distance_range=(4.0, 12.0)),
        on_event=lambda k, m: ev.append(m))
    try:
        assert drive(r) == RunStatus.FINISHED, r.reason
        stages = len(profiles[key].stages)
        assert r.counters.completed == runs and r.counters.victories == runs
        assert r.counters.battles == runs * stages
        assert sum(f"etapa {stages}/{stages}" in m for m in ev) == runs  # chegou à última etapa em cada uma
        assert client.clicks[-1] == ("vitoria", "botao_sair")
    finally:
        cleanup()


def test_bugou_waits_for_shield_instead_of_wasting_shots(kb, params, profiles):
    d = activity_from_option("instancia_bugou_normal", "Bugou", strategy="bugou_normal")
    r, client, eng, clock, cleanup = simulated_activity(
        kb, params, d, runs=1, profile=profiles["bugou_normal"],
        settings=SimSettings(seed=5, max_turns=40, distance_range=(4.0, 12.0)))
    try:
        assert drive(r) == RunStatus.FINISHED
        world = client.world
        # nenhum disparo no Barão enquanto o escudo dele estava visível
        assert any("imune" in p.reason for p in world.plans if p.stage and p.stage.key == "barao")
        # escudo do Barão (de frente) e do Midas (só por cima): nenhum disparo anulado por eles
        assert len(world.shots_log) >= 8
        assert not any(row.get("bloqueado") for row in world.shots_log)
    finally:
        cleanup()


def test_matias_fuse_pauses_run_and_resume_finishes(kb, params, profiles):
    d = activity_from_option("instancia_bugou_normal", "Bugou", strategy="bugou_normal")
    r, client, eng, clock, cleanup = simulated_activity(
        kb, params, d, runs=1, profile=profiles["bugou_normal"], fuse_at=(3, 1),
        settings=SimSettings(seed=2, max_turns=40, distance_range=(4.0, 12.0)))
    try:
        assert drive(r) == RunStatus.PAUSED and "gelo" in r.reason
        client.world.extinguish()  # o jogador usou o gelo
        r.resume()
        assert drive_resumed(r) == RunStatus.FINISHED and r.counters.victories == 1
    finally:
        cleanup()


def test_continuous_instance_until_stopped(kb, params, profiles):
    d = activity_from_option("instancia_formigueiro", "Formigueiro", strategy="formigueiro")
    r, client, eng, clock, cleanup = simulated_activity(kb, params, d, runs=0, profile=profiles["formigueiro"],
                                                        settings=SimSettings(seed=8, max_turns=40,
                                                                             distance_range=(4.0, 12.0)))
    try:
        r.status = RunStatus.RUNNING
        for _ in range(40000):
            if not r.run_once() or r.counters.completed >= 4:
                break
        assert r.counters.completed >= 4 and r.status == RunStatus.RUNNING
        r.request_stop()
        assert r.run_once() is False and r.status == RunStatus.IDLE
    finally:
        cleanup()


def test_engine_raises_needs_attention_on_pause_reason(kb, params, tmp_path):
    from ddbot.aiming import Aimer
    from ddbot.automation.safety import KillSwitch
    from ddbot.calibration import Calibrator, ShotStore
    from ddbot.combat import BattleView, CombatEngine, Mode, Shooter
    from ddbot.config import Config
    from ddbot.tracking import TargetTracker

    class View(BattleView):
        def observe(self):
            return BattleObservation(True, True, distance=5.0, confidence=0.95, pause_reason="pavio aceso")

    class Never(Shooter):
        def shoot(self, *a):
            raise AssertionError("não pode atirar")
    store = ShotStore(tmp_path / "s.sqlite3")
    cal = Calibrator(store, params)
    eng = CombatEngine(View(), Never(), Aimer(kb, params, cal), cal, TargetTracker(), KillSwitch(),
                       Config(data={"automation": {"server_rules_confirmed": True}}))
    eng.set_mode(Mode.AUTO)
    eng.step()
    with pytest.raises(NeedsAttention):
        eng.step()
    eng.step(allow_fire=False)  # só observando: avisa, não pausa nem atira
    store.close()


def drive_resumed(runner, max_steps=40000):
    for _ in range(max_steps):
        if not runner.run_once() or runner.status == RunStatus.PAUSED:
            break
    return runner.status


# --------------------------------------------------------------- serviço
def test_service_associates_strategy_and_lists_targets(home, monkeypatch):
    from ddbot.automation.input import RecordingBackend
    from ddbot.service import BotService
    svc = BotService(home, input_backend=RecordingBackend(), start_hotkey=False)
    monkeypatch.setattr(svc, "inventory", lambda ranked=True: [])
    try:
        assert {p.key for p in svc.strategies()} == set(PRIORITY)
        d = svc.create_activity("instancia_formigueiro", "Formigueiro", "instancia", "pve")
        assert d.strategy == "formigueiro"
        assert any("estratégia Formigueiro associada" in e.message for e in svc.history)
        missing = svc.readiness(d)
        targets = [m for m in missing if m.where == "Calibração > Alvos da instância"]
        assert targets and not any(m.required for m in targets)  # recomendação, não bloqueio
        other = svc.create_activity("instancia_x", "Opção 3", "instancia", "pve")
        assert other.strategy is None
        svc.set_strategy(other, "bugou_normal")
        assert ActivityDef.from_raw(json.loads(other.path.read_text("utf-8"))).strategy == "bugou_normal"
        with pytest.raises(ValueError):
            svc.set_strategy(other, "covil_dragao")  # só pesquisa
        # demonstração da instância com estratégia: inicia, pausa, retoma, para
        ok, why = svc.start(d, 0, simulated=True)
        assert ok, why
        import time
        end = time.monotonic() + 20
        while time.monotonic() < end and not any("Formigueiro: etapa 1/2" in e.message for e in svc.history):
            time.sleep(0.2)
        assert any("Formigueiro: etapa 1/2" in e.message for e in svc.history)
        svc.pause()
        assert svc.status == RunStatus.PAUSED
        svc.resume()
        svc.stop()
        assert not svc.runner.alive
    finally:
        svc.close()


# ------------------------------------------------- regressões da revisão (0.4.0)
def test_status_applies_to_boss_seen_only_as_generic_enemy(profiles):
    """O pavio/escudo mudam a aparência: o chefe pode sair só pelo marcador genérico naquele quadro."""
    pl = planner(profiles["bugou_normal"])
    pl.on_battle_start()
    pl.index = 3
    boss = enemy(GENERIC_ROLE, 6.0)
    fuse = Character(6.0, -0.3, 0.9, "matias_pavio", "teste")
    assert pl.update([boss], [fuse], ME, 1.0).pause is None
    assert pl.update([boss], [fuse], ME, 1.0).pause  # pausa mesmo sem o papel reconhecido
    pl2 = planner(profiles["bugou_normal"])
    pl2.on_battle_start()
    pl2.index = 1
    baron = enemy(GENERIC_ROLE, 6.0)
    plan = pl2.update([baron], [Character(6.0, -0.4, 0.9, "barao_escudo", "teste")], ME, 1.0)
    assert plan.target is None and "imune" in plan.reason


def test_pause_status_needs_two_reads_not_two_hits(profiles):
    pl = planner(profiles["bugou_normal"])
    pl.on_battle_start()
    pl.index = 3
    fuses = [Character(6.0, -0.3, 0.9, "matias_pavio", "teste"), Character(6.1, -0.3, 0.9, "matias_pavio", "teste")]
    assert pl.update([enemy("matias", 6.0)], fuses, ME, 1.0).pause is None


def test_progress_survives_an_empty_frame(profiles):
    pl = planner(profiles["formigueiro"])
    pl.on_battle_start()
    pl.update([], [], ME, 1.0)  # quadro de explosão sem inimigos
    ants = [enemy("formiga", 3.0 + i) for i in range(8)]
    for n in range(8, 1, -1):  # uma formiga a menos a cada 2 disparos
        for _ in range(5):
            pl.update(ants[:n], [], ME, 1.0)
        assert pl.on_shot() is None and pl.on_shot() is None, n


def test_auto_fire_no_progress_pauses_and_resume_does_not_double_fire(kb, params, profiles, tmp_path):
    from ddbot.aiming import Aimer
    from ddbot.automation.safety import KillSwitch
    from ddbot.calibration import Calibrator, ShotStore
    from ddbot.combat import BattleView, CombatEngine, Mode, Shooter, ShotOutcome
    from ddbot.config import Config
    from ddbot.tracking import TargetTracker

    class View(BattleView):
        def observe(self):
            return BattleObservation(True, True, distance=6.0, wind=0.0, confidence=0.95, me_x=0.0, target_x=6.0,
                                     target_y=0.0)

    class Count(Shooter):
        shots = 0

        def shoot(self, *a):
            Count.shots += 1
            return ShotOutcome()
    pl = planner(profiles["formigueiro"])
    pl.on_battle_start()
    pl._shots = pl.stage.max_shots - 1
    store = ShotStore(tmp_path / "s.sqlite3")
    cal = Calibrator(store, params)
    eng = CombatEngine(View(), Count(), Aimer(kb, params, cal), cal, TargetTracker(), KillSwitch(),
                       Config(data={"automation": {"server_rules_confirmed": True, "min_seconds_between_shots": 0,
                                                   "post_shot_wait_s": 0},
                                    "thresholds": {"auto_min_hit_probability": 0.0}}))
    eng.planner = pl
    eng.set_mode(Mode.AUTO)
    eng.step()
    with pytest.raises(NeedsAttention):
        eng.step()
    assert Count.shots == 1
    for _ in range(3):  # retomado, ainda no mesmo turno: nada de segundo disparo
        eng.step()
    assert Count.shots == 1
    store.close()
