"""Interface: atividades pré-cadastradas no Início, seleção da janela sem camada escura e fonte dos ícones.

Precisa de tkinter e de uma tela (Windows ou Linux com Xvfb). As consultas ao Windows (mouse, janela
sob o ponto) são simuladas: nenhuma janela de verdade é escolhida.
"""
import inspect
import os
import sys

import pytest

tk = pytest.importorskip("tkinter")
if sys.platform != "win32" and not os.environ.get("DISPLAY"):
    pytest.skip("sem display", allow_module_level=True)

SIX = ["formigueiro_facil", "formigueiro_normal", "galinheiro_facil", "galinheiro_normal", "galinheiro_dificil",
       "olimpiadas_bugou_normal"]


@pytest.fixture
def app(tk_cleanup, home, monkeypatch):
    monkeypatch.setenv("DDBOT_HEADLESS", "1")
    from ddbot.gui.main_window import MainWindow
    from ddbot.service import BotService
    svc = BotService(home, start_hotkey=False)
    monkeypatch.setattr(svc, "inventory", lambda ranked=True: [])  # a área de trabalho real não entra
    root = tk.Tk()
    tk_cleanup(root)  # vivo até o fim do processo: liberar o Tk no meio da sessão derruba o Windows
    win = MainWindow(root, svc)
    tk_cleanup(win)
    root.update()
    yield win
    win._closing = True
    svc.close()
    root.destroy()


def test_home_lists_the_six_instances_before_connecting(app):
    kids = list(app.tree_act.get_children("sec_instancia"))
    assert kids[:6] == SIX and app.svc.window is None
    names = [app.tree_act.item(k, "text") for k in kids]
    assert names[5] == "Olimpíadas Bugou — Normal" and not any("Castelo" in n for n in names)
    assert app.tree_act.exists("sec_partida")
    app.tree_act.selection_set("galinheiro_dificil")
    app.root.update()
    assert app.selected_activity().key == "galinheiro_dificil"
    assert "Galinheiro — Difícil" == app.lbl_act_title.cget("text")
    assert "Falta calibrar" in app.lbl_ready.cget("text")  # pendências visíveis antes de jogar
    assert app.btn_start.instate(["disabled"])  # sem o jogo e sem calibração, não inicia no jogo real


def test_pending_page_explains_each_item(app):
    app.tree_act.selection_set("olimpiadas_bugou_normal")
    app.root.update()
    app._goto_pending()
    app.root.update()
    assert app.calib_nb.select() == str(app.page_pending)
    assert app._pending and app._pending[0].required
    text = app.lbl_pending.cget("text")
    assert "Capturar tela do jogo" in text or "capture" in text.lower()


def test_banner_icon_uses_a_font_with_the_glyphs(app):
    from ddbot.gui import theme as T
    icon_font = app.th.fonts["icon"]
    assert app.banner.icon.cget("font") == str(icon_font)
    assert icon_font.actual()["family"] in T.ICON_FAMILIES or icon_font.actual()["family"]


def test_pointer_pick_has_no_dark_overlay_and_picks_the_window_under_the_mouse(app, monkeypatch):
    from ddbot.gui import detect_dialog as dd
    from ddbot.winapi import WindowInfo
    src = inspect.getsource(dd)
    assert "PickOverlay" not in src and '"-alpha"' not in src and "virtual_screen" not in src
    own = dd.winapi.own_pid()
    toast_win = WindowInfo(9, "JonFlow", 0, 0, 400, 120, pid=own, exe="JonFlow.exe")
    game = WindowInfo(500, "Jogo", 100, 100, 800, 600, pid=77, exe="cliente.exe")
    under = {"hwnd": 9}
    monkeypatch.setattr(dd.winapi, "cursor_pos", lambda: (400, 300))
    monkeypatch.setattr(dd.winapi, "window_at", lambda x, y: under["hwnd"])
    monkeypatch.setattr(dd.winapi, "root_of", lambda h: h)
    clock = [0.0]
    got = []
    toast = dd.PointerToast(app, [toast_win, game], got.append, now=lambda: clock[0])
    app.root.update()
    sw, sh = toast.winfo_screenwidth(), toast.winfo_screenheight()
    assert toast.winfo_width() * toast.winfo_height() < 0.08 * sw * sh  # um aviso pequeno, não uma camada
    clock[0] = 3.5
    toast._tick()  # o mouse estava sobre o próprio aviso: conta de novo, não escolhe
    assert got == [] and "sobre este aviso" in toast.text.cget("text")
    under["hwnd"] = 500
    clock[0] = 8.0
    toast._tick()
    assert got == [game]


def test_point_pick_hides_the_dialog_and_brings_it_back_to_confirm(app, monkeypatch):
    from ddbot.gui import detect_dialog as dd
    from ddbot.winapi import WindowInfo
    created = []

    class FakeToast:
        def __init__(self, app_, windows, on_done):
            created.append(on_done)

        def cancel(self, notify=True):
            pass
    monkeypatch.setattr(dd, "PointerToast", FakeToast)
    dlg = dd.DetectDialog(app, app.svc, hide_main=False)
    app.root.update()
    dlg.start_point()
    app.root.update()
    assert dlg.state() == "withdrawn" and created
    game = WindowInfo(500, "Jogo", 100, 100, 800, 600, pid=77, exe="cliente.exe")
    created[0](game)
    app.root.update()
    assert dlg.state() == "normal" and dlg.mode == "confirmar" and dlg.shown is game
    dlg.close()
