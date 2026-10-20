"""Detectar jogo: cenários do launcher sem nomes fixos (janelas e processos simulados)."""
from ddbot.detection import CHOOSE, GAME, LAUNCHER_ONLY, NOTHING, detect, pick_at
from ddbot.game_window import GameWindowProfile, WindowRule
from ddbot.winapi import WindowInfo

OWN = 999
EXPLORER = 4


def win(hwnd, pid, exe, title="", w=1000, h=640, parent=0, cls="Wnd"):
    return WindowInfo(hwnd, title, 0, 0, w, h, pid=pid, exe=exe, cls=cls, parent=parent)


DESKTOP = win(1, EXPLORER, "explorer.exe", "", 1920, 1080, cls="Progman")
BOT = win(2, OWN, "JonFlow.exe", "JonFlow 0.3.0", 1200, 800)
OTHER = win(3, 50, "editor.exe", "Documento - Editor", 1400, 900)
# launcher: processo 10, aberto pelo explorer; tem um painel de notícias interno pequeno
LAUNCHER = win(100, 10, "AlgumLauncher.exe", "DDTank Launcher", 1100, 680)
NEWS = win(101, 10, "AlgumLauncher.exe", "", 500, 300, parent=100, cls="Painel")
# jogo em processo próprio, aberto pelo launcher, com título que não diz nada
GAME_WIN = win(200, 20, "cliente.exe", "Janela", 1000, 600)
PARENTS = {10: EXPLORER, 20: 10, 50: EXPLORER, OWN: EXPLORER}
KW = ["DDTank", "DDClássico"]


def run(windows, parents=PARENTS, **kw):
    return detect(windows, parents, OWN, KW, **kw)


def test_launcher_open_game_not_started():
    """Launcher aberto e o jogo ainda não: só a janela do launcher, sem área de jogo."""
    p = GameWindowProfile(WindowRule("cliente.exe", "Wnd"), WindowRule("AlgumLauncher.exe", "Wnd"))
    d = run([DESKTOP, BOT, OTHER, LAUNCHER, NEWS], profile=p)
    assert d.state == LAUNCHER_ONLY and d.launcher.hwnd == 100 and d.game is None


def test_game_opened_by_launcher_in_another_process():
    d = run([DESKTOP, BOT, OTHER, LAUNCHER, NEWS, GAME_WIN])
    assert d.state == GAME and d.game.hwnd == 200 and d.launcher.hwnd == 100
    assert d.confident and not d.same_window and "aberta pelo launcher" in d.candidates[0].reasons


def test_game_in_same_window_as_launcher():
    """O launcher desenha o jogo numa área interna grande: a área é o alvo, não a janela com botões."""
    surface = win(102, 10, "AlgumLauncher.exe", "", 1060, 600, parent=100, cls="Render")
    d = run([DESKTOP, BOT, LAUNCHER, surface])
    assert d.state == GAME and d.game.hwnd == 102 and d.same_window and d.launcher.hwnd == 100


def test_nested_render_area_prefers_innermost():
    host = win(102, 10, "AlgumLauncher.exe", "", 1080, 640, parent=100, cls="Host")
    inner = win(103, 10, "AlgumLauncher.exe", "", 1060, 620, parent=102, cls="Render")
    d = run([LAUNCHER, host, inner])
    assert d.game.hwnd == 103


def test_game_in_separate_process_launcher_closed_after():
    """Launcher fechou depois de abrir o jogo: o jogo continua sendo encontrado (palavra-chave ou perfil)."""
    p = GameWindowProfile(WindowRule("cliente.exe", "Wnd"), WindowRule("AlgumLauncher.exe", "Wnd"))
    d = run([DESKTOP, OTHER, GAME_WIN], parents={20: 10, 50: EXPLORER}, profile=p)
    assert d.state == GAME and d.game.hwnd == 200 and d.launcher is None


def test_new_window_wins_during_wait():
    """Durante a espera, a janela que aparece na família do launcher é o jogo."""
    before = {1, 2, 3, 100, 101}
    late = win(201, 10, "AlgumLauncher.exe", "Outra", 1000, 600)  # mesmo processo, janela nova
    d = run([DESKTOP, BOT, LAUNCHER, NEWS, late], baseline=before,
            profile=GameWindowProfile(None, WindowRule("AlgumLauncher.exe", "Wnd")))
    assert d.state == GAME and d.game.hwnd == 201


def test_two_similar_candidates_ask_user():
    a = win(200, 20, "cliente.exe", "DDTank - conta 1", 1000, 600)
    b = win(300, 30, "cliente.exe", "DDTank - conta 2", 1000, 600)
    d = run([DESKTOP, a, b], parents={20: EXPLORER, 30: EXPLORER})
    assert d.state == CHOOSE and {c.window.hwnd for c in d.candidates} == {200, 300}


def test_saved_profile_breaks_tie():
    a = win(200, 20, "cliente.exe", "DDTank", 1000, 600, cls="GameWnd")
    b = win(300, 30, "navegador.exe", "DDTank - site oficial", 1000, 600)
    p = GameWindowProfile(WindowRule("cliente.exe", "GameWnd"))
    d = run([a, b], parents={20: EXPLORER, 30: EXPLORER}, profile=p)
    assert d.state == GAME and d.game.hwnd == 200


def test_own_window_and_unrelated_never_chosen():
    d = run([DESKTOP, BOT, OTHER])
    assert d.state == NOTHING
    bot_named = win(5, OWN, "JonFlow.exe", "JonFlow - bot para DDTank", 1200, 800)
    assert run([bot_named]).state == NOTHING


def test_rejected_surface_means_launcher_waits():
    """O usuário disse que a área interna é a página do launcher: o bot espera o jogo."""
    surface = win(102, 10, "AlgumLauncher.exe", "", 1060, 600, parent=100, cls="Render")
    d = run([LAUNCHER, surface], rejected={102})
    assert d.state == LAUNCHER_ONLY and d.launcher.hwnd == 100
    game_surface = win(104, 10, "AlgumLauncher.exe", "", 1060, 600, parent=100, cls="Render")
    d = run([LAUNCHER, game_surface], rejected={102}, baseline={100, 102})
    assert d.state == GAME and d.game.hwnd == 104 and d.same_window


def test_small_windows_ignored():
    tiny = win(200, 20, "cliente.exe", "DDTank", 300, 200)
    assert run([tiny], parents={20: EXPLORER}).state == LAUNCHER_ONLY


def test_launcher_with_large_news_page_and_spawned_game():
    """Launcher com página grande (ocupa a janela) e o jogo aberto à parte: escolhe o jogo."""
    page = win(105, 10, "AlgumLauncher.exe", "", 1080, 640, parent=100, cls="Pagina")
    d = run([LAUNCHER, page, GAME_WIN])
    assert d.state == GAME and d.game.hwnd == 200 and d.launcher.hwnd == 100


def test_pick_at_skips_own_overlay_and_prefers_inner_area():
    from ddbot.detection import pick_at
    overlay = WindowInfo(9, "", 0, 0, 1920, 1080, pid=OWN)
    launcher = WindowInfo(100, "L", 100, 100, 1100, 700, pid=10)
    button = WindowInfo(110, "", 120, 120, 80, 30, pid=10, parent=100)
    surface = WindowInfo(102, "", 120, 160, 1060, 620, pid=10, parent=100)
    behind = WindowInfo(3, "Editor", 0, 0, 1900, 1000, pid=50)
    wins = [overlay, launcher, button, surface, behind]
    assert pick_at(wins, 500, 400, OWN).hwnd == 102      # na área do jogo
    assert pick_at(wins, 130, 130, OWN).hwnd == 100      # no botão do launcher: fica a janela principal
    assert pick_at(wins, 1700, 900, OWN).hwnd == 3       # fora do launcher: a janela de trás
    assert pick_at([overlay], 10, 10, OWN) is None


def test_marked_launcher_with_own_surface_waits():
    """Depois de o usuário dizer qual é o launcher, a área interna dele não volta como candidata."""
    surface = win(102, 10, "AlgumLauncher.exe", "", 1060, 600, parent=100, cls="Render")
    p = GameWindowProfile(None, WindowRule("AlgumLauncher.exe", "Wnd"))
    assert run([LAUNCHER, surface], profile=p).state == LAUNCHER_ONLY


def test_game_opened_through_windowless_helper_process():
    """launcher -> atualizador (sem janela) -> jogo: o jogo continua sendo 'aberto pelo launcher'."""
    parents = {10: EXPLORER, 15: 10, 20: 15}
    d = run([LAUNCHER, GAME_WIN], parents=parents)
    assert d.state == GAME and d.game.hwnd == 200 and d.launcher.hwnd == 100 and d.confident


def test_pick_at_follows_the_window_windows_reports_under_the_point():
    """Janela de outro programa antes do jogo na lista (ex.: navegador oculto pelo Windows ou transparente
    ao clique): no clique vale a janela que o Windows diz estar no ponto, não a primeira da lista."""
    browser = WindowInfo(300, "Navegador", 0, 0, 1920, 1040, pid=70, exe="chrome.exe", cls="Chrome_WidgetWin_1")
    d3d = WindowInfo(301, "Intermediate D3D Window", 0, 0, 1920, 1040, pid=70, exe="chrome.exe",
                     cls="Intermediate D3D Window", parent=300)
    game = WindowInfo(400, "Cliente", 260, 180, 1000, 620, pid=80, exe="python.exe", cls="TkTopLevel")
    order = [browser, d3d, game]                          # ordem das janelas: o navegador vem antes
    root = {300: 300, 301: 300, 400: 400}.get
    got = pick_at(order, 360, 280, OWN, hit=400, root_of=root)
    assert got.hwnd == 400
    # sem a resposta do Windows (contorno ao passar o mouse), uma janela oculta não conta
    hidden = WindowInfo(300, "Navegador", 0, 0, 1920, 1040, pid=70, exe="chrome.exe", visible=False)
    assert pick_at([hidden, d3d, game], 360, 280, OWN).hwnd == 400
    # se o Windows aponta a janela do próprio bot (camada ainda na tela), vale a ordem das janelas
    bot = WindowInfo(500, "JonFlow", 0, 0, 1920, 1080, pid=OWN, exe="JonFlow.exe")
    assert pick_at([bot, game], 360, 280, OWN, hit=500, root_of=lambda h: h).hwnd == 400
