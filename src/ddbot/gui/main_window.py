"""Interface gráfica (Tkinter) em português.

A interface nunca faz trabalho pesado na thread principal: captura, análise e
automação rodam em threads e os resultados chegam por filas lidas a cada 200 ms.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

from .. import __version__
from ..activities import CATEGORIES, COMMON_TEMPLATES, ActivityDef, RunStatus, activity_from_option, slug
from ..log import LOG_QUEUE
from ..service import BotService
from ..vision.menu import detect_option_tiles, find_known_options
from ..vision.perception import REGION_KEYS, STATE_LABELS, STATES, draw_overlay
from ..vision.regions import px_to_frac

log = logging.getLogger(__name__)

DEMO_KEY = "__demonstracao__"
KIND_LABELS = {"partida": "Partida", "instancia": "Instância"}
STATUS_LABELS = {RunStatus.IDLE: "Parado", RunStatus.RUNNING: "Executando", RunStatus.PAUSED: "Pausado",
                 RunStatus.FINISHED: "Concluído", RunStatus.FAILED: "Interrompido"}


def demo_activity(kind: str) -> ActivityDef:
    d = activity_from_option(f"{kind}_teste", f"Demonstração simulada ({KIND_LABELS[kind].lower()})", kind, "pve")
    d.key = DEMO_KEY + kind
    d.description = "Simulação interna: não usa o jogo. Serve para conhecer a interface."
    return d


class ImageCanvas(tk.Canvas):
    """Mostra uma imagem BGR ajustada ao tamanho e permite selecionar um retângulo."""

    def __init__(self, master, on_select=None, **kw):
        super().__init__(master, background="#202020", highlightthickness=0, **kw)
        self.on_select = on_select
        self.frame: np.ndarray | None = None
        self._photo = None
        self._scale, self._off = 1.0, (0, 0)
        self._start = None
        self._rect_id = None
        self.selection_px: tuple[int, int, int, int] | None = None
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)

    def show(self, frame: np.ndarray | None, keep_selection=False):
        self.frame = frame
        if not keep_selection:
            self.selection_px = None
        self._redraw()

    def _redraw(self):
        self.delete("all")
        if self.frame is None:
            self.create_text(self.winfo_width() // 2, self.winfo_height() // 2, fill="#bbbbbb",
                             text="Sem imagem. Selecione a janela do jogo e clique em Capturar.")
            return
        h, w = self.frame.shape[:2]
        cw, ch = max(1, self.winfo_width()), max(1, self.winfo_height())
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
            self._rect_id = self.create_rectangle(a, b, c, d, outline="#00ff66", width=2)

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
        self._rect_id = self.create_rectangle(e.x, e.y, e.x, e.y, outline="#00ff66", width=2)

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


class MainWindow:
    def __init__(self, root: tk.Tk, service: BotService):
        self.root = root
        self.svc = service
        self.windows = []
        self.activities: dict[str, ActivityDef] = {}
        self.live_diag = tk.BooleanVar(value=False)
        self.simulated = tk.BooleanVar(value=False)
        self._diag_queue: "queue.Queue[tuple]" = queue.Queue(maxsize=2)
        self._diag_busy = False
        self._tiles: list = []
        self._closing = False
        root.title(f"DDClássico Bot {__version__}")
        root.geometry("1180x760")
        root.minsize(980, 640)
        self._style()
        self._build_top()
        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.nb = nb
        self.tab_home = ttk.Frame(nb, padding=8)
        self.tab_calib = ttk.Frame(nb, padding=8)
        self.tab_diag = ttk.Frame(nb, padding=8)
        self.tab_aim = ttk.Frame(nb, padding=8)
        self.tab_cfg = ttk.Frame(nb, padding=8)
        self.tab_log = ttk.Frame(nb, padding=8)
        for tab, text in ((self.tab_home, "Início"), (self.tab_calib, "Calibração"),
                          (self.tab_diag, "Diagnóstico"), (self.tab_aim, "Mira e disparos"),
                          (self.tab_cfg, "Configurações"), (self.tab_log, "Registro técnico")):
            nb.add(tab, text=text)
        self._build_home()
        self._build_calibration()
        self._build_diagnostics()
        self._build_aim()
        self._build_config()
        self._build_log()
        self.refresh_windows()
        self.refresh_activities()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(200, self._tick)

    # ------------------------------------------------------------------ visual
    def _style(self):
        st = ttk.Style(self.root)
        try:
            st.theme_use("vista" if os.name == "nt" else "clam")
        except tk.TclError:
            pass
        st.configure("Big.TButton", font=("Segoe UI", 11, "bold"), padding=(14, 8))
        st.configure("Value.TLabel", font=("Segoe UI", 10, "bold"))
        st.configure("Head.TLabel", font=("Segoe UI", 12, "bold"))
        st.configure("Warn.TLabel", foreground="#b00020")

    def _build_top(self):
        top = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Janela do jogo:").pack(side="left")
        self.cb_window = ttk.Combobox(top, state="readonly", width=60)
        self.cb_window.pack(side="left", padx=4)
        self.cb_window.bind("<<ComboboxSelected>>", lambda e: self.select_window())
        ttk.Button(top, text="Atualizar", command=self.refresh_windows).pack(side="left")
        self.all_windows = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="mostrar todas as janelas", variable=self.all_windows,
                        command=self.refresh_windows).pack(side="left", padx=6)
        self.lbl_window = ttk.Label(top, text="nenhuma janela selecionada", style="Warn.TLabel")
        self.lbl_window.pack(side="left", padx=8)
        ttk.Checkbutton(top, text="Demonstração (simulada, não usa o jogo)", variable=self.simulated,
                        command=self.refresh_activities).pack(side="right")

    # ------------------------------------------------------------------- Início
    def _build_home(self):
        t = self.tab_home
        t.columnconfigure(0, weight=1)
        t.columnconfigure(1, weight=1)
        t.rowconfigure(2, weight=1)
        self.area = tk.StringVar(value="instancia")
        left = ttk.Frame(t)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        f1 = ttk.LabelFrame(left, text="Partidas automáticas", padding=8)
        f1.pack(fill="x")
        ttk.Radiobutton(f1, text="Jogar partidas", value="partida", variable=self.area).grid(row=0, column=0, sticky="w")
        self.cb_match = ttk.Combobox(f1, state="readonly", width=46)
        self.cb_match.grid(row=1, column=0, sticky="we", pady=4)
        self.cb_match.bind("<<ComboboxSelected>>", lambda e: (self.area.set("partida"), self._describe()))
        f2 = ttk.LabelFrame(left, text="Instâncias", padding=8)
        f2.pack(fill="x", pady=(8, 0))
        ttk.Radiobutton(f2, text="Jogar instância", value="instancia", variable=self.area).grid(row=0, column=0, sticky="w")
        self.cb_inst = ttk.Combobox(f2, state="readonly", width=46)
        self.cb_inst.grid(row=1, column=0, sticky="we", pady=4)
        self.cb_inst.bind("<<ComboboxSelected>>", lambda e: (self.area.set("instancia"), self._describe()))
        self.lbl_desc = ttk.Label(left, text="", wraplength=470, justify="left")
        self.lbl_desc.pack(fill="x", pady=(6, 0))
        ttk.Label(left, text="As opções aparecem depois de capturadas do menu do jogo em Calibração > "
                  "Opções do menu.", wraplength=470, foreground="#555").pack(fill="x", pady=(2, 0))

        runs = ttk.LabelFrame(left, text="Execuções", padding=8)
        runs.pack(fill="x", pady=(8, 0))
        self.run_mode = tk.StringVar(value="uma")
        self.run_count = tk.IntVar(value=5)
        ttk.Radiobutton(runs, text="Uma vez", value="uma", variable=self.run_mode).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(runs, text="Quantidade:", value="qtd", variable=self.run_mode).grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Spinbox(runs, from_=1, to=999, textvariable=self.run_count, width=6).grid(row=0, column=2, padx=4)
        ttk.Radiobutton(runs, text="Contínuo (até parar)", value="cont", variable=self.run_mode).grid(row=0, column=3, sticky="w", padx=(12, 0))

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=10)
        self.btn_start = ttk.Button(btns, text="▶ Iniciar", style="Big.TButton", command=self.start)
        self.btn_pause = ttk.Button(btns, text="⏸ Pausar", style="Big.TButton", command=self.pause)
        self.btn_resume = ttk.Button(btns, text="⏵ Retomar", style="Big.TButton", command=self.resume)
        self.btn_stop = ttk.Button(btns, text="■ Parar", style="Big.TButton", command=self.stop)
        for b in (self.btn_start, self.btn_pause, self.btn_resume, self.btn_stop):
            b.pack(side="left", padx=(0, 6))
        hk = self.svc.config.get("safety.emergency_hotkey", "<f12>").strip("<>").upper()
        ttk.Label(left, text=f"Parada de emergência: tecla {hk} (funciona com o jogo em foco).",
                  style="Warn.TLabel").pack(anchor="w")

        right = ttk.LabelFrame(t, text="Situação", padding=8)
        right.grid(row=0, column=1, sticky="nsew")
        self.vals: dict[str, ttk.Label] = {}
        rows = [("status", "Status"), ("etapa", "Etapa atual"), ("progresso", "Progresso"),
                ("turno", "Turno"), ("alvo", "Alvo"), ("angulo", "Ângulo"), ("forca", "Força"),
                ("vento", "Vento"), ("sugestao", "Sugestão de mira"), ("motivo", "Último aviso")]
        for i, (k, label) in enumerate(rows):
            ttk.Label(right, text=label + ":").grid(row=i, column=0, sticky="nw", pady=1)
            v = ttk.Label(right, text="—", style="Value.TLabel", wraplength=380, justify="left")
            v.grid(row=i, column=1, sticky="w", pady=1)
            self.vals[k] = v
        self.progress = ttk.Progressbar(right, length=300, mode="determinate")
        self.progress.grid(row=len(rows), column=0, columnspan=2, sticky="we", pady=6)
        cnt = ttk.Frame(right)
        cnt.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w")
        self.counters = {}
        for i, (k, label) in enumerate((("vitorias", "Vitórias"), ("derrotas", "Derrotas"),
                                        ("concluidas", "Concluídas"), ("batalhas", "Batalhas"))):
            ttk.Label(cnt, text=label).grid(row=0, column=i, padx=8)
            v = ttk.Label(cnt, text="0", style="Head.TLabel")
            v.grid(row=1, column=i, padx=8)
            self.counters[k] = v

        hist = ttk.LabelFrame(t, text="Histórico (partidas, instâncias, resultados e erros)", padding=4)
        hist.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        self.tree_hist = ttk.Treeview(hist, columns=("hora", "tipo", "msg"), show="headings", height=8)
        for col, text, w in (("hora", "Hora", 80), ("tipo", "Tipo", 90), ("msg", "Mensagem", 900)):
            self.tree_hist.heading(col, text=text)
            self.tree_hist.column(col, width=w, stretch=col == "msg")
        self.tree_hist.tag_configure("erro", foreground="#b00020")
        self.tree_hist.tag_configure("aviso", foreground="#a65e00")
        self.tree_hist.tag_configure("resultado", foreground="#006b2e")
        sb = ttk.Scrollbar(hist, orient="vertical", command=self.tree_hist.yview)
        self.tree_hist.configure(yscrollcommand=sb.set)
        self.tree_hist.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._update_buttons()

    # -------------------------------------------------------------- Calibração
    def _build_calibration(self):
        t = self.tab_calib
        t.columnconfigure(0, weight=1)
        t.rowconfigure(0, weight=1)
        self.calib_canvas = ImageCanvas(t, on_select=self._on_calib_select)
        self.calib_canvas.grid(row=0, column=0, sticky="nsew")
        side = ttk.Frame(t, padding=(8, 0, 0, 0))
        side.grid(row=0, column=1, sticky="ns")
        ttk.Button(side, text="📷 Capturar tela do jogo", command=self.calib_capture).pack(fill="x")
        ttk.Label(side, text="Arraste com o mouse sobre a imagem para selecionar.", wraplength=300).pack(fill="x", pady=4)

        fr = ttk.LabelFrame(side, text="1. Regiões da tela", padding=6)
        fr.pack(fill="x", pady=4)
        self.cb_region = ttk.Combobox(fr, state="readonly", values=[f"{k} — {v}" for k, v in REGION_KEYS.items()], width=40)
        self.cb_region.current(0)
        self.cb_region.pack(fill="x")
        ttk.Button(fr, text="Salvar seleção como região", command=self.save_region).pack(fill="x", pady=2)

        ft = ttk.LabelFrame(side, text="2. Modelos (telas, botões, marcadores)", padding=6)
        ft.pack(fill="x", pady=4)
        tpl_values = [f"estado_{s} — Tela: {STATE_LABELS.get(s, s)}" for s in STATES] + \
                     [f"{k} — {v}" for k, v in COMMON_TEMPLATES.items()]
        self.cb_tpl = ttk.Combobox(ft, state="readonly", values=tpl_values, width=40)
        self.cb_tpl.current(0)
        self.cb_tpl.pack(fill="x")
        ttk.Button(ft, text="Salvar seleção como modelo", command=self.save_template).pack(fill="x", pady=2)
        self.lbl_tpl = ttk.Label(ft, text="", wraplength=300, foreground="#555")
        self.lbl_tpl.pack(fill="x")

        fd = ttk.LabelFrame(side, text="3. Números (ângulo e vento)", padding=6)
        fd.pack(fill="x", pady=4)
        self.digit_kind = tk.StringVar(value="angle")
        ttk.Radiobutton(fd, text="Ângulo", value="angle", variable=self.digit_kind).grid(row=0, column=0)
        ttk.Radiobutton(fd, text="Vento", value="wind", variable=self.digit_kind).grid(row=0, column=1)
        ttk.Label(fd, text="Valor mostrado:").grid(row=1, column=0, sticky="w")
        self.digit_value = ttk.Entry(fd, width=8)
        self.digit_value.grid(row=1, column=1, sticky="w")
        ttk.Button(fd, text="Aprender da região", command=self.learn_digits).grid(row=2, column=0, columnspan=2, sticky="we", pady=2)

        fo = ttk.LabelFrame(side, text="4. Opções do menu (instâncias/partidas)", padding=6)
        fo.pack(fill="x", pady=4)
        ttk.Label(fo, text="Abra no jogo o menu com as opções, capture e clique em Detectar.", wraplength=300).pack(fill="x")
        ttk.Button(fo, text="Detectar opções na captura", command=self.detect_options).pack(fill="x", pady=2)
        self.lst_tiles = tk.Listbox(fo, height=5, exportselection=False)
        self.lst_tiles.pack(fill="x")
        self.lst_tiles.bind("<<ListboxSelect>>", self._on_tile_select)
        g = ttk.Frame(fo)
        g.pack(fill="x", pady=2)
        ttk.Label(g, text="Nome:").grid(row=0, column=0, sticky="w")
        self.opt_name = ttk.Entry(g, width=24)
        self.opt_name.grid(row=0, column=1, sticky="we")
        ttk.Label(g, text="Tipo:").grid(row=1, column=0, sticky="w")
        self.opt_kind = ttk.Combobox(g, state="readonly", values=["instancia", "partida"], width=22)
        self.opt_kind.current(0)
        self.opt_kind.grid(row=1, column=1, sticky="we")
        ttk.Label(g, text="Categoria:").grid(row=2, column=0, sticky="w")
        self.opt_cat = ttk.Combobox(g, state="readonly", values=list(CATEGORIES), width=22)
        self.opt_cat.current(0)
        self.opt_cat.grid(row=2, column=1, sticky="we")
        ttk.Button(fo, text="Criar atividade com a opção/seleção", command=self.create_option).pack(fill="x", pady=2)
        ttk.Button(fo, text="Quais opções conhecidas estão visíveis?", command=self.check_visible_options).pack(fill="x")
        ttk.Button(side, text="Excluir atividade selecionada no Início", command=self.delete_activity).pack(fill="x", pady=(8, 0))

    # ------------------------------------------------------------- Diagnóstico
    def _build_diagnostics(self):
        t = self.tab_diag
        t.columnconfigure(0, weight=1)
        t.rowconfigure(1, weight=1)
        bar = ttk.Frame(t)
        bar.grid(row=0, column=0, columnspan=2, sticky="we")
        ttk.Button(bar, text="Analisar agora", command=self.diag_once).pack(side="left")
        ttk.Checkbutton(bar, text="Ao vivo", variable=self.live_diag).pack(side="left", padx=8)
        ttk.Button(bar, text="Salvar captura", command=self.save_capture).pack(side="left")
        self.assist_on = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Mira assistida ao vivo (só sugere, não joga)", variable=self.assist_on,
                        command=self.toggle_assist).pack(side="left", padx=12)
        self.diag_canvas = ImageCanvas(t)
        self.diag_canvas.grid(row=1, column=0, sticky="nsew", pady=4)
        self.txt_diag = tk.Text(t, width=48, wrap="word", font=("Consolas", 9))
        self.txt_diag.grid(row=1, column=1, sticky="ns", padx=(6, 0), pady=4)

    # -------------------------------------------------------------------- Mira
    def _build_aim(self):
        t = self.tab_aim
        t.columnconfigure(1, weight=1)
        t.rowconfigure(1, weight=1)
        calc = ttk.LabelFrame(t, text="Calculadora", padding=8)
        calc.grid(row=0, column=0, sticky="nw")
        self.aim_inputs = {}
        for i, (k, label, default) in enumerate((("distance", "Distância (1/10 da tela)", "10"),
                                                 ("wind", "Vento (+ a favor)", "0"),
                                                 ("dy", "Altura do alvo (+ acima)", "0"))):
            ttk.Label(calc, text=label).grid(row=i, column=0, sticky="w")
            e = ttk.Entry(calc, width=8)
            e.insert(0, default)
            e.grid(row=i, column=1, padx=4, pady=1)
            self.aim_inputs[k] = e
        ttk.Button(calc, text="Calcular", command=self.calc_aim).grid(row=3, column=0, columnspan=2, sticky="we", pady=4)
        self.tree_aim = ttk.Treeview(t, columns=("met", "ang", "for", "p", "base"), show="headings", height=8)
        for col, text, w in (("met", "Método", 80), ("ang", "Ângulo", 60), ("for", "Força", 60),
                             ("p", "Prob. acerto", 90), ("base", "Base", 500)):
            self.tree_aim.heading(col, text=text)
            self.tree_aim.column(col, width=w, stretch=col == "base")
        self.tree_aim.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        shots = ttk.LabelFrame(t, text="Disparos registrados (marque o resultado para calibrar)", padding=6)
        shots.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        shots.columnconfigure(0, weight=1)
        shots.rowconfigure(0, weight=1)
        self.tree_shots = ttk.Treeview(shots, columns=("id", "ang", "for", "vento", "dist", "imp", "res", "met", "modo"),
                                       show="headings", height=8)
        for col, text, w in (("id", "#", 40), ("ang", "Ângulo", 60), ("for", "Força", 60), ("vento", "Vento", 60),
                             ("dist", "Distância", 70), ("imp", "Impacto", 70), ("res", "Resultado", 80),
                             ("met", "Método", 80), ("modo", "Modo", 90)):
            self.tree_shots.heading(col, text=text)
            self.tree_shots.column(col, width=w)
        self.tree_shots.grid(row=0, column=0, columnspan=6, sticky="nsew")
        ttk.Button(shots, text="Acertou", command=lambda: self.mark_shot(True)).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Button(shots, text="Errou", command=lambda: self.mark_shot(False)).grid(row=1, column=1, sticky="w")
        ttk.Label(shots, text="Impacto (distância onde caiu):").grid(row=1, column=2, sticky="e")
        self.impact_entry = ttk.Entry(shots, width=8)
        self.impact_entry.grid(row=1, column=3, sticky="w")
        ttk.Button(shots, text="Salvar impacto", command=self.mark_impact).grid(row=1, column=4, sticky="w")
        ttk.Button(shots, text="Reajustar modelo com os disparos", command=self.refit).grid(row=1, column=5, sticky="e")
        self.lbl_stats = ttk.Label(shots, text="", wraplength=1000)
        self.lbl_stats.grid(row=2, column=0, columnspan=6, sticky="w")
        self.refresh_shots()

    # ---------------------------------------------------------- Configurações
    def _build_config(self):
        t = self.tab_cfg
        c = self.svc.config
        self.cfg_vars: dict[str, tk.Variable] = {}
        warn = ttk.LabelFrame(t, text="Autorização do modo automático", padding=8)
        warn.pack(fill="x")
        ttk.Label(warn, wraplength=1050, justify="left", text=(
            "As regras do DDClássico sobre programas de automação não puderam ser verificadas. Muitos servidores "
            "punem o uso de bots. Leia os Termos do servidor antes de autorizar. O bot só joga sozinho atividades "
            "PvE/solo; partidas contra outros jogadores ficam apenas com mira assistida. O bot nunca compra itens "
            "nem gasta moeda premium, a menos que você libere um botão específico abaixo.")).pack(fill="x")
        self._cfg_check(warn, "automation.server_rules_confirmed",
                        "Li as regras do servidor e assumo a responsabilidade por usar a automação")
        grid = ttk.Frame(t, padding=(0, 8))
        grid.pack(fill="x")
        fields = [
            ("automation.keys.angle_up", "Tecla aumentar ângulo", str),
            ("automation.keys.angle_down", "Tecla diminuir ângulo", str),
            ("automation.keys.fire", "Tecla de disparo", str),
            ("automation.keys.pass_turn", "Tecla passar turno (opcional)", str),
            ("automation.power_mode", "Controle de força (timed/visual)", str),
            ("automation.power_full_time_s", "Tempo para força 100 (s)", float),
            ("automation.power_offset", "Compensação de força (pontos)", float),
            ("automation.min_seconds_between_shots", "Intervalo mínimo entre disparos (s)", float),
            ("thresholds.template", "Confiança mínima dos modelos (0-1)", float),
            ("thresholds.vision_min_confidence", "Confiança mínima para atirar (0-1)", float),
            ("instances.max_defeats", "Parar após N derrotas", int),
            ("instances.max_minutes", "Tempo máximo da rotina (min)", float),
            ("instances.unknown_state_timeout_s", "Tela desconhecida: pausar após (s)", float),
            ("instances.action_timeout_s", "Tela parada: recuperar após (s)", float),
            ("ruler.units_per_screen", "Unidades da régua por tela", float),
            ("safety.emergency_hotkey", "Tecla de emergência (reinicie o app)", str),
        ]
        self.cfg_types = {}
        for i, (key, label, typ) in enumerate(fields):
            r, col = divmod(i, 2)
            ttk.Label(grid, text=label).grid(row=r, column=col * 2, sticky="w", padx=(0, 6), pady=2)
            v = tk.StringVar(value="" if c.get(key) is None else str(c.get(key)))
            ttk.Entry(grid, textvariable=v, width=18).grid(row=r, column=col * 2 + 1, sticky="w", padx=(0, 24))
            self.cfg_vars[key] = v
            self.cfg_types[key] = typ
        self._cfg_check(t, "safety.require_foreground", "Só enviar comandos com a janela do jogo em foco")
        ttk.Label(t, text="Botões pagos liberados (nomes de modelo separados por vírgula; deixe vazio):").pack(anchor="w", pady=(8, 0))
        self.paid_var = tk.StringVar(value=", ".join(c.get("automation.allowed_paid_templates", []) or []))
        ttk.Entry(t, textvariable=self.paid_var, width=80).pack(anchor="w")
        ttk.Button(t, text="Salvar configurações", style="Big.TButton", command=self.save_config).pack(anchor="w", pady=10)
        ttk.Label(t, text=f"Pasta de dados: {self.svc.paths.root}", foreground="#555").pack(anchor="w")

    def _cfg_check(self, parent, key, text):
        v = tk.BooleanVar(value=bool(self.svc.config.get(key)))
        ttk.Checkbutton(parent, text=text, variable=v).pack(anchor="w", pady=2)
        self.cfg_vars[key] = v

    def _build_log(self):
        self.txt_log = tk.Text(self.tab_log, wrap="none", font=("Consolas", 9))
        sb = ttk.Scrollbar(self.tab_log, orient="vertical", command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=sb.set)
        self.txt_log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    # ================================================================== ações
    def info(self, text, error=False):
        self.vals["motivo"].configure(text=text)
        if error:
            log.warning(text)

    def refresh_windows(self):
        try:
            self.windows = self.svc.find_windows(self.all_windows.get())
        except Exception as exc:
            self.windows = []
            self.info(f"erro ao listar janelas: {exc}", True)
        self.cb_window["values"] = [f"{w.title}  ({w.width}x{w.height})" for w in self.windows]
        if self.windows and self.svc.window is None:
            self.cb_window.current(0)
            self.select_window()
        elif not self.windows:
            self.cb_window.set("")
            self.lbl_window.configure(text="cliente não encontrado: abra o jogo e clique em Atualizar"
                                      " (ou marque 'mostrar todas')")

    def select_window(self):
        i = self.cb_window.current()
        if 0 <= i < len(self.windows):
            self.svc.select_window(self.windows[i])
            w = self.windows[i]
            self.lbl_window.configure(text=f"OK: {w.width}x{w.height}", style="TLabel")

    def refresh_activities(self):
        defs, errors = self.svc.activities()
        for e in errors:
            self.info(f"definição inválida: {e}", True)
        if self.simulated.get():
            defs = [demo_activity("partida"), demo_activity("instancia")] + defs
        self.activities = {d.key: d for d in defs}
        for cb, kind in ((self.cb_match, "partida"), (self.cb_inst, "instancia")):
            items = [d for d in defs if d.kind == kind]
            cb._keys = [d.key for d in items]  # type: ignore[attr-defined]
            cb["values"] = [self._label(d) for d in items]
            if items:
                cb.current(0)
            else:
                cb.set("(nenhuma capturada ainda)")
        self._describe()

    def _label(self, d: ActivityDef):
        tag = "" if d.validated else "  [não validada no cliente]"
        if d.key.startswith(DEMO_KEY):
            tag = "  [simulação]"
        return f"{d.name} — {CATEGORIES.get(d.category, d.category)}{tag}"

    def selected_activity(self) -> ActivityDef | None:
        cb = self.cb_match if self.area.get() == "partida" else self.cb_inst
        keys = getattr(cb, "_keys", [])
        i = cb.current()
        return self.activities.get(keys[i]) if 0 <= i < len(keys) else None

    def _describe(self):
        d = self.selected_activity()
        if d is None:
            self.lbl_desc.configure(text="")
            return
        auto = "joga sozinho" if d.auto_allowed else "NÃO joga sozinho (envolve outros jogadores)"
        self.lbl_desc.configure(text=f"{d.description}\nCategoria: {CATEGORIES.get(d.category)} — {auto}.")

    def _runs(self) -> int:
        mode = self.run_mode.get()
        if mode == "uma":
            return 1
        if mode == "cont":
            return 0
        try:
            return max(1, int(self.run_count.get()))
        except (tk.TclError, ValueError):
            return 1

    def start(self):
        d = self.selected_activity()
        if d is None:
            messagebox.showwarning("Iniciar", "Escolha uma partida ou instância.")
            return
        simulated = self.simulated.get() or d.key.startswith(DEMO_KEY)
        if not simulated and self.svc.window is None:
            messagebox.showwarning("Iniciar", "Selecione a janela do jogo.")
            return
        ok, why = self.svc.start(d, self._runs(), simulated=simulated)
        if not ok:
            messagebox.showwarning("Não foi possível iniciar", why)
            self.info(why, True)
        self.progress.configure(value=0)
        self._update_buttons()

    def pause(self):
        self.svc.pause()
        self._update_buttons()

    def resume(self):
        self.svc.resume()
        self._update_buttons()

    def stop(self):
        # parar não pode travar a interface: espera em thread
        threading.Thread(target=self.svc.stop, daemon=True, name="parar").start()
        self.root.after(300, self._update_buttons)

    def _update_buttons(self):
        st = self.svc.status
        running = self.svc.runner is not None and self.svc.runner.alive
        self.btn_start.state(["disabled"] if running else ["!disabled"])
        self.btn_pause.state(["!disabled"] if running and st == RunStatus.RUNNING else ["disabled"])
        self.btn_resume.state(["!disabled"] if running and st == RunStatus.PAUSED else ["disabled"])
        self.btn_stop.state(["!disabled"] if running else ["disabled"])

    # ------------------------------------------------------------- calibração
    def calib_capture(self):
        frame = self.svc.grab()
        if frame is None:
            messagebox.showwarning("Captura", "Não foi possível capturar a janela (selecionada? minimizada?).")
            return
        self.calib_canvas.show(frame)
        self._tiles = []
        self.lst_tiles.delete(0, "end")

    def _on_calib_select(self, rect):
        self.lbl_tpl.configure(text=f"seleção: {rect[2]}x{rect[3]} px em ({rect[0]}, {rect[1]})")

    def save_region(self):
        frame, sel = self.calib_canvas.frame, self.calib_canvas.selection_px
        if frame is None or not sel:
            messagebox.showinfo("Região", "Capture a tela e arraste sobre a região primeiro.")
            return
        key = self.cb_region.get().split(" — ")[0]
        frac = px_to_frac(sel, frame.shape)
        self.svc.config.set("ruler.playfield" if key == "playfield" else f"regions.{key}", frac)
        self.svc.config.save()
        self.info(f"região '{key}' salva")

    def save_template(self):
        img = self.calib_canvas.selection_image()
        if img is None:
            messagebox.showinfo("Modelo", "Capture a tela e arraste sobre o elemento primeiro.")
            return
        key = self.cb_tpl.get().split(" — ")[0]
        self.svc.templates.add(key, img)
        self.lbl_tpl.configure(text=f"modelo '{key}' salvo ({len(self.svc.templates.get(key))} amostra(s))")

    def learn_digits(self):
        frame = self.calib_canvas.frame
        kind = self.digit_kind.get()
        roi = self.svc.config.get(f"regions.{kind}")
        if frame is None or roi is None:
            messagebox.showinfo("Números", "Capture a tela e salve a região do " +
                                ("ângulo" if kind == "angle" else "vento") + " primeiro.")
            return
        from ..vision.regions import crop
        sub, _ = crop(frame, roi)
        reader = self.svc.perception.angle_reader if kind == "angle" else self.svc.perception.wind_reader
        text = self.digit_value.get().strip()
        if not text or not reader.learn(sub, text):
            messagebox.showwarning("Números", "Não consegui separar os dígitos: confira o valor digitado e a região.")
            return
        self.info(f"dígitos '{text}' aprendidos; treinado: {reader.trained}")

    def detect_options(self):
        frame = self.calib_canvas.frame
        if frame is None:
            messagebox.showinfo("Opções", "Capture a tela com o menu aberto primeiro.")
            return
        self._tiles = detect_option_tiles(frame)
        self.lst_tiles.delete(0, "end")
        for i, (x, y, w, h) in enumerate(self._tiles):
            self.lst_tiles.insert("end", f"Opção {i + 1}: {w}x{h} em ({x},{y})")
        if not self._tiles:
            self.info("nenhuma opção detectada: selecione o cartão manualmente arrastando sobre ele")

    def _on_tile_select(self, _e=None):
        sel = self.lst_tiles.curselection()
        if sel:
            self.calib_canvas.selection_px = self._tiles[sel[0]]
            self.calib_canvas._redraw()

    def create_option(self):
        img = self.calib_canvas.selection_image()
        name = self.opt_name.get().strip()
        if img is None or not name:
            messagebox.showinfo("Criar atividade", "Selecione uma opção (lista ou arrastando) e digite um nome.")
            return
        kind = self.opt_kind.get()
        tpl = slug(f"{kind}_{name}")
        self.svc.templates.add(tpl, img)
        self.svc.create_activity(tpl, name, kind, self.opt_cat.get())
        self.refresh_activities()
        self.info(f"atividade '{name}' criada. Capture também os botões comuns (modelos) se ainda não fez.")

    def check_visible_options(self):
        frame = self.calib_canvas.frame
        if frame is None:
            return
        th = float(self.svc.config.get("thresholds.template", 0.8))
        found = find_known_options(frame, self.svc.templates, th, "instancia_") + \
            find_known_options(frame, self.svc.templates, th, "partida_")
        messagebox.showinfo("Opções visíveis", "\n".join(f"{k} ({s:.2f})" for k, s in found) or
                            "Nenhuma opção conhecida visível nesta captura.")

    def delete_activity(self):
        d = self.selected_activity()
        if d is None or d.key.startswith(DEMO_KEY):
            return
        if messagebox.askyesno("Excluir", f"Excluir a atividade '{d.name}'?"):
            self.svc.delete_activity(d)
            self.refresh_activities()

    # ------------------------------------------------------------ diagnóstico
    def diag_once(self):
        if self._diag_busy:
            return
        self._diag_busy = True

        def work():
            try:
                frame, snap = self.svc.analyze()
                over = None
                if frame is not None:
                    rec = self.svc.engine.last_recommendation if self.svc.engine else None
                    over = draw_overlay(frame, snap, rec)
                self._diag_queue.put((over, snap))
            except Exception as exc:
                log.exception("diagnóstico")
                self._diag_queue.put((None, f"erro: {exc}"))
            finally:
                self._diag_busy = False
        threading.Thread(target=work, daemon=True, name="diagnostico").start()

    def save_capture(self):
        frame = self.svc.grab()
        if frame is None:
            return
        self.info(f"captura salva em {self.svc.save_capture(frame)}")

    def toggle_assist(self):
        if self.assist_on.get():
            if self.svc.source is None:
                self.assist_on.set(False)
                messagebox.showinfo("Mira assistida", "Selecione a janela do jogo.")
                return
            try:
                self.svc.start_assist()
            except RuntimeError as exc:
                self.assist_on.set(False)
                messagebox.showwarning("Mira assistida", str(exc))
        else:
            self.svc.stop_assist()

    # ------------------------------------------------------------------ mira
    def calc_aim(self):
        try:
            vals = {k: float(e.get().replace(",", ".")) for k, e in self.aim_inputs.items()}
        except ValueError:
            messagebox.showwarning("Calculadora", "Use números (ex.: 7,5).")
            return
        rec = self.svc.recommend(vals["distance"], vals["wind"], vals["dy"])
        self.tree_aim.delete(*self.tree_aim.get_children())
        for c in rec.candidates[:15]:
            self.tree_aim.insert("", "end", values=(c.method, c.angle, f"{c.force:.1f}", f"{c.hit_probability:.0%}",
                                                    "; ".join(c.basis)))

    def refresh_shots(self):
        self.tree_shots.delete(*self.tree_shots.get_children())
        for r in self.svc.store.all(limit=200):
            res = "acerto" if r.hit else ("erro" if r.hit is False else "—")
            self.tree_shots.insert("", "end", iid=str(r.id), values=(
                r.id, r.angle, f"{r.force:.1f}", f"{r.wind:.1f}", f"{r.distance:.2f}",
                "—" if r.impact_x is None else f"{r.impact_x:.2f}", res, r.method, r.mode))
        st = self.svc.calibrator.stats()
        rate = "—" if st["taxa_acerto"] is None else f"{st['taxa_acerto']:.0%}"
        err = "—" if st["erro_abs_medio"] is None else f"{st['erro_abs_medio']:.2f}"
        self.lbl_stats.configure(text=f"Disparos: {st['disparos']} | avaliados: {st['avaliados']} | taxa de acerto: "
                                 f"{rate} | erro médio do impacto: {err} | correções ativas: {list(st['modelos'])}")

    def _selected_shot(self):
        sel = self.tree_shots.selection()
        return int(sel[0]) if sel else None

    def mark_shot(self, hit: bool):
        sid = self._selected_shot()
        if sid is None:
            return
        rec = next((r for r in self.svc.store.all() if r.id == sid), None)
        self.svc.calibrator.set_result(sid, rec.impact_x if rec else None, hit)
        self.refresh_shots()

    def mark_impact(self):
        sid = self._selected_shot()
        if sid is None:
            return
        try:
            impact = float(self.impact_entry.get().replace(",", "."))
        except ValueError:
            messagebox.showwarning("Impacto", "Digite a distância (régua) em que o tiro caiu.")
            return
        rec = next((r for r in self.svc.store.all() if r.id == sid), None)
        hit = None if rec is None else abs(impact - rec.distance) <= float(self.svc.config.get("aim.target_width", 0.35))
        self.svc.calibrator.set_result(sid, impact, hit)
        self.refresh_shots()

    def refit(self):
        res = self.svc.calibrator.refit_params()
        if res is None:
            messagebox.showinfo("Reajuste", f"São necessários pelo menos {self.svc.calibrator.MIN_SHOTS_REFIT} "
                                "disparos com impacto medido.")
            return
        params, info = res
        if messagebox.askyesno("Reajuste", f"Erro antes: {info['perda_antes']:.3f}\nErro depois: "
                               f"{info['perda_depois']:.3f}\nAplicar os novos parâmetros?"):
            self.svc.apply_params(params, info)
            self.refresh_shots()

    # ---------------------------------------------------------- configurações
    def save_config(self):
        c = self.svc.config
        try:
            for key, var in self.cfg_vars.items():
                if isinstance(var, tk.BooleanVar):
                    c.set(key, bool(var.get()))
                    continue
                raw = var.get().strip()
                typ = self.cfg_types[key]
                c.set(key, None if raw == "" else typ(raw.replace(",", ".") if typ is not str else raw))
        except ValueError as exc:
            messagebox.showwarning("Configurações", f"Valor inválido: {exc}")
            return
        c.set("automation.allowed_paid_templates", [s.strip() for s in self.paid_var.get().split(",") if s.strip()])
        c.save()
        self.info("configurações salvas")

    # ------------------------------------------------------------------ laço
    def _tick(self):
        if self._closing:
            return
        try:
            self._drain_events()
            self._drain_logs()
            self._drain_diag()
            self._update_status()
            self._update_buttons()
            if self.live_diag.get() and self.nb.select() == str(self.tab_diag):
                self.diag_once()
        except Exception:
            log.exception("erro na atualização da interface")
        self.root.after(200, self._tick)

    def _drain_events(self):
        n = 0
        while n < 100:
            try:
                e = self.svc.events.get_nowait()
            except queue.Empty:
                break
            n += 1
            tag = e.kind if e.kind in ("erro", "aviso", "resultado") else ""
            self.tree_hist.insert("", 0, values=(time.strftime("%H:%M:%S", time.localtime(e.when)), e.kind, e.message),
                                  tags=(tag,))
            if e.kind in ("erro", "aviso", "fim"):
                self.vals["motivo"].configure(text=e.message)
            if e.kind == "combate" and "shot_id" in e.data:
                self.refresh_shots()
        kids = self.tree_hist.get_children()
        if len(kids) > 1000:
            self.tree_hist.delete(*kids[1000:])

    def _drain_logs(self):
        lines = []
        while len(lines) < 200:
            try:
                lines.append(LOG_QUEUE.get_nowait())
            except queue.Empty:
                break
        if lines:
            self.txt_log.insert("end", "\n".join(lines) + "\n")
            if int(self.txt_log.index("end-1c").split(".")[0]) > 5000:
                self.txt_log.delete("1.0", "1000.0")
            self.txt_log.see("end")

    def _drain_diag(self):
        try:
            img, snap = self._diag_queue.get_nowait()
        except queue.Empty:
            return
        if img is not None:
            self.diag_canvas.show(img)
        self.txt_diag.delete("1.0", "end")
        text = snap if isinstance(snap, str) else (json.dumps(snap.summary(), indent=1, ensure_ascii=False)
                                                   if snap else "sem imagem")
        self.txt_diag.insert("1.0", text)

    def _update_status(self):
        r = self.svc.runner
        st = self.svc.status
        self.vals["status"].configure(text=STATUS_LABELS.get(st, st.value) + (" (simulação)" if self.svc.simulated and r else ""))
        if r:
            self.vals["etapa"].configure(text=STATE_LABELS.get(r.current_state, r.current_state))
            c = r.counters.as_dict()
            for k, lbl in self.counters.items():
                lbl.configure(text=str(c.get(k, 0)))
            total = r.limits.runs
            self.vals["progresso"].configure(text=f"{c['concluidas']}/{total}" if total else f"{c['concluidas']} (contínuo)")
            self.progress.configure(value=100 * c["concluidas"] / total if total else 0)
            if st in (RunStatus.PAUSED, RunStatus.FAILED) and r.reason:
                self.vals["motivo"].configure(text=r.reason)
        eng = self.svc.engine
        if eng is not None:
            obs, rec = eng.last_observation, eng.last_recommendation
            if obs is not None:
                self.vals["turno"].configure(text={True: "meu turno", False: "aguardando", None: "desconhecido"}[obs.my_turn])
                self.vals["alvo"].configure(text="—" if obs.distance is None else
                                            f"distância {obs.distance:.2f}, altura {obs.dy:+.2f}"
                                            + ("" if obs.target_visible else " (oculto: estimado)"))
                self.vals["vento"].configure(text="—" if obs.wind is None else f"{obs.wind:+.1f}")
                self.vals["angulo"].configure(text="—" if obs.current_angle is None else f"{obs.current_angle:.0f}°")
            if rec is not None and rec.best:
                b = rec.best
                self.vals["forca"].configure(text=f"{b.force:.1f}")
                self.vals["sugestao"].configure(text=f"{b.angle}° / força {b.force:.1f} ({b.method}, P≈{b.hit_probability:.0%})")

    def on_close(self):
        if self.svc.runner and self.svc.runner.alive:
            if not messagebox.askyesno("Sair", "Há uma rotina em execução. Parar e sair?"):
                return
        self._closing = True
        try:
            self.svc.close()
        finally:
            self.root.destroy()


# ============================================================ inicialização
def _smoke(app: MainWindow, seconds: float, report: dict, done):
    """Exercita a interface sem o jogo: demonstração, iniciar, pausar, retomar, parar."""
    root = app.root
    steps = []

    def at(delay, fn):
        steps.append((delay, fn))

    def check(name, cond):
        report.setdefault("checks", {})[name] = bool(cond)

    def s_demo():
        app.simulated.set(True)
        app.refresh_activities()
        app.area.set("instancia")
        app.cb_inst.current(0)
        app.run_mode.set("cont")
        check("demonstracao_listada", app.selected_activity() is not None)

    def s_start():
        app.btn_start.invoke()
        check("iniciou", app.svc.runner is not None and app.svc.runner.alive)

    def s_pause():
        check("executando", app.svc.status == RunStatus.RUNNING)
        app.btn_pause.invoke()
        check("pausou", app.svc.status == RunStatus.PAUSED)

    def s_paused_still():
        r = app.svc.runner
        report["leituras_pausado_a"] = getattr(r.reader, "reads", None)

    def s_resume():
        r = app.svc.runner
        check("pausa_congela_leituras", getattr(r.reader, "reads", 0) == report.get("leituras_pausado_a"))
        app.btn_resume.invoke()
        check("retomou", app.svc.status == RunStatus.RUNNING)

    def s_tabs():
        for tab in app.nb.tabs():
            app.nb.select(tab)
            root.update_idletasks()
        app.nb.select(app.tab_aim)
        app.calc_aim()
        check("calculadora", len(app.tree_aim.get_children()) > 0)
        app.nb.select(app.tab_home)

    def s_stop():
        t0 = time.monotonic()
        app.btn_stop.invoke()
        report["parar_retorno_ms"] = round((time.monotonic() - t0) * 1000)
        check("parar_nao_trava", report["parar_retorno_ms"] < 500)

    def s_stopped():
        check("parou", not (app.svc.runner and app.svc.runner.alive))
        check("historico", len(app.tree_hist.get_children()) > 0)
        report["contadores"] = app.svc.runner.counters.as_dict() if app.svc.runner else None

    def s_emergency():
        app.run_mode.set("cont")
        app.btn_start.invoke()
        root.after(400, lambda: (app.svc.emergency_stop(), root.after(1200, s_emergency_check)))

    def s_emergency_check():
        check("emergencia_para", not (app.svc.runner and app.svc.runner.alive))
        done()

    span = max(6.0, seconds)
    at(0.3, s_demo)
    at(0.6, s_start)
    at(span * 0.30, s_pause)
    at(span * 0.38, s_paused_still)
    at(span * 0.46, s_resume)
    at(span * 0.55, s_tabs)
    at(span * 0.65, s_stop)
    at(span * 0.80, s_stopped)
    at(span * 0.85, s_emergency)

    # responsividade: mede o atraso do laço de eventos durante a automação
    lags = []

    def probe(last=[time.monotonic()]):
        now = time.monotonic()
        lags.append(now - last[0] - 0.1)
        last[0] = now
        report["atraso_max_ms"] = round(max(lags) * 1000)
        root.after(100, probe)
    root.after(100, probe)
    for delay, fn in steps:
        root.after(int(delay * 1000), fn)


def run_gui(home: Path | None = None, smoke_seconds: float = 0.0) -> int:
    report: dict = {}
    smoke_out = os.environ.get("DDBOT_SMOKE_OUT")
    try:
        svc = BotService(home, start_hotkey=smoke_seconds <= 0)
    except Exception as exc:
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("DDClássico Bot", f"Erro ao iniciar: {exc}")
            r.destroy()
        except Exception:
            pass
        if smoke_out:
            Path(smoke_out).write_text(json.dumps({"erro": str(exc)}), encoding="utf-8")
        return 1
    root = tk.Tk()
    app = MainWindow(root, svc)
    if smoke_seconds > 0:
        finished = []

        def finish():
            if finished:
                return
            finished.append(True)
            checks = report.get("checks", {})
            report["atraso_ok"] = report.get("atraso_max_ms", 0) < 1500
            report["resultado"] = "OK" if checks and all(checks.values()) and report["atraso_ok"] else "FALHOU"
            if smoke_out:
                Path(smoke_out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            app._closing = True
            svc.close()
            root.destroy()
        _smoke(app, smoke_seconds, report, finish)
        root.after(int((max(6.0, smoke_seconds) + 20) * 1000), lambda: (report.setdefault("checks", {}).update(
            {"terminou_no_prazo": False}), finish()))
    root.mainloop()
    if smoke_seconds > 0:
        return 0 if report.get("resultado") == "OK" else 1
    return 0
