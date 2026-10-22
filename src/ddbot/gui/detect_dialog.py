"""Detectar jogo: acha a janela jogável sozinho e só pede ajuda quando não tem certeza.

Enquanto a janela está aberta a janela principal do JonFlow fica minimizada, para não
cobrir o launcher nem o jogo; ao fechar ela volta como estava. A prévia é capturada da
própria janela do jogo (funciona mesmo com outra janela por cima).

Estados mostrados:
- procurando / launcher aberto: continua procurando a cada segundo e conecta sozinho;
- jogo conectado (evidência forte): mostra a prévia para conferir;
- é esta? (evidência fraca): mostra a prévia e pergunta se é o jogo;
- escolher pela imagem: as janelas candidatas lado a lado, cada uma com a sua prévia;
- apontar com o mouse (exceção): o JonFlow sai da frente, um aviso pequeno no canto conta
  3 segundos e a janela sob o mouse é escolhida, sem clique (nada chega ao jogo). Não existe
  camada escura sobre a tela: nas versões até a 0.4.4 havia uma, e ela cobria o jogo.
"""
from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

import cv2
from PIL import Image, ImageTk

from .. import winapi
from ..capture import WindowCapture
from ..detection import CHOOSE, GAME, LAUNCHER_ONLY, Detection, pick_at
from . import theme as T
from .widgets import ImageCanvas, ScrollFrame

SCAN_EVERY_MS = 1000
GALLERY_MAX = 12        # prévias na galeria (as janelas mais prováveis primeiro)
THUMB_W = 176


def describe_window(w) -> str:
    title = (w.title or "").strip() or "sem título"
    kind = "área interna" if w.parent else "janela"
    return f"{title} ({w.exe or 'programa desconhecido'}, {kind} {w.width}×{w.height})"


def grab_preview(hwnd):
    """Imagem conferida da janela (a mesma captura usada no jogo) ou None."""
    cap = WindowCapture(hwnd)
    try:
        return cap.grab()
    except Exception:
        return None
    finally:
        cap.close()


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
        self._thumbs: "queue.Queue" = queue.Queue()
        self._preview_for = None
        self._thumb_gen = 0
        self._thumb_photos: dict[int, ImageTk.PhotoImage] = {}
        self._cards: dict[int, tuple] = {}
        self.pointer = None

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
        # galeria: cada janela candidata com a sua prévia (escolher olhando a imagem, não o nome)
        self.gallery = ScrollFrame(body, app.th, width=THUMB_W + 40)
        self.gallery.grid(row=0, column=0, sticky="ns", padx=(0, px(12)))
        self.gallery.grid_remove()
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
        if not winapi.IS_WINDOWS and os.environ.get("DDBOT_HEADLESS"):
            # teste automático no Linux (Xvfb sem gerenciador de janelas): minimizar não tem efeito
            # e o Tk fica esperando a resposta do gerenciador; o programa é para Windows
            return
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
        if self.pointer is not None:
            self.pointer.cancel(notify=False)
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
                self.canvas.empty_text = ("Sem prévia: a janela está minimizada, coberta ou não deixa capturar a "
                                          "imagem. Confira olhando a própria janela.")
                self.canvas.show(frame)
        except queue.Empty:
            pass
        self._drain_thumbs()
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
            self.shown = self.list_items[0] if self.list_items else None
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
        point = ("Apontar com o mouse", self.start_point, "TButton", "left")
        gallery = ("Escolher pela imagem", self.show_all, "TButton", "left")
        cancel = ("Fechar", self.close, "TButton", "right")
        can_point = winapi.IS_WINDOWS
        self.gallery.grid_remove()
        if m == "procurando":
            self._set_text("Procurando o jogo...",
                           "Abra o jogo pelo launcher. O JonFlow continua procurando e conecta sozinho quando "
                           "o jogo aparecer. Se o jogo já está aberto e não foi encontrado, clique em Escolher pela "
                           "imagem.")
            self._buttons([gallery] + ([point] if can_point else []) + [cancel])
        elif m == "launcher":
            name = (d.launcher.title or d.launcher.exe) if d and d.launcher else "o launcher"
            self._set_text("Launcher aberto: aguardando o jogo",
                           f"Encontrei {name}, mas o jogo ainda não abriu. Entre no jogo pelo launcher; "
                           "o JonFlow conecta sozinho quando a janela do jogo aparecer.")
            self._buttons([gallery] + ([point] if can_point else []) + [cancel])
        elif m == "conectado":
            where = d.message if d else "Jogo conectado"
            self._set_text("Jogo conectado",
                           f"{where}: {describe_window(self.shown)}. Confira na prévia: ela deve mostrar o jogo "
                           "(lobby, menu ou batalha). Os cliques e teclas vão só para essa área.")
            self._buttons([("Pronto", self.close, "Primary.TButton", "left"),
                           ("Não é esta janela", self.not_this, "TButton", "left"), cancel])
        elif m == "confirmar":
            self._set_text("Esta é a tela do jogo?",
                           f"Encontrei {describe_window(self.shown)}. Se a prévia mostra o jogo (lobby, menu ou "
                           "batalha), confirme. Se mostra o launcher (notícias, botão de jogar), clique em É o "
                           "launcher: o JonFlow espera o jogo abrir. Se é outra coisa, clique em Não é esta.")
            self._buttons([("Sim, é o jogo", self.confirm, "Primary.TButton", "left"),
                           ("É o launcher", self.is_launcher, "TButton", "left"),
                           ("Não é esta", self.skip_this, "TButton", "left"), gallery, cancel])
        elif m in ("escolher", "todas"):
            if m == "escolher":
                self._set_text("Qual destas janelas é o jogo?",
                               "Mais de uma janela parece o jogo. Clique na prévia que mostra o jogo e confira a "
                               "imagem grande antes de usar.")
            else:
                self._set_text("Escolha a janela do jogo pela imagem",
                               "As janelas abertas, com as mais prováveis primeiro. Clique na prévia que mostra o "
                               "jogo e confira a imagem grande antes de usar.")
            self.gallery.grid()
            self._fill_gallery()
            self._buttons([("Usar esta janela", self.use_selected, "Primary.TButton", "left")]
                          + ([point] if can_point else []) + [("Voltar a procurar", self.restart, "TButton", "left"),
                                                              cancel])
        self._request_preview()

    # ------------------------------------------------------------- galeria
    def _fill_gallery(self):
        """Uma prévia por janela candidata; as imagens chegam aos poucos (captura fora da thread do Tk)."""
        inner = self.gallery.inner
        for child in inner.winfo_children():
            child.destroy()
        self._cards.clear()
        self._thumb_photos.clear()
        self._thumb_gen += 1
        gen = self._thumb_gen
        px = self.app.th.px
        items = self.list_items[:GALLERY_MAX]
        if not items:
            ttk.Label(inner, text="Nenhuma janela encontrada.", style="SurfaceMuted.TLabel").grid(sticky="w")
            return
        for i, w in enumerate(items):
            card = tk.Frame(inner, background=T.SURFACE, highlightthickness=2, highlightbackground=T.LINE,
                            cursor="hand2")
            card.grid(row=i, column=0, sticky="we", pady=(0, px(8)))
            pic = tk.Label(card, text="carregando prévia...", background="#2A323C", foreground="#C9D1DA",
                           width=THUMB_W // 8, height=6)
            pic.pack(fill="x")
            cap = tk.Label(card, text=describe_window(w), background=T.SURFACE, foreground=T.INK,
                           wraplength=px(THUMB_W), justify="left", font=self.app.th.fonts["small"])
            cap.pack(fill="x", padx=px(4), pady=px(2))
            for widget in (card, pic, cap):
                widget.bind("<Button-1>", lambda e, w=w: self._select_card(w))
            self._cards[w.hwnd] = (card, pic)
        self._mark_selected()

        def work():
            for w in items:
                if self._closed or gen != self._thumb_gen:
                    return
                frame = grab_preview(w.hwnd)
                self._thumbs.put((gen, w.hwnd, frame))
        threading.Thread(target=work, daemon=True, name="previas-janelas").start()

    def _drain_thumbs(self):
        px = self.app.th.px
        while True:
            try:
                gen, hwnd, frame = self._thumbs.get_nowait()
            except queue.Empty:
                return
            if gen != self._thumb_gen or hwnd not in self._cards:
                continue
            _, pic = self._cards[hwnd]
            if frame is None:
                pic.configure(text="sem prévia\n(coberta ou minimizada)")
                continue
            h, w = frame.shape[:2]
            tw = px(THUMB_W)
            th = max(1, int(h * tw / max(w, 1)))
            rgb = cv2.cvtColor(cv2.resize(frame, (tw, th), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
            photo = ImageTk.PhotoImage(Image.fromarray(rgb))
            self._thumb_photos[hwnd] = photo
            pic.configure(image=photo, text="", width=tw, height=th)

    def _select_card(self, w):
        self.shown = w
        self._preview_for = None
        self._mark_selected()
        self._request_preview()

    def _mark_selected(self):
        for hwnd, (card, _) in self._cards.items():
            on = self.shown is not None and hwnd == self.shown.hwnd
            card.configure(highlightbackground=T.PRIMARY if on else T.LINE)

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
            frame = grab_preview(w.hwnd)
            try:
                self._previews.put_nowait((w.hwnd, frame))
            except queue.Full:
                pass
        threading.Thread(target=work, daemon=True, name="previa-janela").start()

    # --------------------------------------------------------------- ações
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
        self.shown = self.list_items[0] if self.list_items else None
        self._preview_for = None
        self._render()

    def restart(self):
        self.mode = "procurando"
        self.detection = None
        self.shown = None
        self._next_scan = 0
        self._render()

    # ------------------------------------------- apontar com o mouse (exceção)
    def start_point(self):
        """O JonFlow sai da frente; o usuário só aponta o mouse para o jogo (sem clicar) e a janela volta."""
        windows = self.svc.inventory(ranked=False)  # antes do aviso aparecer: ordem real das janelas
        self.withdraw()
        self.pointer = PointerToast(self.app, windows, self._picked)

    def _picked(self, w):
        self.pointer = None
        if self._closed:
            return
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


class PointerToast(tk.Toplevel):
    """Aviso pequeno no canto da tela: conta 3 segundos e escolhe a janela que está sob o mouse.

    Não há clique (nada chega ao jogo) nem camada sobre a tela: só este aviso, que nunca é
    escolhido (é do próprio JonFlow). Mouse sobre o aviso: conta de novo; Cancelar desiste.
    """

    SECONDS = 3
    MAX_TRIES = 3

    def __init__(self, app, windows, on_done, now=time.monotonic):
        super().__init__(app.root)
        self.windows, self.on_done, self.now = windows, on_done, now
        self.own = winapi.own_pid()
        px = app.th.px
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        area = winapi.work_area()
        ax, ay, aw, ah = area or (0, 0, self.winfo_screenwidth(), self.winfo_screenheight())
        w, h = px(400), px(118)
        self.geometry(f"{w}x{h}+{ax + aw - w - px(16)}+{ay + px(16)}")
        box = tk.Frame(self, background=T.SURFACE, highlightthickness=2, highlightbackground=T.PRIMARY)
        box.pack(fill="both", expand=True)
        self.text = tk.Label(box, background=T.SURFACE, foreground=T.INK, font=app.th.fonts["strong"],
                             justify="left", wraplength=w - px(28), anchor="w")
        self.text.pack(fill="x", padx=px(12), pady=(px(10), px(4)))
        ttk.Button(box, text="Cancelar", command=self.cancel).pack(anchor="e", padx=px(12), pady=(0, px(8)))
        self._done = False
        self._tries = 0
        self._start = self.now()
        self._tick()

    def _tick(self):
        if self._done:
            return
        left = self.SECONDS - (self.now() - self._start)
        if left > 0:
            self.text.configure(text=f"Aponte o mouse para a janela do jogo (não precisa clicar). Escolho em "
                                f"{int(left) + 1} s.")
            self.after(100, self._tick)
            return
        x, y = winapi.cursor_pos()
        hit = winapi.window_at(x, y)
        mine = any(w.hwnd == winapi.root_of(hit) and w.pid == self.own for w in self.windows) if hit else False
        if mine or self._over_me(x, y):
            self._tries += 1
            if self._tries >= self.MAX_TRIES:
                self._finish(None)
                return
            self._start = self.now()
            self.text.configure(text="O mouse está sobre este aviso. Aponte para o jogo.")
            self.after(1200, self._tick)
            return
        self._finish(pick_at(self.windows, x, y, self.own, hit=hit, root_of=winapi.root_of))

    def _over_me(self, x, y) -> bool:
        try:
            rx, ry = self.winfo_rootx(), self.winfo_rooty()
            return rx <= x < rx + self.winfo_width() and ry <= y < ry + self.winfo_height()
        except tk.TclError:
            return False

    def cancel(self, notify=True):
        if notify:
            self._finish(None)
        else:
            self._done = True
            self._destroy()

    def _destroy(self):
        try:
            self.destroy()
        except tk.TclError:
            pass

    def _finish(self, w):
        if self._done:
            return
        self._done = True
        self._destroy()
        self.on_done(w)
