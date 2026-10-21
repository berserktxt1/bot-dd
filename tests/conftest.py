import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ddbot.knowledge import KnowledgeBase  # noqa: E402
from ddbot.physics import PhysicsParams  # noqa: E402


@pytest.fixture(scope="session")
def kb():
    return KnowledgeBase(ROOT / "data")


@pytest.fixture(scope="session")
def params():
    return PhysicsParams.load(ROOT / "data" / "knowledge" / "model_params.json")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DDBOT_HOME", str(tmp_path))
    return tmp_path


_TK_ALIVE: list = []  # janelas Tk dos testes, vivas até o fim do processo (ver tk_cleanup)


@pytest.fixture
def tk_cleanup():
    """Para testes que abrem janelas Tk: devolve a função que guarda a janela (ou o Tk) viva até o fim do processo.

    No Windows, liberar um interpretador Tk no meio da sessão derruba o processo ou o Tk seguinte: (1) se a coleta
    de lixo roda numa thread da janela (a procura do jogo), o Tcl é liberado fora da thread que o criou e o processo
    cai ("fatal exception 0x80000003", CI 39525965108); (2) liberado na thread principal, o Tk criado em seguida às
    vezes não lê os próprios arquivos ("Can't find a usable init.tcl", diagnóstico 39527994935). Guardadas aqui, as
    janelas fechadas só são liberadas na saída do processo, na thread principal.
    """
    return _TK_ALIVE.append
