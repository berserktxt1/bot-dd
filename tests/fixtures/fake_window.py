"""Janelas de teste para a detecção no Windows (launcher, jogo e uma janela que cobre o jogo).

Uso: python fake_window.py launcher --spawn-after 4 --x 40 --y 40
     python fake_window.py game --x 300 --y 200
     python fake_window.py cover --x 400 --y 260

Cada janela é um processo próprio, como o launcher e o cliente reais. O "launcher" abre o
"jogo" como processo filho depois de alguns segundos (como o botão Jogar). Fecha sozinha
depois de ``--life`` segundos para não sobrar processo na máquina de testes.
"""
import argparse
import subprocess
import sys
import tkinter as tk

COLORS = {"launcher": "#3355AA", "game": "#22AA44", "cover": "#AA2222"}
TITLES = {"launcher": "DDTank Launcher (teste)", "game": "Cliente", "cover": "Outra janela"}
SIZES = {"launcher": (900, 560), "game": (1000, 620), "cover": (700, 420)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=list(COLORS))
    ap.add_argument("--spawn-after", type=float, default=0)
    ap.add_argument("--x", type=int, default=50)
    ap.add_argument("--y", type=int, default=50)
    ap.add_argument("--life", type=float, default=90)
    a = ap.parse_args()
    root = tk.Tk()
    root.title(TITLES[a.kind])
    w, h = SIZES[a.kind]
    root.geometry(f"{w}x{h}+{a.x}+{a.y}")
    c = tk.Canvas(root, background=COLORS[a.kind], highlightthickness=0)
    c.pack(fill="both", expand=True)
    c.create_text(w // 2, h // 2, text=a.kind.upper(), fill="#FFFFFF", font=("Arial", 32, "bold"))
    if a.kind == "launcher" and a.spawn_after > 0:
        def spawn():
            subprocess.Popen([sys.executable, __file__, "game", "--x", str(a.x + 260), "--y", str(a.y + 160),
                              "--life", str(a.life)])
        root.after(int(a.spawn_after * 1000), spawn)
    root.after(int(a.life * 1000), root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
