"""Detectar jogo: acha a janela jogável sozinho e só pede ajuda quando não tem certeza.

Enquanto a janela está aberta a janela principal do JonFlow fica minimizada, para não
cobrir o launcher nem o jogo; ao fechar ela volta como estava. A prévia é capturada da
própria janela do jogo (funciona mesmo com outra janela por cima).

Estados mostrados:
- procurando / launcher aberto: continua procurando a cada segundo e conecta sozinho;
- jogo conectado (evidência forte): mostra a prévia para conferir;
- é esta? (evidência fraca): pergunta se a janela é o jogo ou o launcher;
- escolher: duas ou mais candidatas parecidas, numa lista com prévia;
- mostrar onde está o jogo: uma camada sobre a tela; o usuário clica na janela do jogo
  (o clique não chega ao jogo) ou aperta Esc para cancelar.
"""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from .. import winapi
from ..capture import WindowCapture
from ..detection import CHOOSE, GAME, LAUNCHER_ONLY, Detection, pick_at
from . import theme as T
from .widgets import ImageCanvas

SCAN_EVERY_MS = 1000


def describe_window(w) -> str:
    title = (w.title or "").strip() or "sem título"
    kind = "área interna" if w.parent else "janela"
    return f"{title} ({w.exe or 'programa desconhecido'}, {kind} {w.width}×{w.height})"


class DetectDialog(tk.Toplevel):
    def __init__(self, app, service, on_done=None, hide_main=True):
        super().__init__(app.root)
        self.app, self.svc, self.on_done = app, service, on_done
        px = app.th.px
        self.title("Detectar jogo")
        self.configure(background=T.BG)
        w, h = px(860), px(560)
        area = winapi.work_area()
        ax, ay, aw, ah = area or (0, 0, self.winfo_screenwidth(), self.winfo_screenheight())
        w, h = min(w, aw - px(16)), min(h, ah - px(48))
        # no canto superior direito: cobre o mínimo do launcher, que costuma abrir no centro
        self.geometry(f"{w}x{h}+{ax + aw - w - px(12)}+{ay + px(12)}")
        self.minsize(min(px(640), w), min(px(420), h))
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.close())

        self.baseline: set[int] | None = None
        self.rejected: set[int] = set()
        self.detection: Detection | None = None
        self.shown = None             # janela em exibição/confirmação
        self.list_items: list = []
        self.mode = "procurando"
        self._closed = False
        self._scanning = False
        self._next_scan = 0.0
        self._results: "queue.Queue" = queue.Queue(maxsize=4)
        self._previews: "queue.Queue" = queue.Queue(maxsize=2)
        self._preview_for = None

        pad = px(16)
        head = ttk.Frame(self)
        head.pack(fill="x", padx=pad, pady=(px(14), 0))
        self.lbl_title = ttk.Label(head, text="Procurando o jogo...", style="Section.TLabel")
        self.lbl_title.pack(anchor="w")
        self.lbl_detail = ttk.Label(head, text="", style="Muted.TLabel", wraplength=w - 2 * pad, justify="left")
        self.lbl_detail.pack(anchor="w", fill="x", pady=(px(4), 0))
        head.bind("<Configure>", lambda e: self.lbl_detail.configure(wraplength=max(px(300), e.width)))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=pad, pady=px(10))
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(body, columns=("janela",), show="headings", selectmode="browse")
        self.tree.heading("janela", text="Janelas", anchor="w")
        self.tree.column("janela", width=px(320), anchor="w")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_list_select())
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(0, px(12)))
        self.tree.grid_remove()
        self.canvas = ImageCanvas(body, "A prévia da janela aparece aqui.")
        self.canvas.grid(row=0, column=1, sticky="nsew")

        self.bar = ttk.Frame(self)
        self.bar.pack(fill="x", padx=pad, pady=(0, px(14)))

        self._main_hidden = False
        if hide_main:
            self._hide_main()
        self._render()
        self.after(50, self._tick)

    # ------------------------------------------------------- janela principal
    def _hide_main(self):
        """A janela principal sai da frente enquanto o usuário procura o jogo (volta ao fechar)."""
        try:
            self.app.root.iconify()
            self._main_hidden = True
        except tk.TclError:
            self._main_hidden = False

    def _restore_main(self):
        if not self._main_hidden:
            return
        self._main_hidden = False
        try:
            self.app.root.deiconify()
            self.app.root.lift()
        except tk.TclError:
            pass

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._restore_main()
        try:
            self.destroy()
        finally:
            if self.on_done:
                self.on_done()

    # ----------------------------------------------------------------- busca
    def _scan(self):
        if self._scanning:
            return
        self._scanning = True
        baseline, rejected = self.baseline, set(self.rejected)

        def work():
            try:
                base = baseline
                if base is None:
                    base = {w.hwnd for w in self.svc.inventory(ranked=False)}
                found = self.svc.auto_connect(base, rejected)
                self._results.put((found, base, None))
            except Exception as exc:
                self._results.put((None, baseline, exc))
            finally:
                self._scanning = False
        threading.Thread(target=work, daemon=True, name="detectar-jogo").start()

    def _waiting(self) -> bool:
        return self.mode in ("procurando", "launcher")

    def _tick(self):
        if self._closed:
            return
        try:
            found, base, exc = self._results.get_nowait()
        except queue.Empty:
            found = exc = None
        else:
            if self.baseline is None:
                self.baseline = base
            if exc is not None:
                self._set_text("Não foi possível procurar as janelas", f"Erro: {exc}")
            elif found is not None and self._waiting():
                self._on_detection(found)
        try:
            hwnd, frame = self._previews.get_nowait()
            if self.shown is not None and hwnd == self.shown.hwnd:
                self.canvas.empty_text = ("Sem prévia: a janela está minimizada ou não deixa capturar a imagem. "
                                          "Confira olhando a própria janela.")
                self.canvas.show(frame)
        except queue.Empty:
            pass
        if self._waiting() and time.monotonic() >= self._next_scan:
            self._next_scan = time.monotonic() + SCAN_EVERY_MS / 1000
            self._scan()
        self.after(150, self._tick)

    def _on_detection(self, d: Detection):
        self.detection = d
        if d.state == GAME and d.confident:
            self.mode = "conectado"
            self.shown = d.game
        elif d.state == GAME:
            self.mode = "confirmar"
            self.shown = d.game
        elif d.state == CHOOSE:
            self.mode = "escolher"
            self.list_items = [c.window for c in d.candidates if c.window.hwnd not in self.rejected]
        elif d.state == LAUNCHER_ONLY:
            self.mode = "launcher"
            self.shown = d.launcher
        else:
            self.mode = "procurando"
            self.shown = None
        self._render()

    # ------------------------------------------------------------- desenho
    def _set_text(self, title, detail):
        self.lbl_title.configure(text=title)
        self.lbl_detail.configure(text=detail)

    def _buttons(self, spec):
        for w in self.bar.winfo_children():
            w.destroy()
        px = self.app.th.px
        for text, cmd, style, side in spec:
            ttk.Button(self.bar, text=text, command=cmd, style=style).pack(
                side=side, padx=(0, px(8)) if side == "left" else (px(8), 0))

    def _render(self):
        d, m = self.detection, self.mode
        can_pick = winapi.IS_WINDOWS
        pick = ("Mostrar onde está o jogo", self.start_pick, "TButton", "left")
        listing = ("Escolher da lista", self.show_all, "TButton", "left")
        cancel = ("Fechar", self.close, "TButton", "right")
        self.tree.grid_remove()
        if m == "procurando":
            self._set_text("Procurando o jogo...",
                           "Abra o DDClássico pelo launcher. O JonFlow continua procurando e conecta sozinho quando "
                           "o jogo aparecer. Se o jogo já está aberto e não foi encontrado, clique em Mostrar onde "
                           "está o jogo.")
            self._buttons(([pick] if can_pick else []) + [listing, cancel])
        elif m == "launcher":
            name = (d.launcher.title or d.launcher.exe) if d and d.launcher else "o launcher"
            self._set_text("Launcher aberto: aguardando o jogo",
                           f"Encontrei {name}, mas o jogo ainda não abriu. Entre no jogo pelo launcher; "
                           "o JonFlow conecta sozinho quando a janela do jogo aparecer.")
            self._buttons(([pick] if can_pick else []) + [listing, cancel])
        elif m == "conectado":
            where = d.message if d else "Jogo conectado"
            self._set_text("Jogo conectado",
                           f"{where}: {describe_window(self.shown)}. Confira na prévia: ela deve mostrar o jogo "
                           "(lobby, menu ou batalha). Os cliques e teclas vão só para essa área.")
            self._buttons([("Pronto", self.close, "Primary.TButton", "left"),
                           ("Não é esta janela", self.not_this, "TButton", "left"), cancel])
        elif m == "confirmar":
            self._set_text("É esta a janela do jogo?",
                           f"Encontrei {describe_window(self.shown)}. Se a prévia mostra o jogo (lobby, menu ou "
                           "batalha), confirme. Se mostra o launcher (notícias, botão de jogar), clique em É o "
                           "launcher: o JonFlow espera o jogo abrir. Se é outra coisa, clique em Não é esta.")
            self._buttons([("Sim, é o jogo", self.confirm, "Primary.TButton", "left"),
                           ("É o launcher", self.is_launcher, "TButton", "left"),
                           ("Não é esta", self.skip_this, "TButton", "left"),
                           ("Escolher da lista", self.show_all, "TButton", "left"), cancel])
        elif m in ("escolher", "todas"):
            if m == "escolher":
                self._set_text("Qual destas janelas é o jogo?",
                               "Mais de uma janela parece o jogo. Escolha na lista e confira na prévia.")
            else:
                self._set_text("Escolha a janela do jogo",
                               "Todas as janelas abertas, com as mais prováveis primeiro. Escolha a que mostra o "
                               "jogo e confira na prévia.")
            self.tree.grid()
            self.tree.delete(*self.tree.get_children())
            for i, w in enumerate(self.list_items):
                self.tree.insert("", "end", iid=str(i), values=(describe_window(w),))
            if not self.list_items:
                self.tree.insert("", "end", iid="vazio", values=("nenhuma janela encontrada",))
            self._buttons([("Usar esta janela", self.use_selected, "Primary.TButton", "left")]
                          + ([pick] if can_pick else []) + [("Voltar a procurar", self.restart, "TButton", "left"),
                                                            cancel])
            if self.list_items:
                self.tree.selection_set("0")
        self._request_preview()

    def _request_preview(self):
        w = self.shown
        if w is None:
            self.canvas.empty_text = "A prévia da janela aparece aqui."
            self.canvas.show(None)
            return
        if self._preview_for == w.hwnd:
            return
        self._preview_for = w.hwnd

        def work():
            cap = WindowCapture(w.hwnd)
            try:
                frame = cap.grab()
            except Exception:
                frame = None
            finally:
                cap.close()
            try:
                self._previews.put_nowait((w.hwnd, frame))
            except queue.Full:
                pass
        threading.Thread(target=work, daemon=True, name="previa-janela").start()

    # --------------------------------------------------------------- ações
    def _on_list_select(self):
        sel = self.tree.selection()
        if sel and sel[0].isdigit():
            self.shown = self.list_items[int(sel[0])]
            self._preview_for = None
            self._request_preview()

    def _launcher_for(self, game):
        d = self.detection
        launcher = d.launcher if d is not None else None
        if launcher is None or launcher.hwnd == game.hwnd:
            return None
        return launcher

    def confirm(self):
        w = self.shown
        if w is None:
            return
        err = self.svc.confirm_game(w, self._launcher_for(w))
        if err and "mesma janela" in err:
            err = self.svc.confirm_game(w, None)  # o "launcher" era o próprio jogo: guarda só o jogo
        if err:
            self._set_text("Não deu para usar esta janela", err[:1].upper() + err[1:] + ".")
            return
        self.detection = Detection(GAME, w, self._launcher_for(w), confident=True,
                                   same_window=bool(w.parent))
        self.mode = "conectado"
        self._render()

    def use_selected(self):
        if self.shown is not None:
            self.confirm()

    def is_launcher(self):
        w = self.shown
        if w is None:
            return
        self.svc.mark_launcher(w)
        self.rejected.add(w.hwnd)
        self.baseline = None  # o que aparecer a partir de agora é novo
        self.mode = "launcher"
        self.detection = Detection(LAUNCHER_ONLY, None, w)
        self._render()

    def skip_this(self):
        """Não é o jogo nem o launcher (ex.: uma página sobre o jogo): ignora e continua procurando."""
        if self.shown is not None:
            self.rejected.add(self.shown.hwnd)
        self.restart()

    def not_this(self):
        w = self.shown
        if w is not None:
            self.rejected.add(w.hwnd)
            if self.svc.window is not None and self.svc.window.hwnd == w.hwnd:
                self.svc._drop_window("o usuário indicou que não é o jogo")
        self.show_all()

    def show_all(self):
        self.mode = "todas"
        self.list_items = [w for w in self.svc.inventory() if w.hwnd not in self.rejected
                           and w.pid != winapi.own_pid()]
        self.shown = None
        self._render()

    def restart(self):
        self.mode = "procurando"
        self.detection = None
        self.shown = None
        self._next_scan = 0
        self._render()

    # ------------------------------------------------- mostrar com um clique
    def start_pick(self):
        windows = self.svc.inventory(ranked=False)  # antes da camada aparecer: ordem real das janelas
        self.withdraw()
        PickOverlay(self.app, windows, self._picked)

    def _picked(self, w):
        self.deiconify()
        self.lift()
        if w is None:
            self._render()
            return
        self.shown = w
        self.detection = Detection(GAME, w, None)
        self.mode = "confirmar"
        self._preview_for = None
        self._render()


class PickOverlay(tk.Toplevel):
    """Camada semitransparente sobre todos os monitores: destaca a janela sob o mouse.

    O clique fica na camada (não chega ao jogo). Esc ou o botão direito cancelam; depois de
    90 s sem escolha, cancela sozinha.
    """

    TIMEOUT_MS = 90_000

    def __init__(self, app, windows, on_done):
        super().__init__(app.root)
        self.windows, self.on_done = windows, on_done
        self.own = winapi.own_pid()
        vx, vy, vw, vh = winapi.virtual_screen() or (0, 0, self.winfo_screenwidth(), self.winfo_screenheight())
        self.vx, self.vy = vx, vy
        self.overrideredirect(True)
        self.geometry(f"{vw}x{vh}+{vx}+{vy}")
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.35)
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(self, background="#000000", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        f = app.th.fonts["banner"]
        self.canvas.create_text(vw // 2 - (vx if vx < 0 else 0), app.th.px(60), fill="#FFFFFF", font=f,
                                text="Clique sobre a janela do jogo  ·  Esc cancela")
        self.rect = self.canvas.create_rectangle(0, 0, 0, 0, outline="#FFD43B", width=4)
        self.hover = None
        self._done = False
        self.bind("<Motion>", self._move)
        self.bind("<Button-1>", self._click)
        self.bind("<Button-3>", lambda e: self._finish(None))
        self.bind("<Escape>", lambda e: self._finish(None))
        self.after(self.TIMEOUT_MS, lambda: self._finish(None))
        self.after(30, self._grab_focus)

    def _grab_focus(self):
        try:
            self.focus_force()
            self.grab_set()
        except tk.TclError:
            pass

    def _move(self, e):
        w = pick_at(self.windows, e.x_root, e.y_root, self.own)
        self.hover = w
        if w is None:
            self.canvas.coords(self.rect, 0, 0, 0, 0)
            return
        x, y = w.left - self.vx, w.top - self.vy
        self.canvas.coords(self.rect, x, y, x + w.width, y + w.height)

    def _click(self, e):
        self._finish(pick_at(self.windows, e.x_root, e.y_root, self.own))

    def _finish(self, w):
        if self._done:
            return
        self._done = True
        try:
            self.grab_release()
            self.destroy()
        except tk.TclError:
            pass
        self.on_done(w)

