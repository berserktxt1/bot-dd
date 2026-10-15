"""Localização de recursos empacotados e da pasta de dados do usuário."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from . import APP_NAME


def resource_root() -> Path:
    """Pasta com 'data/' e 'config/' padrão (dentro do pacote PyInstaller ou do repositório)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def _writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        return True
    except OSError:
        return False


def user_root() -> Path:
    """Pasta gravável: 'dados/' ao lado do .exe (portátil) ou %LOCALAPPDATA%."""
    env = os.environ.get("DDBOT_HOME")
    if env:
        p = Path(env)
        p.mkdir(parents=True, exist_ok=True)
        return p
    if getattr(sys, "frozen", False):
        portable = Path(sys.executable).parent / "dados"
        if _writable(portable):
            return portable
    else:
        dev = resource_root() / "dados"
        if _writable(dev):
            return dev
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    p = base / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


class Paths:
    def __init__(self, root: Path | None = None):
        self.resources = resource_root()
        self.root = Path(root) if root else user_root()
        self.config_file = self.root / "config.json"
        self.logs = self.root / "logs"
        self.templates = self.root / "templates"
        self.captures = self.root / "capturas"
        self.instances = self.root / "instancias"
        self.knowledge = self.root / "knowledge"
        self.db = self.root / "disparos.sqlite3"
        self.ensure()

    @property
    def data_dir(self) -> Path:
        """Diretório com a pasta 'knowledge' efetiva (cópia do usuário)."""
        return self.root

    def ensure(self):
        for d in (self.logs, self.templates, self.captures, self.instances, self.knowledge):
            d.mkdir(parents=True, exist_ok=True)
        # copia dados padrão na primeira execução, sem sobrescrever edições do usuário
        src_k = self.resources / "data" / "knowledge"
        for f in src_k.glob("*.json"):
            dst = self.knowledge / f.name
            if not dst.exists():
                shutil.copy2(f, dst)
        for f in (self.resources / "data" / "instances").glob("*.json"):
            dst = self.instances / f.name
            if not dst.exists():
                shutil.copy2(f, dst)
        default_cfg = self.resources / "config" / "default_config.json"
        if not self.config_file.exists() and default_cfg.exists():
            shutil.copy2(default_cfg, self.config_file)
