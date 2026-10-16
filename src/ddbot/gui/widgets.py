"""Componentes visuais reutilizáveis da interface."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

from . import theme as T


class Panel(ttk.Frame):
    """Área branca com título opcional; o conteúdo vai em ``.body``."""

    def __init__(self, master, th: T.Theme, title: str | None = None, hint: str | None = None, pad: str = "l",
                 **kw):
        super().__init__(master, style="Surface.TFrame", padding=th.px(T.SPACE[pad]), **kw)
        self.columnconfigure(0, weight=1)
        row = 0
        if title:
            ttk.Label(self, text=title, style="SurfaceSection.TLabel").grid(row=row, column=0, sticky="w")
            row += 1
        if hint:
            lbl = ttk.Label(self, text=hint, style="SurfaceMuted.TLabel", wraplength=th.px(420), justify="left")
            lbl.grid(row=row, column=0, sticky="we", pady=(th.px(2), 0))
            # a quebra acompanha a largura do painel (limitada para linhas legíveis, ~90 caracteres)
            self.bind("<Configure>", lambda e, lbl=lbl: lbl.configure(
                wraplength=max(th.px(200), min(e.width - th.px(T.SPACE["l"]) * 2, th.px(760)))), add="+")
            row += 1
        self.body = ttk.Frame(self, style="Surface.TFrame")
        self.body.grid(row=row, column=0, sticky="nsew", pady=(th.px(T.SPACE["s"]) if (title or hint) else 0, 0))
        self.rowconfigure(row, weight=1)
        self.body.columnconfigure(0, weight=1)


class StatusBanner(tk.Frame):
    """Faixa de estado: ícone + título + orientação. Cor, ícone e texto mudam juntos."""

    def __init__(self, master, th: T.Theme):
        super().__init__(master, background=T.STATE_STYLES["idle"][0])
        self.th = th
        pad = th.px(T.SPACE["l"])
        self.icon = tk.Label(self, font=th.fonts["banner"], width=2, anchor="center")
        self.icon.pack(side="left", padx=(pad, th.px(4)), pady=th.px(8))
        box = tk.Frame(self)
        box.pack(side="left", fill="x", expand=True, pady=th.px(6))
        self.title = tk.Label(box, font=th.fonts["banner"], anchor="w", justify="left")
        self.title.pack(fill="x")
        self.detail = tk.Label(box, font=th.fonts["body"], anchor="w", justify="left")
        self.detail.pack(fill="x")
        self._box = box
        self.kind = None
        self.set("idle", "", "")
        self.bind("<Configure>", lambda e: self._wrap(e.width))

    def _wrap(self, width):
        w = max(200, width - self.th.px(90))
        self.title.configure(wraplength=w)
        self.detail.configure(wraplength=w)

    def set(self, kind: str, title: str, detail: str = ""):
        bg, fg, icon = T.STATE_STYLES.get(kind, T.STATE_STYLES["idle"])
        if (kind, title, detail) == getattr(self, "_last", None):
            return
        self._last = (kind, title, detail)
        self.kind = kind
        for w in (self, self._box, self.icon, self.title, self.detail):
            w.configure(background=bg)
        for w in (self.icon, self.title, self.detail):
            w.configure(foreground=fg)
        self.icon.configure(text=icon)
        self.title.configure(text=title)
        self.detail.configure(text=detail)


class Readout(ttk.Frame):
    """Número grande de instrumento com rótulo pequeno (ângulo, força, vento)."""

    def __init__(self, master, th: T.Theme, label: str, unit: str = ""):
        super().__init__(master, style="Surface.TFrame")
        ttk.Label(self, text=label, style="SurfaceMuted.TLabel").pack(anchor="w")
        self.value = ttk.Label(self, text="—", style="Readout.TLabel")
        self.value.pack(anchor="w")
        self.unit = unit

    def set(self, value: str | None):
        self.value.configure(text="—" if value is None else f"{value}{self.unit}")


class Counter(ttk.Frame):
    def __init__(self, master, th: T.Theme, label: str):
        super().__init__(master, style="Surface.TFrame")
        self.value = ttk.Label(self, text="0", style="Count.TLabel")
        self.value.pack(anchor="w")
        ttk.Label(self, text=label, style="SurfaceMuted.TLabel").pack(anchor="w")

    def set(self, n):
        self.value.configure(text=str(n))


class ScrollFrame(ttk.Frame):
    """Coluna com rolagem vertical (para painéis que não cabem em telas baixas)."""

    def __init__(self, master, th: T.Theme, width: int, style="Surface.TFrame"):
        super().__init__(master, style=style)
        self.canvas = tk.Canvas(self, highlightthickness=0, background=T.SURFACE, width=th.px(width))
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, style=style, padding=th.px(T.SPACE["m"]))
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        for w in (self.canvas, self.inner):
            w.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
            w.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")


class ImageCanvas(tk.Canvas):
    """Mostra uma imagem BGR ajustada ao tamanho e permite selecionar um retângulo."""

    def __init__(self, master, empty_text: str, on_select=None, **kw):
        super().__init__(master, background="#2A323C", highlightthickness=0, **kw)
        self.on_select = on_select
        self.empty_text = empty_text
        self.frame: np.ndarray | None = None
        self._photo = None
        self._scale, self._off = 1.0, (0, 0)
        self._start = None
        self._rect_id = None
        self.selection_px: tuple[int, int, int, int] | None = None
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)

    def show(self, frame: np.ndarray | None, keep_selection=False):
        self.frame = frame
        if not keep_selection:
            self.selection_px = None
        self.redraw()

    def redraw(self):
        self.delete("all")
        self._rect_id = None
        cw, ch = max(1, self.winfo_width()), max(1, self.winfo_height())
        if self.frame is None:
            self.create_text(cw // 2, ch // 2, fill="#C9D1DA", text=self.empty_text, width=max(100, cw - 40),
                             justify="center")
            return
        h, w = self.frame.shape[:2]
        self._scale = min(cw / w, ch / h)
        nw, nh = max(1, int(w * self._scale)), max(1, int(h * self._scale))
        self._off = ((cw - nw) // 2, (ch - nh) // 2)
        rgb = cv2.cvtColor(cv2.resize(self.frame, (nw, nh), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
        self._photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.create_image(self._off[0], self._off[1], anchor="nw", image=self._photo)
        if self.selection_px:
            x, y, sw, sh = self.selection_px
            a, b = self._to_canvas(x, y)
            c, d = self._to_canvas(x + sw, y + sh)
            self._rect_id = self.create_rectangle(a, b, c, d, outline="#4FD18B", width=2)

    def _to_canvas(self, x, y):
        return self._off[0] + x * self._scale, self._off[1] + y * self._scale

    def _to_frame(self, cx, cy):
        h, w = self.frame.shape[:2]
        x = (cx - self._off[0]) / self._scale
        y = (cy - self._off[1]) / self._scale
        return int(min(max(0, x), w - 1)), int(min(max(0, y), h - 1))

    def _press(self, e):
        if self.frame is None:
            return
        self._start = (e.x, e.y)
        if self._rect_id:
            self.delete(self._rect_id)
        self._rect_id = self.create_rectangle(e.x, e.y, e.x, e.y, outline="#4FD18B", width=2)

    def _drag(self, e):
        if self._start and self._rect_id:
            self.coords(self._rect_id, self._start[0], self._start[1], e.x, e.y)

    def _release(self, e):
        if not self._start or self.frame is None:
            return
        x0, y0 = self._to_frame(*self._start)
        x1, y1 = self._to_frame(e.x, e.y)
        self._start = None
        x, y, w, h = min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)
        if w < 3 or h < 3:
            return
        self.selection_px = (x, y, w, h)
        if self.on_select:
            self.on_select(self.selection_px)

    def selection_image(self) -> np.ndarray | None:
        if self.frame is None or not self.selection_px:
            return None
        x, y, w, h = self.selection_px
        return self.frame[y:y + h, x:x + w].copy()
