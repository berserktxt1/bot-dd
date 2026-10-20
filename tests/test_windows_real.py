"""Detecção e captura com janelas reais do Windows (só roda no Windows; na CI, no runner windows-2025).

As janelas vêm de processos de teste (tests/fixtures/fake_window.py): um "launcher" que abre o
"jogo" num processo filho depois de alguns segundos e uma janela que cobre o jogo. Testa as
chamadas reais do Windows (lista de janelas, árvore de processos, captura pela janela) que os
testes com janelas simuladas não alcançam. Não substitui o teste com o launcher e o jogo reais.

Isolamento: cada teste marca os títulos com uma etiqueta única e usa o pid informado pela
própria janela (``--ready``), nunca o do ``Popen``: no Windows, o python.exe de um venv é um
redirecionador que abre o Python base como processo filho, e é o filho que cria a janela (por
isso, num PC com venv, o pid do Popen não tinha janela nenhuma e o launcher "esperado" era o
redirecionador). Janelas de outros programas ou de execuções anteriores nunca entram no teste.
Ao terminar (mesmo com erro), só os processos criados pelo teste são encerrados.
"""
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="só no Windows")
pytest.importorskip("tkinter")

FIXTURES = Path(__file__).parent / "fixtures"
FAKE = FIXTURES / "fake_window.py"
sys.path.insert(0, str(FIXTURES))
from fake_window import title_for  # noqa: E402


def wait_for(fn, timeout=20.0, every=0.25):
    end = time.monotonic() + timeout
    last = None
    while time.monotonic() < end:
        last = fn()
        if last is not None and last is not False:
            return last
        time.sleep(every)
    return last


class Proc:
    """Processo de teste e a identidade da janela que ele criou."""

    def __init__(self, popen, ready: Path, kind: str, tag: str):
        self.popen, self.ready, self.kind, self.tag = popen, ready, kind, tag

    @staticmethod
    def _read(path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def info(self, timeout=20.0) -> dict:
        got = wait_for(lambda: self._read(self.ready), timeout)
        assert got is not None, f"a janela de teste '{self.kind}' não apareceu (saída {self.popen.poll()})"
        return got

    @property
    def pid(self) -> int:
        """Pid do processo dono da janela (não o do Popen, que pode ser o redirecionador do venv)."""
        return self.info()["pid"]

    def game_info(self, timeout=25.0) -> dict | None:
        return wait_for(lambda: self._read(Path(str(self.ready) + ".game")), timeout)

    def window(self, timeout=20.0):
        """A janela principal deste processo, com o título desta execução."""
        from ddbot import winapi
        me = self.info(timeout)
        return wait_for(lambda: next((w for w in winapi.list_windows()
                                      if w.pid == me["pid"] and w.title == me["title"]), None), timeout)


@pytest.fixture
def tag():
    return uuid.uuid4().hex[:8]


@pytest.fixture
def procs(tmp_path, tag):
    started: list[Proc] = []

    def start(kind, *args):
        ready = tmp_path / f"{kind}_{len(started)}.json"
        p = subprocess.Popen([sys.executable, str(FAKE), kind, "--tag", tag, "--ready", str(ready), *args])
        proc = Proc(p, ready, kind, tag)
        started.append(proc)
        return proc
    try:
        yield start
    finally:
        # só os processos deste teste: a árvore do Popen (redirecionador → Python → jogo) e, se a ligação
        # com o pai se perdeu, os pids que as próprias janelas informaram
        for proc in started:
            subprocess.run(["taskkill", "/PID", str(proc.popen.pid), "/T", "/F"], capture_output=True)
            for path in (proc.ready, Path(str(proc.ready) + ".game")):
                data = Proc._read(path)
                if data:
                    subprocess.run(["taskkill", "/PID", str(data["pid"]), "/T", "/F"], capture_output=True)


@pytest.fixture
def svc(home, tag):
    from ddbot.service import BotService
    s = BotService(home, start_hotkey=False)
    s.config.set("window.title_keywords", [title_for("launcher", tag)])
    try:
        yield s
    finally:
        s.close()


def mean_color(frame):
    return tuple(int(v) for v in frame.reshape(-1, 3).mean(axis=0))  # BGR


def ancestors(pid):
    from ddbot import winapi
    parents, cur, chain = winapi.process_parents(), pid, []
    while cur and len(chain) < 8:
        cur = parents.get(cur)
        chain.append(cur)
    return chain


def test_launcher_then_game_in_child_process(procs, svc):
    from ddbot.detection import GAME
    launcher = procs("launcher", "--spawn-after", "6", "--x", "40", "--y", "40")
    lwin = launcher.window()
    assert lwin is not None, "a janela do launcher de teste não apareceu"
    first = wait_for(lambda: (lambda d: d if d.state != "nada" else None)(svc.detect_game()))
    assert first is not None, "o launcher de teste não foi detectado"
    # primeira vez, só o launcher aberto: evidência fraca; o usuário diz que é o launcher
    assert not (first.state == GAME and first.confident)
    win = first.game or first.launcher
    assert win.pid == launcher.pid  # a detecção encontrou o launcher deste teste
    svc.mark_launcher(win)
    assert svc.detect_game().state == "launcher_sem_jogo"
    # o launcher abre o jogo (processo filho): conecta sozinho, com o launcher reconhecido
    found = wait_for(lambda: (lambda d: d if d.state == GAME else None)(svc.auto_connect()), timeout=25)
    assert found is not None and found.confident, found
    game = launcher.game_info()
    assert game is not None and found.game.pid == game["pid"]  # é o jogo que este launcher abriu
    assert launcher.pid in ancestors(found.game.pid)  # o jogo descende do processo dono da janela do launcher
    assert found.launcher is not None and found.launcher.pid == launcher.pid, (found.launcher, launcher.pid)
    assert found.launcher.hwnd == lwin.hwnd
    assert svc.window is not None and svc.window.hwnd == found.game.hwnd
    # captura pela janela: a imagem é do jogo (verde). Logo que a janela aparece o Windows ainda anima a
    # abertura (a imagem sai misturada com o fundo, CI 39346270446: BGR 139, 202, 118); espera o jogo terminar
    # de desenhar. Uma captura da janela errada (launcher azul, outra janela) nunca fica verde e reprova
    seen = []

    def drawn():
        f = svc.grab()
        if f is None:
            return None
        seen.append(mean_color(f))
        b, g, r = seen[-1]
        return f if g > 120 and r < 100 and b < 120 else None
    frame = wait_for(drawn, timeout=10)
    assert frame is not None, ("a captura não ficou com a imagem do jogo", seen[-5:])
    # na próxima vez o perfil salvo reconhece o jogo direto
    assert svc.profile.game is not None


def test_capture_of_covered_game_is_the_game(procs, svc):
    from ddbot import winapi
    from ddbot.capture import WindowCapture, covered
    game = procs("game", "--x", "200", "--y", "150").window()
    assert game is not None
    cover = procs("cover", "--x", "300", "--y", "220", "--topmost").window()
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
            # sem a imagem da janela confirmada: a captura recusa (com o motivo) em vez de ler a janela errada
            assert frame is None and cap.unavailable
    finally:
        cap.close()


def test_pick_at_real_window(procs, svc):
    """A janela escolhida é a que o Windows diz estar sob o ponto, e não uma de outro programa.

    O jogo de teste fica acima das janelas comuns (``--topmost``): trazer para a frente com
    SetForegroundWindow é recusado quando o processo do teste não está em primeiro plano, e
    então um navegador maximizado continuava por cima do ponto (falha relatada com a janela
    "Intermediate D3D Window" do Chrome).
    """
    from ddbot import winapi
    from ddbot.detection import pick_at
    game = procs("game", "--x", "260", "--y", "180", "--topmost").window()
    assert game is not None
    x, y = game.left + 100, game.top + 100
    # o próprio Windows confirma o cenário: no ponto está o jogo de teste
    under = wait_for(lambda: (lambda h: h if h and winapi.root_of(h) == winapi.root_of(game.hwnd) else None)(
        winapi.window_at(x, y)), timeout=5)
    assert under, ("outra janela continua sobre o jogo de teste", winapi.window_info(winapi.window_at(x, y)))
    windows = svc.inventory(ranked=False)
    got = pick_at(windows, x, y, winapi.own_pid(), hit=under, root_of=winapi.root_of)  # como no clique
    assert got is not None and winapi.root_of(got.hwnd) == winapi.root_of(game.hwnd), got
    got = pick_at(windows, x, y, winapi.own_pid())  # só a ordem das janelas (contorno ao passar o mouse)
    assert got is not None and winapi.root_of(got.hwnd) == winapi.root_of(game.hwnd), got


def test_two_launchers_game_linked_to_the_one_that_opened_it(procs, svc):
    """Dois launchers abertos; só o segundo abre o jogo: o jogo é associado a ele, não ao primeiro."""
    from ddbot.detection import GAME
    first_l = procs("launcher", "--x", "40", "--y", "40")
    second_l = procs("launcher", "--spawn-after", "6", "--x", "520", "--y", "60")
    first_w, second_w = first_l.window(), second_l.window()
    assert first_w is not None and second_w is not None, "os launchers de teste não apareceram"
    assert first_w.pid != second_w.pid
    svc.mark_launcher(first_w)
    found = wait_for(lambda: (lambda d: d if d.state == GAME else None)(svc.auto_connect()), timeout=25)
    assert found is not None and found.confident, found
    game = second_l.game_info()
    assert game is not None and found.game.pid == game["pid"]
    assert found.game.pid not in (first_l.pid, second_l.pid)
    assert second_l.pid in ancestors(found.game.pid) and first_l.pid not in ancestors(found.game.pid)
    assert found.launcher is not None and found.launcher.pid == second_l.pid, (found.launcher, first_l.pid)
    assert found.launcher.hwnd == second_w.hwnd
