"""Janelas de teste para a detecção no Windows (launcher, jogo e uma janela que cobre o jogo).

Uso: python fake_window.py launcher --spawn-after 4 --x 40 --y 40 --tag ab12 --ready pasta/launcher.json
     python fake_window.py game --x 300 --y 200 --tag ab12 --ready pasta/game.json
     python fake_window.py cover --x 400 --y 260 --tag ab12

Cada janela é um processo próprio, como o launcher e o cliente reais. O "launcher" abre o
"jogo" como processo filho depois de alguns segundos (como o botão Jogar). Fecha sozinha
depois de ``--life`` segundos para não sobrar processo na máquina de testes.

Identidade (para o teste reconhecer só as janelas que ele criou):
- ``--tag`` entra no título: janelas de outra execução (ou de outro programa) nunca batem;
- ``--ready`` recebe, quando a janela já está na tela, o pid **deste** processo e o hwnd da
  janela. O pid do ``subprocess.Popen`` não serve: no Windows, o python.exe de um venv é um
  redirecionador que abre o Python base como processo filho, e é o filho que cria a janela.
  O jogo aberto pelo launcher escreve em ``<ready>.game``.
"""
import argparse
import json
import os
import subprocess
import sys
import tkinter as tk

COLORS = {"launcher": "#3355AA", "game": "#22AA44", "cover": "#AA2222"}
TITLES = {"launcher": "DDTank Launcher (teste)", "game": "Cliente", "cover": "Outra janela"}
SIZES = {"launcher": (900, 560), "game": (1000, 620), "cover": (700, 420)}


def title_for(kind: str, tag: str = "") -> str:
    return f"{TITLES[kind]} {tag}".strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=list(COLORS))
    ap.add_argument("--spawn-after", type=float, default=0)
    ap.add_argument("--x", type=int, default=50)
    ap.add_argument("--y", type=int, default=50)
    ap.add_argument("--life", type=float, default=90)
    ap.add_argument("--tag", default="")
    ap.add_argument("--ready", default="")
    ap.add_argument("--topmost", action="store_true")
    a = ap.parse_args()
    root = tk.Tk()
    root.title(title_for(a.kind, a.tag))
    w, h = SIZES[a.kind]
    root.geometry(f"{w}x{h}+{a.x}+{a.y}")
    if a.topmost:
        # acima das janelas comuns (navegador maximizado etc.) sem depender de trazer para a frente:
        # o Windows recusa SetForegroundWindow de um processo que não está em primeiro plano
        root.attributes("-topmost", True)
    c = tk.Canvas(root, background=COLORS[a.kind], highlightthickness=0)
    c.pack(fill="both", expand=True)
    c.create_text(w // 2, h // 2, text=a.kind.upper(), fill="#FFFFFF", font=("Arial", 32, "bold"))

    def ready():
        if not a.ready:
            return
        root.update_idletasks()
        try:
            frame = int(root.wm_frame(), 16)  # janela principal (a moldura), não a área interna do Tk
        except (tk.TclError, ValueError):
            frame = 0
        tmp = a.ready + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "hwnd": frame, "title": root.title()}, f)
        os.replace(tmp, a.ready)  # o teste nunca lê um arquivo pela metade
    root.after(300, ready)
    if a.kind == "launcher" and a.spawn_after > 0:
        def spawn():
            args = [sys.executable, __file__, "game", "--x", str(a.x + 260), "--y", str(a.y + 160),
                    "--life", str(a.life), "--tag", a.tag]
            if a.ready:
                args += ["--ready", a.ready + ".game"]
            subprocess.Popen(args)
        root.after(int(a.spawn_after * 1000), spawn)
    root.after(int(a.life * 1000), root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
