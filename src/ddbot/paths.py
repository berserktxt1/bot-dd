"""Localização de recursos empacotados e da pasta de dados do usuário."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
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
        with tempfile.NamedTemporaryFile(dir=p, prefix=".teste_escrita_", delete=True):
            pass
        return True
    except OSError:
        return False


LEGACY_NAMES = ("DDClassicoBot",)  # nome do programa até a 0.2.1


def _fallback_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    new = base / APP_NAME
    if not new.exists():
        for old in LEGACY_NAMES:  # quem já usava o programa continua com os mesmos dados
            if (base / old / "config.json").exists():
                return base / old
    return new


def user_root(notes: list[str] | None = None) -> Path:
    """Pasta gravável: 'dados/' ao lado do .exe (portátil) ou %LOCALAPPDATA%."""
    notes = notes if notes is not None else []
    env = os.environ.get("DDBOT_HOME")
    if env:
        p = Path(env).expanduser().resolve()
        if _writable(p):
            return p
        notes.append(f"a pasta DDBOT_HOME ({p}) não permite gravar; usando a pasta padrão")
    if getattr(sys, "frozen", False):
        portable = Path(sys.executable).parent / "dados"
        if _writable(portable):
            return portable
        notes.append("a pasta do programa não permite gravar (ex.: Arquivos de Programas); os dados ficam em "
                     f"{_fallback_dir()}")
    else:
        dev = resource_root() / "dados"
        if _writable(dev):
            return dev
    p = _fallback_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Paths:
    def __init__(self, root: Path | None = None):
        self.notes: list[str] = []
        self.resources = resource_root()
        self.root = Path(root).expanduser().resolve() if root else user_root(self.notes)
        self.config_file = self.root / "config.json"
        self.logs = self.root / "logs"
        self.templates = self.root / "templates"
        self.captures = self.root / "capturas"
        self.instances = self.root / "instancias"
        self.knowledge = self.root / "knowledge"
        self.db = self.root / "disparos.sqlite3"
        self.manifest = self.root / ".manifest.json"
        self.ensure()

    @property
    def data_dir(self) -> Path:
        """Diretório com a pasta 'knowledge' efetiva (cópia do usuário)."""
        return self.root

    def _sync_knowledge(self):
        """Copia os dados de conhecimento do programa.

        Arquivo ausente: copia. Arquivo igual ao que uma versão anterior copiou (o usuário
        não mexeu): atualiza para a versão nova. Arquivo editado pelo usuário (inclusive o
        modelo reajustado com disparos reais): mantém.
        """
        try:
            manifest = json.loads(self.manifest.read_text(encoding="utf-8")) if self.manifest.exists() else {}
        except (OSError, ValueError):
            manifest = {}
        changed = False
        for f in sorted((self.resources / "data" / "knowledge").glob("*.json")):
            dst = self.knowledge / f.name
            new_hash = _sha(f)
            if not dst.exists():
                shutil.copy2(f, dst)
            elif manifest.get(f.name) and manifest[f.name] == _sha(dst) and manifest[f.name] != new_hash:
                shutil.copy2(f, dst)
                self.notes.append(f"dados atualizados para a versão nova: {f.name}")
            elif _sha(dst) != new_hash:
                continue  # editado pelo usuário: não registra o hash novo
            if manifest.get(f.name) != new_hash:
                manifest[f.name] = new_hash
                changed = True
        if changed:
            from .util import atomic_write_text
            atomic_write_text(self.manifest, json.dumps(manifest, indent=1))

    def ensure(self):
        for d in (self.logs, self.templates, self.captures, self.instances, self.knowledge):
            d.mkdir(parents=True, exist_ok=True)
        self._sync_knowledge()
        for f in (self.resources / "data" / "instances").glob("*.json"):
            dst = self.instances / f.name
            if not dst.exists():
                shutil.copy2(f, dst)
        default_cfg = self.resources / "config" / "default_config.json"
        if not self.config_file.exists() and default_cfg.exists():
            shutil.copy2(default_cfg, self.config_file)
