"""Jogo aberto por um launcher: identificar a janela certa e nunca mandar comandos ao launcher."""
import pytest

from ddbot.automation.input import InputController, RecordingBackend
from ddbot.automation.safety import FocusLost, KillSwitch
from ddbot.game_window import (GAME, LAUNCHER_ONLY, GameWindowProfile, WindowRule, keyboard_ok, rank_candidates,
                               validate_choice)
from ddbot.winapi import WindowInfo


def win(hwnd, exe, cls="", title="", w=1000, h=600, parent=0, left=0, top=0):
    return WindowInfo(hwnd, title, left, top, w, h, pid=hwnd * 10, exe=exe, cls=cls, parent=parent)


LAUNCHER = win(100, "LauncherX.exe", "LauncherWnd", "Launcher", 1280, 760)
LAUNCHER_PANEL = win(101, "LauncherX.exe", "PanelHost", "", 1280, 700, parent=100)  # área interna sem jogo
SEPARATE_GAME = win(200, "ClienteJogo.exe", "GameWnd", "Algum título", 1000, 600)
EMBEDDED_GAME = win(102, "LauncherX.exe", "RenderArea", "", 1000, 600, parent=100)


def profile(game_rule, launcher_rule=WindowRule("LauncherX.exe", "LauncherWnd")):
    return GameWindowProfile(game_rule, launcher_rule)


def test_rule_matching_main_vs_child():
    # a regra do jogo embutido não pode casar com a janela principal do launcher (mesmo programa)
    rule = WindowRule("LauncherX.exe", "", child=True)
    assert not rule.matches(LAUNCHER) and rule.matches(EMBEDDED_GAME)


def test_wizard_choice_validation():
    assert validate_choice(LAUNCHER, LAUNCHER)  # a mesma janela
    twin = win(150, "LauncherX.exe", "LauncherWnd", w=1280, h=760)
    assert "área interna" in validate_choice(twin, LAUNCHER)
    assert validate_choice(win(5, "x.exe", w=150, h=100), None)  # pequena demais
    assert validate_choice(EMBEDDED_GAME, LAUNCHER) is None
    assert validate_choice(SEPARATE_GAME, LAUNCHER) is None


def test_candidates_ranked_by_keyword_then_size():
    ranked = rank_candidates([win(1, "editor.exe", title="Notas", w=1900, h=1000), SEPARATE_GAME,
                              win(2, "x.exe", title="DDTank - cliente", w=800, h=600)], ["DDTank"])
    assert ranked[0].hwnd == 2


# ------------------------------------------------------------- foco do teclado
ROOTS = {100: 100, 101: 100, 102: 100, 103: 100, 200: 200, 201: 200, 999: 999}
CHILDREN = {102: {102}, 200: {200, 201}}


def root_of(h):
    return ROOTS.get(h, h)


def contains(target, h):
    return h in CHILDREN.get(target, {target})


def test_keys_refused_when_focus_on_launcher_button():
    # jogo embutido (102) no launcher (100); o foco está num botão do launcher (103)
    ok, why = keyboard_ok(102, True, foreground=100, focus=103, root_of=root_of, contains=contains)
    assert not ok and "launcher" in why
    assert keyboard_ok(102, True, foreground=100, focus=102, root_of=root_of, contains=contains)[0]


def test_keys_refused_when_other_app_in_front():
    assert not keyboard_ok(200, False, foreground=999, focus=999, root_of=root_of, contains=contains)[0]
    assert not keyboard_ok(200, False, foreground=100, focus=100, root_of=root_of, contains=contains)[0]  # launcher
    assert keyboard_ok(200, False, foreground=200, focus=201, root_of=root_of, contains=contains)[0]


def test_input_controller_blocks_keys_but_not_clicks_without_keyboard_focus():
    be = RecordingBackend()
    inp = InputController(KillSwitch(), be, foreground_check=lambda: True, key_focus_check=lambda: False,
                          key_delay_s=0.001)
    with pytest.raises(FocusLost):
        inp.tap("up")
    assert not any(e[0] == "key" for e in be.events)
    inp.click(10, 10)  # o clique dentro do jogo é o que devolve o foco a ele
    assert ("click", 10, 10) in be.events


def test_click_over_launcher_button_refused(tmp_path):
    """Jogo embutido: o botão do launcher tem a mesma janela principal, mas não é a área do jogo."""
    from ddbot.game_io import GameActor
    from test_integration import build
    game, cfg, lib, per, kill, inp, view, store = build(tmp_path)

    class Info:
        left, top, width, height = 500, 300, 1000, 600
        parent = 100
    game.info = Info()
    game.hwnd = 102
    point_owner = {"hwnd": 103}  # um botão do launcher por cima do ponto
    actor = GameActor(inp, game, lib, cfg, window_at=lambda x, y: point_owner["hwnd"], contains=contains)
    frame = game.grab()
    assert actor.click("botao_iniciar", frame) is False
    point_owner["hwnd"] = 102
    assert actor.click("botao_iniciar", frame) is True
    store.close()


# ------------------------------------------------------------------- serviço
@pytest.fixture
def svc(home):
    from ddbot.service import BotService
    s = BotService(home, start_hotkey=False)
    s.config.set("window.profile", profile(WindowRule("ClienteJogo.exe", "GameWnd")).to_dict())
    s.config.set("automation.server_rules_confirmed", True)
    yield s
    s.close()


def test_start_refused_while_launcher_has_no_game(svc):
    from ddbot.activities import activity_from_option
    svc.inventory = lambda: [LAUNCHER, LAUNCHER_PANEL]
    ok, why = svc.start(activity_from_option("instancia_x", "X"), 1, simulated=False)
    assert not ok and "launcher está aberto" in why


def test_auto_connect_when_game_appears(svc):
    windows = [LAUNCHER]
    svc.inventory = lambda: list(windows)
    assert svc.auto_connect().state == LAUNCHER_ONLY and svc.window is None
    windows.append(SEPARATE_GAME)
    found = svc.auto_connect()
    assert found.state == GAME and svc.window.hwnd == 200 and svc.source.hwnd == 200


def test_confirm_rejects_launcher_as_game(svc):
    assert svc.confirm_game(LAUNCHER, LAUNCHER)
    assert svc.confirm_game(EMBEDDED_GAME, LAUNCHER) is None
    assert svc.profile.game.child and svc.profile.game.cls == "RenderArea"
    assert svc.window.hwnd == EMBEDDED_GAME.hwnd


def test_launcher_panel_not_taken_as_game_after_confirmation(svc):
    """Com o jogo confirmado em outro programa, a área interna do launcher não vira o jogo."""
    svc.inventory = lambda: [LAUNCHER, LAUNCHER_PANEL]
    found = svc.auto_connect()
    assert found.state == LAUNCHER_ONLY and svc.window is None


def test_mark_launcher_then_wait(svc):
    svc.config.set("window.profile", {})
    svc.inventory = lambda: [LAUNCHER]
    svc.mark_launcher(LAUNCHER)
    assert svc.profile.launcher.exe == "LauncherX.exe" and svc.profile.game is None
    assert svc.auto_connect().state == LAUNCHER_ONLY


def test_resume_rebinds_when_game_reopened(svc, monkeypatch):
    from ddbot import winapi
    from ddbot.activities import activity_from_option
    svc.inventory = lambda: [LAUNCHER, SEPARATE_GAME]
    svc.auto_connect()
    assert svc.start(activity_from_option("instancia_teste", "T"), 0, simulated=True)[0]
    svc.simulated = False  # o caminho de reconexão vale para a rotina real
    svc.runner.pause()
    reopened = win(250, "ClienteJogo.exe", "GameWnd", w=1000, h=600)
    svc.inventory = lambda: [LAUNCHER, reopened]
    monkeypatch.setattr(winapi, "window_info", lambda h: None)  # a janela antiga sumiu
    svc.resume()
    assert svc.source.hwnd == 250
    svc.stop()


def test_banner_launcher_waiting():
    from ddbot.gui.states import UiSnapshot, describe
    b = describe(UiSnapshot(has_window=False, demo=False, activity_name="X", window_state=LAUNCHER_ONLY))
    assert "aguardando o jogo" in b.title
    b = describe(UiSnapshot(has_window=False, demo=False, activity_name="X", window_state="nada"))
    assert "Detectar jogo" in b.detail


def test_profile_roundtrip(tmp_path):
    from ddbot.config import Config
    c = Config(tmp_path / "config.json")
    p = profile(WindowRule("LauncherX.exe", "RenderArea", child=True))
    c.set("window.profile", p.to_dict())
    c.save()
    assert GameWindowProfile.from_config(Config(tmp_path / "config.json")) == p
