"""Fluxo das expedições pelo Cais (log do usuário de 2026-10-21).

Passo a passo informado pelo usuário: Lobby > Central (Cais de Expedição) > Jogar > selecionar a instância >
Formigueiro > dificuldade Normal > OK > Início > OK no lembrete > a batalha começa. No log, depois do clique em
Formigueiro a janela de escolha passou a ser lida como "Escolha da instância 0,75, Derrota 0,56, Sala/preparação
0,49 (mínimo 0,80)": o bot tratava a janela como tela desconhecida, nunca clicava na dificuldade e pausava em 20 s.

Tudo aqui é simulação (``SimulatedClient``): prova a lógica do fluxo, não o funcionamento no DDClássico.
"""
from pathlib import Path

import pytest

from ddbot.activities import (ActivityRunner, RunLimits, RunStatus, ScreenState, activity_from_option)
from ddbot.automation.safety import KillSwitch
from ddbot.catalog import build_activity, load_catalog
from ddbot.config import Config
from ddbot.readiness import check
from ddbot.simulation import FakeClock, SimSettings, drive, simulated_activity
from ddbot.strategy import load_profiles

ROOT = Path(__file__).resolve().parents[1]
CATALOG, _ = load_catalog(ROOT / "data" / "knowledge" / "catalogo.json")
PROFILES, _ = load_profiles(ROOT / "data" / "knowledge" / "instances.json")
NAV = ("lobby", "cais_expedicao", "sala", "menu_instancias", "aviso_sozinho")


class Run:
    """Atividade do catálogo no cliente simulado, com a escolha como no DDClássico (janela que muda e OK)."""

    def __init__(self, kb, params, key="formigueiro_normal", runs=1, faults=None, solo_ok=True, real=True):
        e = CATALOG.get(key)
        self.entry, self.d = e, build_activity(e, CATALOG)
        overrides = {"instances": {"confirm_solo_warning": True}} if solo_ok else None
        self.r, self.c, _, self.clock, self.cleanup = simulated_activity(
            kb, params, self.d, runs=runs, profile=PROFILES[e.strategy], faults=faults, config_overrides=overrides,
            settings=SimSettings(seed=4, max_turns=40, distance_range=(4.0, 12.0)))
        self.c.confirm_choice = self.c.dialog_changes = real
        self.events = []  # (instante, evento)
        self.r.on_event = lambda ev: self.events.append((self.clock(), ev))

    def drive(self, steps=20000):
        try:
            return drive(self.r, steps)
        finally:
            self.cleanup()

    @property
    def option(self):
        return self.entry.option

    @property
    def difficulty(self):
        return CATALOG.difficulties[self.entry.difficulty].template

    def nav(self):
        return [(s, t) for s, t in self.c.clicks if s in NAV]

    def when(self, text):
        return next(t for t, ev in self.events if text in ev.message)

    def messages(self):
        return [ev.message for _, ev in self.events]


def expected_path(option, difficulty):
    return [("lobby", "botao_cais"), ("cais_expedicao", "botao_criar_sala"), ("sala", "botao_escolher_instancia"),
            ("menu_instancias", option), ("menu_instancias", difficulty), ("menu_instancias", "botao_confirmar"),
            ("sala", "botao_iniciar"), ("aviso_sozinho", "botao_confirmar_aviso")]


# ------------------------------------------------------------- caminho completo
@pytest.mark.parametrize("key", ["formigueiro_normal", "formigueiro_facil", "galinheiro_dificil"])
def test_dock_flow_follows_the_user_steps_with_the_chosen_difficulty(kb, params, key):
    """Lobby -> Central -> Jogar -> escolher a instância -> instância -> dificuldade -> OK -> Início -> lembrete."""
    run = Run(kb, params, key, faults={"solo_warning": True})
    assert run.drive() == RunStatus.FINISHED, run.r.reason
    assert run.nav() == expected_path(run.option, run.difficulty)
    assert run.c.started_with == [[run.option, run.difficulty]]  # a sala iniciou com a dificuldade escolhida
    other = {t for _, t in run.c.clicks if t.startswith("dificuldade_")} - {run.difficulty}
    assert not other  # nenhuma outra dificuldade foi clicada
    assert run.r.counters.battles >= 1 and run.r.counters.completed == 1
    assert all(a != b for a, b in zip(run.nav(), run.nav()[1:]))  # nenhum clique repetido até a batalha
    assert not [m for m in run.messages() if "intervenção" in m]


def test_log_scenario_changed_dialog_is_followed_by_context(kb, params):
    """Regressão do log: a janela lida a 0,75 depois do clique na instância segue pela dificuldade e pelo OK."""
    run = Run(kb, params, "formigueiro_normal")
    assert run.drive() == RunStatus.FINISHED, run.r.reason
    ctx = [m for m in run.messages() if "reconhecida pelo contexto" in m]
    assert ctx and "semelhança 0,75 (mínimo 0,80)" in ctx[0] and "dificuldade_normal visível" in ctx[0]
    assert [t for _, t in run.c.clicks].count("instancia_formigueiro") == 1  # sem clicar de novo na instância
    assert not [m for m in run.messages() if "tela não reconhecida" in m]
    # a escolha é confirmada pela mudança de tela, com o tempo de cada passagem no Histórico
    assert any(m.startswith("tela: sala") and "confirmado o clique em botao_confirmar" in m for m in run.messages())


def test_captured_difficulty_screen_keeps_what_was_chosen(kb, params):
    """Com a "Tela: Escolha da dificuldade" capturada, a janela vira menu_dificuldade e a instância não é refeita."""
    run = Run(kb, params, "formigueiro_normal", real=False)
    run.c.confirm_choice = run.c.difficulty_screen = True
    assert run.drive() == RunStatus.FINISHED, run.r.reason
    assert "tela: menu_dificuldade" in [m.split(":")[0] + ": " + m.split(": ")[1].split()[0] for m in run.messages()
                                        if m.startswith("tela: ")]
    assert [t for _, t in run.c.clicks].count("instancia_formigueiro") == 1
    assert run.c.started_with == [["instancia_formigueiro", "dificuldade_normal"]]


def test_return_to_room_after_ok_clicks_start_and_each_run_chooses_again(kb, params):
    """Depois do OK a sala volta com a instância: o bot clica em Início, não em escolher a instância de novo."""
    run = Run(kb, params, "formigueiro_normal", runs=2)
    run.c.back_to_room = True
    assert run.drive() == RunStatus.FINISHED, run.r.reason
    choose = expected_path(run.option, run.difficulty)[2:7]
    assert run.nav() == expected_path(run.option, run.difficulty)[:2] + choose + choose
    assert run.c.started_with == [["instancia_formigueiro", "dificuldade_normal"]] * 2


def test_ok_is_never_clicked_without_the_difficulty(kb, params):
    """A dificuldade não aparece na janela mudada: pausa sem clicar em OK (que iniciaria a padrão) nem no X."""
    run = Run(kb, params, "formigueiro_normal", faults={"menu_hides": ["dificuldade_normal"]})
    assert run.drive(5000) == RunStatus.PAUSED
    clicked = [t for _, t in run.c.clicks]
    assert "botao_confirmar" not in clicked and "botao_fechar" not in clicked
    assert not [t for t in clicked if t.startswith("dificuldade_")]
    assert run.c.started_with == [] and run.c.screen == "menu_instancias"
    reason = run.r.reason
    assert "janela de escolha da instância mudou depois do clique em instancia_formigueiro" in reason
    assert "dificuldade_normal não foi encontrado" in reason and "Escolha da dificuldade" in reason
    # pausa no limite curto da navegação (10 s), não nos 20 s de antes
    assert run.when("intervenção") - run.when("clicou em instancia_formigueiro") <= 12


def test_menu_without_the_difficulty_never_confirms(kb, params):
    """Janela que não muda (dificuldade ausente do menu): pausa na escolha, sem OK nem outra dificuldade."""
    run = Run(kb, params, "galinheiro_dificil", faults={"menu_hides": ["dificuldade_dificil"]}, real=False)
    run.c.confirm_choice = True
    assert run.drive(5000) == RunStatus.PAUSED
    assert "a dificuldade" in run.r.reason and "não escolhe outra atividade" in run.r.reason
    assert [t for s, t in run.c.clicks if s == "menu_instancias"] == ["instancia_galinheiro"]


# ------------------------------------------------- transições demoradas e tempo
def test_slow_transition_waits_without_repeating_the_click(kb, params):
    """O Cais e a sala demoram a aparecer (tela desconhecida por alguns segundos): o clique não é repetido."""
    run = Run(kb, params, faults={"solo_warning": True,
                                  "transition": {"botao_cais": (12, 0.3), "botao_criar_sala": (30, 0.3)}})
    assert run.drive() == RunStatus.FINISHED, run.r.reason
    clicked = [t for _, t in run.c.clicks]
    assert clicked.count("botao_cais") == 1 and clicked.count("botao_criar_sala") == 1
    assert run.nav() == expected_path(run.option, run.difficulty)


def test_weak_screen_with_the_expected_button_is_accepted_by_context(kb, params):
    """No log a sala e o Cais ficaram em 0,75-0,78 por até 15 s: com o botão esperado visível, o bot segue."""
    run = Run(kb, params, faults={"solo_warning": True, "transition": {"botao_criar_sala": (10 ** 6, 0.77)}})
    assert run.drive() == RunStatus.FINISHED, run.r.reason
    assert any("a tela sala reconhecida pelo contexto" in m for m in run.messages())
    assert run.when("clicou em botao_escolher_instancia") - run.when("clicou em botao_criar_sala") < 3


def test_weak_screen_without_the_button_pauses_without_clicking(kb, params):
    run = Run(kb, params, faults={"transition": {"botao_criar_sala": (10 ** 6, 0.77)},
                                  "missing_button": "botao_escolher_instancia"})
    assert run.drive(5000) == RunStatus.PAUSED
    assert "desconhecida" in run.r.reason
    assert [s for s, _ in run.c.clicks if s == "sala"] == []
    assert run.when("intervenção") - run.when("clicou em botao_criar_sala") <= 12


def test_loading_after_start_keeps_the_longer_limit(kb, params):
    """Depois de Início o jogo carrega a batalha: tela desconhecida ali só pausa no limite configurado (20 s)."""
    run = Run(kb, params, faults={"transition": {"botao_iniciar": (10 ** 6, 0.3)}})
    assert run.drive(5000) == RunStatus.PAUSED and "desconhecida" in run.r.reason
    waited = run.when("intervenção") - run.when("clicou em botao_iniciar")
    assert 19 <= waited <= 23


def test_navigation_until_the_battle_is_fast(kb, params):
    """Do lobby à batalha, sem esperas fixas longas: cada passagem é conferida em leituras curtas."""
    run = Run(kb, params, real=False)  # o mesmo cliente simulado da 0.5.2: 9,9 s até a batalha nela
    assert run.drive() == RunStatus.FINISHED, run.r.reason
    assert run.when("tela: batalha") - run.r.counters.started_at < 8  # 6,5 s agora
    run = Run(kb, params, faults={"solo_warning": True})  # com o OK e o lembrete
    assert run.drive() == RunStatus.FINISHED, run.r.reason
    assert run.when("tela: batalha") - run.r.counters.started_at < 10


# --------------------------------------------------------------- sala já escolhida
def test_room_with_an_instance_already_chosen_pauses_with_a_clear_reason(kb, params):
    """Retomar numa sala que já tem instância (o botão de escolher muda): o bot não inicia sem escolher ele mesmo."""
    run = Run(kb, params, faults={"choice_button_changes": True})
    run.c.screen, run.c.room_choice = "sala", ["instancia_formigueiro", "dificuldade_facil"]
    assert run.drive(5000) == RunStatus.PAUSED
    assert "já parece ter uma instância escolhida" in run.r.reason and "mais uma amostra" in run.r.reason
    assert run.c.clicks == [] and run.c.started_with == []
    assert run.when("intervenção") - run.when("tela: sala") <= 13


# ------------------------------------------------- reconhecimento pelo contexto
class Script:
    """Leitor e ator de teste: devolve as leituras na ordem (a última se repete) e registra os cliques."""

    def __init__(self, reads, visible=True):
        self.reads, self.clicks, self.show = list(reads), [], visible

    def read(self):
        return self.reads.pop(0) if len(self.reads) > 1 else self.reads[0]

    def click(self, template, frame=None):
        self.clicks.append(template)
        return True

    def visible(self, template, frame=None):
        return self.show

    def press(self, key):
        pass


def scripted(reads, visible=True, steps=60):
    d = activity_from_option("instancia_x", "X")
    io = Script(reads, visible)
    clock = FakeClock()
    r = ActivityRunner(d, io, io, lambda allow_fire=True: None, KillSwitch(),
                       Config(data={"automation": {"server_rules_confirmed": True}}), RunLimits(), clock=clock)
    r._sleep = lambda s: clock.advance(max(s, 0.05))
    r.status = RunStatus.RUNNING
    for _ in range(steps):
        if not r.run_once() or r.status == RunStatus.PAUSED:
            break
    return r, io


CAIS = [ScreenState("cais_expedicao", 0.95)] * 2


def weak(**scores):
    return ScreenState("desconhecido", max(scores.values()), scores=scores)


@pytest.mark.parametrize("reads,why", [
    ([ScreenState("lobby", 0.95)] * 2 + [weak(sala=0.77, derrota=0.5)], "a sala não vem direto do lobby"),
    (CAIS + [weak(derrota=0.77, sala=0.4)], "derrota nunca é aceita pelo contexto"),
    (CAIS + [weak(sala=0.77, derrota=0.72)], "sem folga sobre a segunda mais parecida"),
    (CAIS + [weak(sala=0.6, derrota=0.3)], "semelhança baixa demais"),
])
def test_context_never_accepts_a_doubtful_screen(reads, why):
    r, io = scripted(reads)
    assert "botao_escolher_instancia" not in io.clicks, why
    assert r.current_state in ("lobby", "cais_expedicao"), why


def test_context_needs_the_button_on_screen():
    r, io = scripted(CAIS + [weak(sala=0.77, derrota=0.5)], visible=False)
    assert "botao_escolher_instancia" not in io.clicks and r.current_state == "cais_expedicao"
    r, io = scripted(CAIS + [weak(sala=0.77, derrota=0.5)], visible=True)
    assert io.clicks[:2] == ["botao_criar_sala", "botao_escolher_instancia"] and r.current_state == "sala"


def test_global_threshold_is_unchanged():
    """O mínimo geral continua 0,80: fora do contexto, 0,79 é tela desconhecida."""
    r, io = scripted([ScreenState("lobby", 0.79)], steps=10)
    assert io.clicks == [] and r.unknown_screen


# ------------------------------------------------------------------ calibração
def test_difficulty_screen_is_optional_and_ok_is_required():
    d = build_activity(CATALOG.get("formigueiro_normal"), CATALOG)
    assert d.flow["menu_dificuldade"] == d.flow["menu_instancias"]
    missing = {m.key: m for m in check(d, lambda name: False, Config(data={}), True, True)}
    assert not missing["estado_menu_dificuldade"].required
    assert "depois de clicar na instância" in missing["estado_menu_dificuldade"].how
    assert missing["botao_confirmar"].required


def test_old_user_flow_without_difficulty_screen_uses_the_choice_actions():
    """Definições salvas antes (instancias/*.json) não têm menu_dificuldade: a tela usa as ações da escolha."""
    d = activity_from_option("instancia_x", "X")
    del d.flow["menu_dificuldade"]
    r = ActivityRunner(d, None, None, None, KillSwitch(), Config(data={}), RunLimits())
    assert r._actions_for("menu_dificuldade") is d.flow["menu_instancias"]


def test_vision_reader_passes_the_scores_and_actor_checks_visibility(tmp_path):
    import numpy as np

    from ddbot.automation.input import InputController, RecordingBackend
    from ddbot.capture import ArraySource
    from ddbot.game_io import GameActor, VisionScreenReader
    from ddbot.vision.perception import Perception
    from ddbot.vision.templates import TemplateLibrary
    rng = np.random.default_rng(3)
    frame = rng.integers(0, 255, (300, 400, 3), dtype=np.uint8)
    lib = TemplateLibrary(tmp_path / "t")
    dialog = frame[40:200, 60:300].copy()
    lib.add("estado_menu_instancias", dialog)
    changed = frame.copy()
    changed[40:120, 60:300] = rng.integers(0, 255, (80, 240, 3), dtype=np.uint8)  # metade da janela mudou
    cfg = Config(data={})
    reader = VisionScreenReader(ArraySource(changed), Perception(cfg, lib, tmp_path / "g"), require_foreground=False)
    st = reader.read()
    assert st.state == "desconhecido" and st.scores["menu_instancias"] == pytest.approx(st.confidence)
    lib.add("dificuldade_normal", changed[150:190, 80:160].copy())
    actor = GameActor(InputController(KillSwitch(), RecordingBackend()), ArraySource(changed), lib, cfg,
                      window_at=lambda x, y: 1, contains=lambda a, b: True)
    assert actor.visible("dificuldade_normal", changed) and not actor.visible("dificuldade_facil", changed)
    lib.add("dificuldade_facil", changed[150:190, 80:160].copy())  # igual à normal: ambígua, não está "visível"
    assert not actor.visible("dificuldade_normal", changed)
