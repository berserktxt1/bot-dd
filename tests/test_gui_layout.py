"""Layout da interface em 1080p a 100%, 125% e 150% de escala, pela mesma auditoria das capturas.

Precisa de tkinter e de uma tela de 1920×1080 ou maior (Windows, ou Linux com Xvfb
``-screen 0 1920x1080x24``); numa tela menor a janela teria outro tamanho e o teste é pulado.
A escala é simulada com DDBOT_UI_SCALE, como nas capturas da CI.
"""
import os
import sys

import pytest

from ddbot import winapi

tk = pytest.importorskip("tkinter")
if sys.platform != "win32" and not os.environ.get("DISPLAY"):
    pytest.skip("sem display", allow_module_level=True)

# como o app, o processo se declara ciente da escala do Windows (winapi) antes do primeiro Tk: senão, numa tela em
# 125%, o Tk vê a tela "virtual" de 1536×864 e os testes de 1080p são pulados (diagnóstico 39527994935)
DPI_AWARE = winapi.IS_WINDOWS

PAGES = ["Pendências", "Regiões", "Modelos", "Números", "Menu", "Alvos"]
COMBAT_TEXT = "Etapa Formigas. Alvo a 11,1 de distância, altura -0,6. Modelo físico, chance estimada 79%."


def test_audit_finds_squeezed_tabs_clipped_panels_and_lists_without_rows(tk_cleanup):
    """Antes a auditoria só via texto cortado e o que saía da janela: os defeitos abaixo passavam."""
    from tkinter import ttk

    from ddbot.gui.screenshots import audit_layout
    root = tk.Tk()
    tk_cleanup(root)
    try:
        root.geometry("1000x240+0+0")
        nb = ttk.Notebook(root)
        for name in PAGES:
            nb.add(ttk.Frame(nb), text=name)
        nb.place(x=0, y=0, width=200, height=60)  # seis abas em 200 px: o Tk espreme os nomes
        box = ttk.Frame(root)
        box.place(x=0, y=100, width=320, height=60)
        ttk.Frame(box).place(x=0, y=0, width=320, height=100)  # passa da borda de baixo do painel
        tree = ttk.Treeview(root, columns=("a",), show="headings")
        tree.place(x=400, y=100, width=320, height=40)  # cabeçalho e menos de duas linhas
        root.update()
        kinds = {p["tipo"] for p in audit_layout(root)}
        assert {"abas cortadas", "cortado", "lista sem espaço"} <= kinds
        nb.place_configure(width=960)
        box.place_configure(height=110)
        tree.place_forget()
        root.update()
        assert not {"abas cortadas", "cortado", "lista sem espaço"} & {p["tipo"] for p in audit_layout(root)}
    finally:
        root.destroy()


@pytest.fixture
def app_at(tk_cleanup, home, monkeypatch):
    made = []

    def build(scale: str):
        monkeypatch.setenv("DDBOT_HEADLESS", "1")
        monkeypatch.setenv("DDBOT_UI_SCALE", scale)
        from ddbot.gui.main_window import MainWindow
        from ddbot.service import BotService
        root = tk.Tk()
        tk_cleanup(root)  # vivo até o fim do processo: liberar o Tk no meio da sessão derruba o Windows
        if root.winfo_screenwidth() < 1920 or root.winfo_screenheight() < 1080:
            root.destroy()
            pytest.skip("o layout é conferido numa tela de 1920×1080 (no Linux: Xvfb -screen 0 1920x1080x24)")
        svc = BotService(home, start_hotkey=False)
        monkeypatch.setattr(svc, "inventory", lambda ranked=True: [])  # a área de trabalho real não entra
        win = MainWindow(root, svc)
        tk_cleanup(win)
        made.append((win, svc, root))
        root.update()
        return win

    yield build
    for win, svc, root in made:
        win._closing = True
        svc.close()
        root.destroy()


@pytest.mark.parametrize("scale", ["1.0", "1.25", "1.5"])
def test_interface_fits_1080p_at_each_scale(app_at, scale):
    """Regressão das capturas do Windows (Segoe UI) na 0.5.0: as seis páginas da Calibração eram abas
    espremidas ("Pendênc", "Regiõ", "Mer") em todas as escalas e, em 150%, o Histórico do Início ficava sem
    nenhuma linha visível; a lista dos disparos registrados (aba Mira) mostrava menos de uma linha."""
    from ddbot.gui.screenshots import audit_layout
    app = app_at(scale)
    root = app.root
    found = {}  # junta tudo antes de reprovar: a CI do Windows mostra todos os problemas de uma vez

    def audit(where):
        root.update_idletasks()
        root.update()
        problems = audit_layout(root)
        if problems:
            found[where] = problems

    app.nb.select(app.tab_home)
    audit("Início sem jogo")  # com "Falta calibrar" e os atalhos de pendências
    app.simulated.set(True)
    app._toggle_demo()
    audit("Início no modo demonstração")
    app._update_status = lambda: None  # a atualização periódica apagaria os números da mira
    app.ro_angle.set("74")
    app.ro_force.set("82,6")
    app.ro_wind.set("-1,6")
    app.lbl_target.configure(text=COMBAT_TEXT)  # duas linhas: o painel Andamento fica mais alto
    audit("Início em combate")
    app.btn_confirm_warning.grid(row=7, column=0, sticky="w", pady=(app.th.px(8), 0))  # pausa no aviso difícil
    audit("Início pausado no aviso de instância difícil")
    app.btn_confirm_warning.grid_remove()
    for tab in (app.tab_diag, app.tab_aim, app.tab_cfg, app.tab_log):
        app.nb.select(tab)
        if tab is app.tab_aim:
            app.calc_aim()
        audit(app.nb.tab(tab, "text"))
    app.nb.select(app.tab_calib)
    for page in app.calib_nb.tabs():
        app.calib_nb.select(page)
        audit(f"Calibração > {app.calib_nb.tab(page, 'text')}")
        assert app.calib_page.get() == page  # o seletor acompanha a página aberta pelo código
    assert [b.cget("text") for b in app.calib_page_buttons] == PAGES
    assert not found, f"layout em {scale} (janela {root.winfo_geometry()}, compacta={app.compact}): {found}"


def test_calibration_page_buttons_open_their_pages(app_at):
    app = app_at("1.0")
    app.nb.select(app.tab_calib)
    app.root.update()
    for button, page in zip(app.calib_page_buttons, app.calib_nb.tabs()):
        button.invoke()
        app.root.update()
        assert app.calib_nb.select() == page and app.calib_page.get() == page
    app._goto_pending()  # "Ver pendências" no Início
    app.root.update()
    assert app.calib_nb.select() == str(app.page_pending) == app.calib_page.get()
