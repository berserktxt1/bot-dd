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
