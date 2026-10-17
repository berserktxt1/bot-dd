"""Logo do JonFlow (canhão com o disparo em arco) para o topo da janela e o ícone."""
from __future__ import annotations

import logging

from ..paths import resource_root

log = logging.getLogger(__name__)


def load_logo(root, size: int):
    """PhotoImage quadrada do ícone no tamanho pedido; None se o arquivo faltar (o programa segue sem)."""
    path = resource_root() / "assets" / "jonflow-icon.png"
    try:
        from PIL import Image, ImageTk
        img = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
        return ImageTk.PhotoImage(img, master=root)
    except Exception as exc:
        log.warning("logo indisponível (%s): %s", path, exc)
        return None
