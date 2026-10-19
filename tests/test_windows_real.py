"""Detecção e captura com janelas reais do Windows (só roda no Windows; na CI, no runner windows-latest).

As janelas vêm de processos de teste (tests/fixtures/fake_window.py): um "launcher" que abre o
"jogo" num processo filho depois de alguns segundos e uma janela que cobre o jogo. Testa as
chamadas reais do Windows (lista de janelas, árvore de processos, captura pela janela) que os
testes com janelas simuladas não alcançam. Não substitui o teste com o launcher e o jogo reais.
"""
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="só no Windows")
pytest.importorskip("tkinter")

FAKE = Path(__file__).parent / "fixtures" / "fake_window.py"


def wait_for(fn, timeout=20.0, every=0.25):
    end = time.monotonic() + timeout
    last = None
    while time.monotonic() < end:
        last = fn()
        if last is not None and last is not False:
            return last
        time.sleep(every)
    return last


@pytest.fixture
def procs():
    started = []

    def start(*args):
        p = subprocess.Popen([sys.executable, str(FAKE), *args])
        started.append(p)
        return p
    yield start
    # o jogo é neto deste processo: encerra a árvore inteira
    for p in started:
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)


@pytest.fixture
def svc(home):
    from ddbot.service import BotService
    s = BotService(home, start_hotkey=False)
    s.config.set("window.title_keywords", ["DDTank Launcher (teste)"])
    yield s
    s.close()


def mean_color(frame):
    return tuple(int(v) for v in frame.reshape(-1, 3).mean(axis=0))  # BGR


def test_launcher_then_game_in_child_process(procs, svc):
    from ddbot.detection import GAME
    launcher = procs("launcher", "--spawn-after", "6", "--x", "40", "--y", "40")
    first = wait_for(lambda: (lambda d: d if d.state != "nada" else None)(svc.detect_game()))
    assert first is not None, "o launcher de teste não apareceu"
    # primeira vez, só o launcher aberto: evidência fraca; o usuário diz que é o launcher
    assert not (first.state == GAME and first.confident)
    win = first.game or first.launcher
    svc.mark_launcher(win)
    assert svc.detect_game().state == "launcher_sem_jogo"
    # o launcher abre o jogo (processo filho): conecta sozinho, com o launcher reconhecido
    found = wait_for(lambda: (lambda d: d if d.state == GAME else None)(svc.auto_connect()), timeout=25)
    assert found is not None and found.confident, found
    from ddbot import winapi
    assert found.game.pid != launcher.pid
    parents, cur, chain = winapi.process_parents(), found.game.pid, []
    while cur and len(chain) < 5:
        cur = parents.get(cur)
        chain.append(cur)
    assert launcher.pid in chain  # o jogo descende do launcher
    assert found.launcher is not None and found.launcher.pid == launcher.pid
    assert svc.window is not None and svc.window.hwnd == found.game.hwnd
    # captura pela janela: a imagem é do jogo (verde)
    frame = wait_for(lambda: svc.grab(), timeout=5)
    b, g, r = mean_color(frame)
    assert g > 120 and r < 100 and b < 120, (b, g, r)
    # na próxima vez o perfil salvo reconhece o jogo direto
    assert svc.profile.game is not None


def test_capture_of_covered_game_is_the_game(procs, svc):
    from ddbot import winapi
    from ddbot.capture import WindowCapture, covered
    procs("game", "--x", "200", "--y", "150")
    game = wait_for(lambda: next((w for w in winapi.list_windows() if w.title == "Cliente"), None))
    assert game is not None
    procs("cover", "--x", "300", "--y", "220")
    cover = wait_for(lambda: next((w for w in winapi.list_windows() if w.title == "Outra janela"), None))
    assert cover is not None
    time.sleep(1.0)
    info = winapi.window_info(game.hwnd)
    assert covered(game.hwnd, info, winapi.window_at, winapi.root_of)
    cap = WindowCapture(game.hwnd)
    try:
        frame = cap.grab()
        if cap.method == "janela":
            b, g, r = mean_color(frame)
            assert g > 120 and r < 100, ("a captura trouxe a janela da frente", (b, g, r))
        else:
            # o Windows não deu a imagem pela janela: a captura recusa em vez de ler a janela errada
            assert frame is None and "na frente do jogo" in cap.unavailable
    finally:
        cap.close()


def test_pick_at_real_window(procs, svc):
    from ddbot import winapi
    from ddbot.detection import pick_at
    procs("game", "--x", "260", "--y", "180")
    game = wait_for(lambda: next((w for w in winapi.list_windows() if w.title == "Cliente"), None))
    assert game is not None
    time.sleep(0.8)
    winapi.set_foreground(game.hwnd)
    time.sleep(0.5)
    got = pick_at(svc.inventory(ranked=False), game.left + 100, game.top + 100, winapi.own_pid())
    assert got is not None and winapi.root_of(got.hwnd) == winapi.root_of(game.hwnd)


def test_two_launchers_game_linked_to_the_one_that_opened_it(procs, svc):
    """Dois launchers abertos; só o segundo abre o jogo: o jogo é associado a ele, não ao primeiro."""
    from ddbot import winapi
    from ddbot.detection import GAME
    first_l = procs("launcher", "--x", "40", "--y", "40")
    second_l = procs("launcher", "--spawn-after", "6", "--x", "520", "--y", "60")
    both = wait_for(lambda: (lambda ws: ws if len(ws) >= 2 else None)(
        [w for w in winapi.list_windows() if w.title == "DDTank Launcher (teste)"]))
    assert both is not None, "os launchers de teste não apareceram"
    svc.mark_launcher(next(w for w in both if w.pid == first_l.pid))
    found = wait_for(lambda: (lambda d: d if d.state == GAME else None)(svc.auto_connect()), timeout=25)
    assert found is not None and found.confident, found
    assert found.game.pid not in (first_l.pid, second_l.pid)
    assert found.launcher is not None and found.launcher.pid == second_l.pid, (found.launcher, first_l.pid)
