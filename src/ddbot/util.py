"""Gravação atômica de arquivos e utilidades pequenas compartilhadas."""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path


def atomic_write_text(path, text: str, encoding="utf-8", retries=10) -> Path:
    """Grava em arquivo temporário, força para o disco e substitui o destino.

    Uma queda no meio deixa o arquivo antigo intacto. No Windows o ``replace`` falha com
    ``PermissionError`` se outro programa (antivírus, indexador, OneDrive) estiver com o
    destino aberto: tenta de novo algumas vezes antes de desistir.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        for i in range(retries):
            try:
                os.replace(tmp, path)
                return path
            except PermissionError:
                if i == retries - 1:
                    raise
                time.sleep(0.05 * (i + 1))
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return path


def mask_home(text: str) -> str:
    """Troca a pasta do usuário (que contém o nome dele) por %USERPROFILE% nos registros."""
    home = str(Path.home())
    if len(home) > 3 and home in text:
        text = text.replace(home, "%USERPROFILE%")
    return text
