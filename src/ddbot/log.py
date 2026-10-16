"""Logs em arquivo rotativo + fila para a interface gráfica."""
from __future__ import annotations

import logging
import queue
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_QUEUE: "queue.Queue[str]" = queue.Queue(maxsize=5000)


class MaskHome(logging.Filter):
    """Os registros podem ser enviados para suporte: troca a pasta do usuário por %USERPROFILE%."""

    def filter(self, record):
        from .util import mask_home
        msg = record.getMessage()
        masked = mask_home(msg)
        if masked != msg:
            record.msg, record.args = masked, ()
        return True


class QueueHandler(logging.Handler):
    def emit(self, record):
        try:
            LOG_QUEUE.put_nowait(self.format(record))
        except queue.Full:
            pass


def setup_logging(log_dir: Path, level=logging.INFO) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "ddbot.log"
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8", delay=True)
    fh.setFormatter(fmt)
    qh = QueueHandler()
    qh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
    for h in (fh, qh):
        h.addFilter(MaskHome())
        root.addHandler(h)
    return log_file
