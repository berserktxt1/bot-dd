"""Assistente: identificar qual janela é o jogo e qual é o launcher.

Lista as janelas reais do computador (principais e internas), com o programa, a classe e o
tamanho, e mostra uma prévia da captura de cada uma. O usuário marca o jogo (onde a batalha
aparece) e, se quiser, o launcher. Nada de nomes presumidos.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

from ..capture import WindowCapture
from ..game_window import validate_choice
from . import theme as T
from .widgets import ImageCanvas


class WindowWizard(tk.Toplevel):
    def __init__(self, app, service, on_saved=None):
        super().__init__(app.root)
        self.app, self.svc, self.on_saved = app, service, on_saved
        px = app.th.px
        self.title("Identificar a janela do jogo")
        self.configure(background=T.BG)
        self.geometry(f"{px(1060)}x{px(640)}")
        self.transient(app.root)
        self.windows = []
        self.game = None
        self.launcher = None
        self._preview_q: "queue.Queue" = queue.Queue(maxsize=2)
        self._list_q: "queue.Queue" = queue.Queue(maxsize=2)

        intro = ttk.Label(self, wraplength=px(1000), justify="left", text=(
            "Abra o DDClássico pelo launcher e entre no jogo. Escolha na lista a janela onde a batalha aparece "
            "(confira na prévia) e clique em Este é o jogo. Se o jogo fica dentro do launcher, escolha a janela "
            "interna, a que mostra só o jogo. Depois escolha a janela do launcher e clique em Este é o launcher: "
            "assim o bot sabe avisar quando o launcher está aberto e o jogo ainda não."))
        intro.pack(fill="x", padx=px(16), pady=(px(14), px(8)))
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=px(16))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(body, columns=("tipo", "prog", "titulo", "classe", "tam"), show="headings")
        for col, text, w in (("tipo", "Tipo", 90), ("prog", "Programa", 140), ("titulo", "Título", 220),
                             ("classe", "Classe", 160), ("tam", "Tamanho", 90)):
            self.tree.heading(col, text=text, anchor="w")
            self.tree.column(col, width=px(w), anchor="w", stretch=col == "titulo")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._preview())
        self.canvas = ImageCanvas(body, "Escolha uma janela na lista para ver a prévia.")
        self.canvas.grid(row=0, column=1, sticky="nsew", padx=(px(12), 0))

        self.lbl_choice = ttk.Label(self, text="", style="Muted.TLabel", wraplength=px(1000), justify="left")
        self.lbl_choice.pack(fill="x", padx=px(16), pady=(px(8), 0))
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=px(16), pady=px(12))
        ttk.Button(bar, text="Atualizar lista", command=self.reload).pack(side="left")
        ttk.Button(bar, text="Este é o jogo", style="Primary.TButton", command=self.mark_game).pack(
            side="left", padx=(px(12), 0))
        ttk.Button(bar, text="Este é o launcher", command=self.mark_launcher).pack(side="left", padx=(px(8), 0))
        ttk.Button(bar, text="Cancelar", command=self.destroy).pack(side="right")
        self.btn_save = ttk.Button(bar, text="Salvar", style="Primary.TButton", command=self.save)
        self.btn_save.pack(side="right", padx=(0, px(8)))
        self._update_choice()
        self.reload()
        self.after(150, self._poll)

    # ------------------------------------------------------------------ lista
    def reload(self):
        self.tree.delete(*self.tree.get_children())
        self.tree.insert("", "end", iid="carregando", values=("", "procurando janelas...", "", "", ""))

        def work():
            try:
                self._list_q.put(self.svc.inventory())
            except Exception as exc:
                self._list_q.put(exc)
        threading.Thread(target=work, daemon=True, name="inventario-janelas").start()

    def _fill(self, windows):
        self.tree.delete(*self.tree.get_children())
        self.windows = windows
        if not windows:
            self.tree.insert("", "end", values=("", "nenhuma janela encontrada (o bot só lista janelas no Windows)",
                                                "", "", ""))
            return
        for i, w in enumerate(windows):
            kind = "interna" if w.parent else "principal"
            self.tree.insert("", "end", iid=str(i), values=(kind, w.exe or "?", w.title or "(sem título)",
                                                            w.cls, f"{w.width}×{w.height}"))

    def _selected(self):
        sel = self.tree.selection()
        if not sel or not sel[0].isdigit():
            return None
        return self.windows[int(sel[0])]

    # ----------------------------------------------------------------- prévia
    def _preview(self):
        w = self._selected()
        if w is None:
            return

        def work():
            cap = WindowCapture(w.hwnd)
            try:
                frame = cap.grab()
            except Exception:
                frame = None
            finally:
                cap.close()
            try:
                self._preview_q.put_nowait(frame)
            except queue.Full:
                pass
        threading.Thread(target=work, daemon=True, name="previa-janela").start()

    def _poll(self):
        if not self.winfo_exists():
            return
        try:
            item = self._list_q.get_nowait()
            if isinstance(item, Exception):
                self._fill([])
                self.lbl_choice.configure(text=f"Erro ao listar as janelas: {item}")
            else:
                self._fill(item)
        except queue.Empty:
            pass
        try:
            frame = self._preview_q.get_nowait()
            self.canvas.empty_text = "Não foi possível capturar esta janela (minimizada?)."
            self.canvas.show(frame)
        except queue.Empty:
            pass
        self.after(150, self._poll)

    # ---------------------------------------------------------------- escolha
    def _describe(self, w):
        if w is None:
            return "não escolhido"
        kind = "janela interna" if w.parent else "janela"
        return f"{w.exe or '?'}, {kind}, {w.width}×{w.height}" + (f", classe {w.cls}" if w.cls else "")

    def _update_choice(self, error=""):
        text = f"Jogo: {self._describe(self.game)}.   Launcher: {self._describe(self.launcher)}."
        if error:
            text += f"   {error}"
        self.lbl_choice.configure(text=text, style="Error.TLabel" if error else "Muted.TLabel")
        self.btn_save.state(["!disabled"] if self.game else ["disabled"])

    def mark_game(self):
        w = self._selected()
        if w is not None:
            self.game = w
            self._update_choice(validate_choice(self.game, self.launcher) or "")

    def mark_launcher(self):
        w = self._selected()
        if w is not None:
            self.launcher = w
            self._update_choice(validate_choice(self.game, self.launcher) or "" if self.game else "")

    def save(self):
        err = self.svc.save_profile(self.game, self.launcher)
        if err:
            self._update_choice(err)
            return
        if self.on_saved:
            self.on_saved()
        self.destroy()
