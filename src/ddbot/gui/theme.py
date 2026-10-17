"""Sistema visual do JonFlow: cores, tipografia, espaçamento e estilos ttk.

Direção: painel de instrumento de pontaria. Fundo frio e neutro, um azul-aço para a
ação principal, latão só nos números da mira e cores de estado sempre acompanhadas
de ícone e texto (nunca só a cor).
"""
from __future__ import annotations

import os

# ----------------------------------------------------------------- cores
BG = "#EEF1F4"         # fundo da janela
SURFACE = "#FFFFFF"    # painéis
LINE = "#D5DBE2"       # divisórias e bordas de campos
INK = "#1D2733"        # texto principal
MUTED = "#5B6876"      # texto secundário (contraste 5,6:1 sobre BG)
PRIMARY = "#1F5FAD"    # ação principal (Iniciar)
PRIMARY_HOVER = "#184C8B"
BRASS = "#8A5E00"      # números da mira (contraste 6,0:1 sobre branco)
FOCUS = "#1F5FAD"

# estados: (fundo da faixa, texto da faixa, ícone)
STATE_STYLES = {
    "idle": ("#E2E7ED", INK, "○"),
    "ready": ("#DCE8F7", "#123A69", "●"),
    "running": ("#DDF0E5", "#14532F", "▶"),
    "combat": ("#DDF0E5", "#14532F", "◎"),
    "paused": ("#FBEBCB", "#6B4300", "❚❚"),
    "done": ("#DCE8F7", "#123A69", "✓"),
    "warning": ("#FBEBCB", "#6B4300", "!"),
    "error": ("#F8DEDC", "#7A1A14", "✕"),
    "emergency": ("#B3261E", "#FFFFFF", "■"),
}
RESULT_COLORS = {"erro": "#B3261E", "aviso": "#8A5600", "resultado": "#1F7A4D"}

# ------------------------------------------------------------ espaçamento
SPACE = {"xs": 4, "s": 8, "m": 12, "l": 16, "xl": 24}


def _family(candidates, fallback):
    import tkinter.font as tkfont
    available = {f.lower() for f in tkfont.families()}
    for c in candidates:
        if c.lower() in available:
            return c
    return fallback


class Theme:
    """Aplica o estilo e guarda fontes e fator de escala (DPI)."""

    def __init__(self, root):
        import tkinter.font as tkfont
        self.root = root
        self.scale = self._detect_scale()
        body = _family(["Segoe UI", "Noto Sans", "DejaVu Sans"], "TkDefaultFont")
        display = _family(["Bahnschrift", "Segoe UI Semibold", "DejaVu Sans Condensed", "DejaVu Sans"], body)
        self.fonts = {
            "body": tkfont.Font(root, family=body, size=10),
            "small": tkfont.Font(root, family=body, size=9),
            "strong": tkfont.Font(root, family=body, size=10, weight="bold"),
            "section": tkfont.Font(root, family=display, size=12, weight="bold"),
            "banner": tkfont.Font(root, family=display, size=14, weight="bold"),
            "readout": tkfont.Font(root, family=display, size=24, weight="bold"),
            "count": tkfont.Font(root, family=display, size=20, weight="bold"),
            "button": tkfont.Font(root, family=body, size=10, weight="bold"),
            "mono": tkfont.Font(root, family=_family(["Consolas", "DejaVu Sans Mono"], "TkFixedFont"), size=9),
        }
        self._apply()

    def _detect_scale(self) -> float:
        override = os.environ.get("DDBOT_UI_SCALE")
        if override:
            try:
                s = float(override)
                # faz o Tk converter pontos em pixels como num monitor com essa escala
                self.root.tk.call("tk", "scaling", 96 * s / 72)
                return s
            except ValueError:
                pass
        import tkinter as tk
        try:
            return max(1.0, float(self.root.winfo_fpixels("1i")) / 96.0)
        except tk.TclError:
            return 1.0

    def px(self, value: float) -> int:
        """Converte um tamanho de projeto (em 100%) para pixels reais."""
        return int(round(value * self.scale))

    def _apply(self):
        from tkinter import ttk
        import tkinter.font as tkfont
        r, f, px = self.root, self.fonts, self.px
        r.configure(background=BG)
        # fontes padrão pelos nomes do Tk: option_add("*Font") forçaria a fonte em cada widget e
        # anularia as fontes dos estilos (títulos, contadores e números da mira ficavam pequenos)
        body = f["body"].actual()
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
            try:
                tkfont.nametofont(name).configure(family=body["family"], size=body["size"])
            except Exception:
                pass
        r.option_add("*TCombobox*Listbox.font", f["body"])
        r.option_add("*TCombobox*Listbox.selectBackground", PRIMARY)
        st = ttk.Style(r)
        st.theme_use("clam")  # único tema que aceita as cores em todos os sistemas
        st.configure(".", background=BG, foreground=INK, font=f["body"], bordercolor=LINE,
                     lightcolor=BG, darkcolor=BG, troughcolor=LINE, focuscolor=FOCUS,
                     selectbackground=PRIMARY, selectforeground="#FFFFFF", insertcolor=INK)
        st.configure("TFrame", background=BG)
        st.configure("Surface.TFrame", background=SURFACE)
        st.configure("TLabel", background=BG, foreground=INK)
        st.configure("Surface.TLabel", background=SURFACE)
        st.configure("Muted.TLabel", foreground=MUTED, font=f["small"])
        st.configure("SurfaceMuted.TLabel", background=SURFACE, foreground=MUTED, font=f["small"])
        st.configure("Section.TLabel", font=f["section"])
        st.configure("SurfaceSection.TLabel", background=SURFACE, font=f["section"])
        st.configure("Readout.TLabel", background=SURFACE, foreground=BRASS, font=f["readout"])
        st.configure("Count.TLabel", background=SURFACE, foreground=INK, font=f["count"])
        st.configure("Strong.TLabel", background=SURFACE, font=f["strong"])
        st.configure("Error.TLabel", foreground="#B3261E", font=f["strong"])
        st.configure("SurfaceError.TLabel", background=SURFACE, foreground="#B3261E", font=f["strong"])
        # botões: secundário, principal e crítico
        pad = (px(14), px(7))
        st.configure("TButton", background=SURFACE, foreground=INK, bordercolor=LINE, lightcolor=SURFACE,
                     darkcolor=SURFACE, padding=pad, font=f["body"], focusthickness=2)
        st.map("TButton", background=[("disabled", BG), ("pressed", "#E3E8EE"), ("active", "#F4F6F9")],
               foreground=[("disabled", "#9AA5B1")], bordercolor=[("focus", FOCUS)])
        st.configure("Primary.TButton", background=PRIMARY, foreground="#FFFFFF", bordercolor=PRIMARY,
                     lightcolor=PRIMARY, darkcolor=PRIMARY, font=f["button"], padding=(px(22), px(10)))
        st.map("Primary.TButton", background=[("disabled", "#A9BCD3"), ("pressed", PRIMARY_HOVER),
                                              ("active", PRIMARY_HOVER)],
               foreground=[("disabled", "#F2F5F9")], bordercolor=[("focus", "#0E2F57")])
        st.configure("Danger.TButton", background=SURFACE, foreground="#B3261E", bordercolor="#B3261E",
                     font=f["button"], padding=pad)
        st.map("Danger.TButton", background=[("disabled", BG), ("active", "#FBEDEC")],
               foreground=[("disabled", "#C9A9A6")], bordercolor=[("disabled", LINE)])
        # seletor de fluxo (Instâncias | Partidas)
        st.configure("Segment.TRadiobutton", background=SURFACE, foreground=MUTED, font=f["button"],
                     padding=(px(16), px(8)), indicatorsize=0, borderwidth=1, relief="flat")
        st.map("Segment.TRadiobutton", background=[("selected", "#DCE8F7"), ("active", "#F4F6F9")],
               foreground=[("selected", "#123A69")])
        st.layout("Segment.TRadiobutton", [("Radiobutton.padding", {"sticky": "nswe", "children": [
            ("Radiobutton.focus", {"sticky": "nswe", "children": [("Radiobutton.label", {"sticky": "nswe"})]})]})])
        st.configure("TRadiobutton", background=BG)
        st.configure("Surface.TRadiobutton", background=SURFACE)
        st.configure("TCheckbutton", background=BG)
        st.configure("Surface.TCheckbutton", background=SURFACE)
        st.configure("TEntry", fieldbackground=SURFACE, padding=px(4))
        st.configure("TSpinbox", fieldbackground=SURFACE, padding=px(3), arrowsize=px(12))
        st.configure("TCombobox", fieldbackground=SURFACE, padding=px(4), arrowsize=px(14))
        st.map("TCombobox", fieldbackground=[("readonly", SURFACE)], foreground=[("readonly", INK)],
               selectbackground=[("readonly", SURFACE)], selectforeground=[("readonly", INK)])
        st.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(px(8), px(6), px(8), 0))
        st.configure("TNotebook.Tab", background=BG, foreground=MUTED, padding=(px(16), px(7)), borderwidth=0,
                     font=f["body"])
        st.map("TNotebook.Tab", background=[("selected", SURFACE)], foreground=[("selected", INK)],
               font=[("selected", f["strong"])])
        st.configure("Sub.TNotebook", background=SURFACE)
        st.configure("Sub.TNotebook.Tab", background=SURFACE, padding=(px(10), px(5)))
        st.map("Sub.TNotebook.Tab", background=[("selected", "#DCE8F7")])
        st.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=INK,
                     rowheight=px(24), bordercolor=LINE, font=f["body"])
        st.configure("Treeview.Heading", background=BG, foreground=MUTED, font=f["small"], relief="flat",
                     padding=(px(6), px(4)))
        st.map("Treeview", background=[("selected", "#DCE8F7")], foreground=[("selected", INK)])
        st.configure("Horizontal.TProgressbar", background=PRIMARY, troughcolor="#E2E7ED", bordercolor="#E2E7ED",
                     lightcolor=PRIMARY, darkcolor=PRIMARY, thickness=px(10))
        st.configure("TLabelframe", background=SURFACE, bordercolor=LINE)
        st.configure("TLabelframe.Label", background=SURFACE, foreground=INK, font=f["strong"])
        st.configure("Vertical.TScrollbar", background=BG, troughcolor=SURFACE, bordercolor=SURFACE,
                     arrowsize=px(12))
