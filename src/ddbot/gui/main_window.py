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

from .. import __version__
from ..activities import CATEGORIES, COMMON_TEMPLATES, ActivityDef, RunStatus, activity_from_option
from ..log import LOG_QUEUE
from ..service import BotService
from ..strategy import CONFIDENCE_LABELS, SOLO_LABELS
from ..vision.menu import detect_option_tiles, find_known_options
from ..vision.perception import REGION_KEYS, STATE_LABELS, STATES, draw_overlay
from ..vision.regions import crop, px_to_frac
from . import theme as T
from .logo import load_logo
from .states import UiSnapshot, advice, describe, humanize, method_label, pick_options
from .widgets import Counter, ImageCanvas, Panel, Readout, ScrollFrame, StatusBanner

log = logging.getLogger(__name__)

DEMO_KEY = "__demonstracao__"
KIND_LABELS = {"instancia": "Instâncias", "partida": "Partidas automáticas"}
HIST_ICONS = {"resultado": "✓", "aviso": "!", "erro": "✕", "fim": "■", "combate": "◎"}
OPTIONAL_FIELDS = {"automation.keys.pass_turn"}


def demo_activity(kind: str, profile=None) -> ActivityDef:
    if profile is not None:
        d = activity_from_option(f"instancia_{profile.key}", f"{profile.name} (demonstração)", "instancia", "pve",
                                 strategy=profile.key)
        d.key = DEMO_KEY + profile.key
    else:
        name = "Instância de demonstração" if kind == "instancia" else "Partida de demonstração"
        d = activity_from_option(f"{kind}_teste", name, kind, "pve")
        d.key = DEMO_KEY + kind
    d.description = "Simulação interna para conhecer o programa. Nada é enviado ao jogo."
    return d


class _Blank:
    """Configuração vazia: conta todos os itens de calibração que uma atividade pede."""

    def get(self, key, default=None):
        return default


def headless() -> bool:
    """Em testes automáticos nenhuma caixa de diálogo pode bloquear a janela."""
    return bool(os.environ.get("DDBOT_SMOKE_OUT") or os.environ.get("DDBOT_HEADLESS"))


class MainWindow:
    def __init__(self, root: tk.Tk, service: BotService):
        self.root = root
        self.svc = service
        self.th = T.Theme(root)
        px = self.th.px
        self.windows = []
        self.activities: dict[str, ActivityDef] = {}
        self.live_diag = tk.BooleanVar(value=False)
        self.simulated = tk.BooleanVar(value=False)
        self._starting = False  # Iniciar no jogo real em andamento (em thread)
        self._missing_required = ""  # calibração obrigatória que falta para a atividade escolhida
        self._diag_queue: "queue.Queue[tuple]" = queue.Queue(maxsize=2)
        self._diag_busy = False
        self._tiles: list = []
        self._closing = False
        self._notice_after = None
        root.title(f"JonFlow {__version__}")
        self._logo = load_logo(root, px(30))
        if self._logo is not None:
            try:
                root.iconphoto(True, load_logo(root, 64) or self._logo)
            except tk.TclError:
                pass
        from .. import winapi
        area = winapi.work_area()
        ax, ay, aw, ah = area or (0, 0, root.winfo_screenwidth(), root.winfo_screenheight() - px(48))
        # cabe na área de trabalho (sem a barra de tarefas), descontando borda e barra de título
        w, h = min(px(1220), aw - px(16)), min(px(800), ah - px(40))
        # janela baixa (ex.: 1080p a 150%, só ~630 px lógicos de altura): listas pedem menos linhas para
        # que as de baixo não fiquem sem espaço
        self.compact = h / self.th.scale < 700
        root.geometry(f"{w}x{h}+{ax + max(0, (aw - w) // 2)}+{ay + max(0, (ah - h - px(32)) // 2)}")
        root.minsize(min(px(960), aw), min(px(600), ah - px(40)))
        self._build_top()
        self.nb = ttk.Notebook(root)
        self._build_notice()
        self.nb.pack(fill="both", expand=True, padx=px(12), pady=(0, px(4)))
        # voltar ao Início depois de calibrar atualiza o que ainda falta
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self._on_tab_changed())
        self.tab_home = ttk.Frame(self.nb, padding=(0, px(12), 0, 0))
        self.tab_calib = ttk.Frame(self.nb, padding=(0, px(12), 0, 0))
        self.tab_diag = ttk.Frame(self.nb, padding=(0, px(12), 0, 0))
        self.tab_aim = ttk.Frame(self.nb, padding=(0, px(12), 0, 0))
        self.tab_cfg = ttk.Frame(self.nb, padding=(0, px(12), 0, 0))
        self.tab_log = ttk.Frame(self.nb, padding=(0, px(12), 0, 0))
        for tab, text in ((self.tab_home, "Início"), (self.tab_calib, "Calibração"),
                          (self.tab_diag, "Diagnóstico"), (self.tab_aim, "Mira e disparos"),
                          (self.tab_cfg, "Configurações"), (self.tab_log, "Registro técnico")):
            self.nb.add(tab, text=text)
        self._build_home()
        self._build_calibration()
        self._build_diagnostics()
        self._build_aim()
        self._build_config()
        self._build_log()
        self._bind_keys()
        self.refresh_windows()
        self.refresh_activities()
        self._fill_strategy_page()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(200, self._tick)

    # ================================================================ layout
    def _build_top(self):
        px = self.th.px
        top = ttk.Frame(self.root, padding=(px(16), px(12), px(16), px(8)))
        top.pack(fill="x")
        if self._logo is not None:
            ttk.Label(top, image=self._logo).pack(side="left", padx=(0, px(8)))
        ttk.Label(top, text="JonFlow", style="Section.TLabel").pack(side="left")
        ttk.Label(top, text="bot para DDTank", style="Muted.TLabel").pack(side="left", padx=(px(6), px(24)))
        ttk.Label(top, text="Jogo:").pack(side="left")
        self.lbl_window = ttk.Label(top, text="procurando...")
        self.lbl_window.pack(side="left", padx=(px(8), px(12)))
        self.btn_detect = ttk.Button(top, text="Detectar jogo", style="Primary.TButton", command=self.open_detect)
        self.btn_detect.pack(side="left")
        self.detect_dialog = None
        self._minimized_for_run = False
        ttk.Checkbutton(top, text="Modo demonstração", variable=self.simulated,
                        command=self._toggle_demo).pack(side="right")
        self.window_state = ""
        self._locating = False
        self._locate_queue: "queue.Queue" = queue.Queue(maxsize=2)

    def _build_notice(self):
        """Rodapé: retorno das ações (salvou, capturou...) e o estado da tecla de emergência."""
        px = self.th.px
        self.notice_var = tk.StringVar(value="")
        bar = ttk.Frame(self.root, padding=(px(16), px(2), px(16), px(8)))
        bar.pack(fill="x", side="bottom")
        self.lbl_notice = ttk.Label(bar, textvariable=self.notice_var, style="Muted.TLabel")
        self.lbl_notice.pack(side="left")
        hk = (self.svc.config.get("safety.emergency_hotkey") or "<f12>").strip("<>").upper()
        ok = getattr(self.svc, "hotkey_ok", None)
        if ok is False:
            text = f"Tecla de emergência {hk} indisponível: use o botão Parar. Modo automático bloqueado."
        else:
            text = f"Parada de emergência: tecla {hk}, a qualquer momento"
        self.lbl_hotkey = ttk.Label(bar, text=text, style="Error.TLabel")
        self.lbl_hotkey.pack(side="right")

    def notice(self, text: str, error: bool = False):
        self.notice_var.set(text)
        self.lbl_notice.configure(style="Error.TLabel" if error else "Muted.TLabel")
        if error:
            log.warning(text)
        if self._notice_after:
            self.root.after_cancel(self._notice_after)
        self._notice_after = self.root.after(8000, lambda: self.notice_var.set(""))

    # ---------------------------------------------------------------- Início
    def _build_home(self):
        px, t = self.th.px, self.tab_home
        gap = px(T.SPACE["m"])
        for col, weight in ((0, 10), (1, 14), (2, 9)):
            t.columnconfigure(col, weight=weight, uniform="home")
        t.rowconfigure(2, weight=1)
        self.banner = StatusBanner(t, self.th)
        self.banner.grid(row=0, column=0, columnspan=3, sticky="we")

        # atividades: duas seções, as instâncias pré-cadastradas sempre visíveis (antes de conectar ao jogo)
        acts = Panel(t, self.th, "Atividades", pad="m")
        acts.grid(row=1, column=0, sticky="nsew", pady=(gap, 0), padx=(0, gap))
        ab = acts.body
        ab.rowconfigure(0, weight=1)
        # em janela baixa pede uma linha a menos (cada linha a mais tira espaço do histórico); com mais
        # atividades, a lista rola
        self.tree_act = ttk.Treeview(ab, columns=("estado",), show="tree", selectmode="browse",
                                     height=8 if self.compact else 9, style="Activities.Treeview")
        self.tree_act.column("#0", width=px(200), stretch=True)
        self.tree_act.column("estado", width=px(84), stretch=False, anchor="w")
        self.tree_act.tag_configure("secao", font=self.th.fonts["strong"], foreground=T.MUTED)
        self.tree_act.tag_configure("pronta", foreground="#1F7A4D")
        self.tree_act.tag_configure("pendente", foreground="#8A5600")
        self.tree_act.tag_configure("ausente", foreground="#B3261E")
        self.tree_act.tag_configure("vazio", foreground=T.MUTED)
        self.tree_act.grid(row=0, column=0, sticky="nsew")
        sb_act = ttk.Scrollbar(ab, orient="vertical", command=self.tree_act.yview)
        self.tree_act.configure(yscrollcommand=sb_act.set)
        sb_act.grid(row=0, column=1, sticky="ns")
        self.tree_act.bind("<<TreeviewSelect>>", lambda e: self._on_activity_selected())
        self._chosen = None  # atividade escolhida (mantida ao recarregar a lista)

        det = Panel(t, self.th, None, pad="m")
        det.grid(row=1, column=1, sticky="nsew", pady=(gap, 0), padx=(0, gap))
        b = det.body
        self.lbl_act_title = ttk.Label(b, text="Escolha uma atividade", style="SurfaceSection.TLabel")
        self.lbl_act_title.grid(row=0, column=0, sticky="w")
        self.lbl_desc = ttk.Label(b, text="", style="SurfaceMuted.TLabel", justify="left", wraplength=px(400))
        self.lbl_desc.grid(row=1, column=0, sticky="we", pady=(px(2), 0))
        self.lbl_state = ttk.Label(b, text="", style="Surface.TLabel", justify="left", wraplength=px(400))
        self.lbl_state.grid(row=2, column=0, sticky="we", pady=(px(4), 0))
        self.lbl_ready = ttk.Label(b, text="", style="SurfaceMuted.TLabel", justify="left", wraplength=px(400))
        self.lbl_ready.grid(row=3, column=0, sticky="we", pady=(px(4), 0))
        # os textos acompanham a largura do painel (em telas baixas cada linha a mais tira espaço do histórico)
        b.bind("<Configure>", lambda e: [w.configure(wraplength=max(px(200), e.width - px(8)))
                                         for w in (self.lbl_desc, self.lbl_state, self.lbl_ready)], add="+")
        links = ttk.Frame(b, style="Surface.TFrame")
        links.grid(row=4, column=0, sticky="w", pady=(px(6), 0))
        self.btn_goto_calib = ttk.Button(links, text="Ver pendências", style="Small.TButton",
                                         command=self._goto_pending)
        self.btn_goto_calib.pack(side="left")
        self.btn_avail = ttk.Button(links, text="Não aparece no meu jogo", style="Small.TButton",
                                    command=self._toggle_availability)
        self.btn_avail.pack(side="left", padx=(px(8), 0))

        runs = ttk.Frame(b, style="Surface.TFrame")
        runs.grid(row=5, column=0, sticky="w", pady=(px(8), 0))
        self.run_mode = tk.StringVar(value="uma")
        self.run_count = tk.IntVar(value=5)
        ttk.Label(runs, text="Quantas vezes", style="Strong.TLabel").grid(row=0, column=0, sticky="w",
                                                                         padx=(0, px(12)))
        ttk.Radiobutton(runs, text="Uma vez", value="uma", variable=self.run_mode,
                        style="Surface.TRadiobutton").grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(runs, text="Repetir", value="qtd", variable=self.run_mode,
                        style="Surface.TRadiobutton").grid(row=0, column=2, sticky="w", padx=(px(10), px(4)))
        self.sp_runs = ttk.Spinbox(runs, from_=1, to=999, textvariable=self.run_count, width=4,
                                   command=lambda: self.run_mode.set("qtd"))
        self.sp_runs.grid(row=0, column=3, sticky="w")
        self.sp_runs.bind("<KeyRelease>", lambda e: self.run_mode.set("qtd"))
        ttk.Radiobutton(runs, text="Até eu parar", value="cont", variable=self.run_mode,
                        style="Surface.TRadiobutton").grid(row=0, column=4, sticky="w", padx=(px(10), 0))

        actions = ttk.Frame(b, style="Surface.TFrame")
        actions.grid(row=6, column=0, sticky="w", pady=(px(8), 0))
        self.btn_start = ttk.Button(actions, text="Iniciar (F5)", style="Primary.TButton", command=self.start)
        self.btn_start.pack(side="left")
        self.btn_pause = ttk.Button(actions, text="Pausar (F6)", command=self.toggle_pause)
        self.btn_pause.pack(side="left", padx=(px(8), 0))
        self.btn_stop = ttk.Button(actions, text="Parar (F8)", style="Danger.TButton", command=self.stop)
        self.btn_stop.pack(side="left", padx=(px(8), 0))

        # andamento: progresso e mira num painel só. Em telas baixas (1080p a 150%) cada linha a mais tira
        # espaço do histórico: situação e barra dividem uma linha e cada contador tem o rótulo ao lado
        prog = Panel(t, self.th, None, pad="m")
        prog.grid(row=1, column=2, sticky="nsew", pady=(gap, 0))
        pb = prog.body
        ttk.Label(pb, text="Andamento", style="SurfaceSection.TLabel").grid(row=0, column=0, columnspan=2,
                                                                           sticky="w")
        line = ttk.Frame(pb, style="Surface.TFrame")
        line.grid(row=1, column=0, columnspan=2, sticky="we", pady=(px(4), px(4)))
        line.columnconfigure(1, weight=1)
        self.lbl_progress = ttk.Label(line, text="Nada em execução", style="Strong.TLabel")
        self.lbl_progress.grid(row=0, column=0, sticky="w", padx=(0, px(10)))
        self.progress = ttk.Progressbar(line, mode="determinate")
        self.progress.grid(row=0, column=1, sticky="we")
        self.counters = {}
        for i, (k, label) in enumerate((("concluidas", "concluídas"), ("vitorias", "vitórias"),
                                        ("derrotas", "derrotas"), ("batalhas", "batalhas"))):
            c = Counter(pb, self.th, label)
            c.grid(row=2 + i // 2, column=i % 2, sticky="w", padx=(0, px(10)))
            self.counters[k] = c
        for i in range(2):
            pb.columnconfigure(i, weight=1)
        ttk.Separator(pb).grid(row=5, column=0, columnspan=2, sticky="we", pady=px(6))
        aim = ttk.Frame(pb, style="Surface.TFrame")
        aim.grid(row=6, column=0, columnspan=2, sticky="we")
        ttk.Label(aim, text="Mira", style="Strong.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        self.ro_angle = Readout(aim, self.th, "ângulo", "°")
        self.ro_force = Readout(aim, self.th, "força")
        self.ro_wind = Readout(aim, self.th, "vento")
        for i, ro in enumerate((self.ro_angle, self.ro_force, self.ro_wind)):
            ro.grid(row=1, column=i, sticky="w", padx=(0, px(18)))
        aim.columnconfigure(3, weight=1)  # sobra de espaço à direita: os três números ficam juntos
        self.lbl_target = ttk.Label(aim, text="Os valores aparecem durante o combate.", style="SurfaceMuted.TLabel",
                                    justify="left", wraplength=px(300))
        self.lbl_target.grid(row=2, column=0, columnspan=4, sticky="we", pady=(px(4), 0))
        aim.bind("<Configure>", lambda e: self.lbl_target.configure(wraplength=max(px(160), e.width - px(4))),
                 add="+")

        hist = Panel(t, self.th, "Histórico", pad="m")
        hist.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=(gap, 0))
        t.rowconfigure(2, weight=1, minsize=px(124))  # título, cabeçalho e ao menos duas linhas
        hb = hist.body
        hb.rowconfigure(0, weight=1)
        self.tree_hist = ttk.Treeview(hb, columns=("hora", "tipo", "msg"), show="headings", height=3)
        for col, text, w in (("hora", "Hora", 76), ("tipo", "Tipo", 110), ("msg", "O que aconteceu", 760)):
            self.tree_hist.heading(col, text=text, anchor="w")
            self.tree_hist.column(col, width=px(w), stretch=col == "msg", anchor="w")
        for tag, color in T.RESULT_COLORS.items():
            self.tree_hist.tag_configure(tag, foreground=color)
        sb = ttk.Scrollbar(hb, orient="vertical", command=self.tree_hist.yview)
        self.tree_hist.configure(yscrollcommand=sb.set)
        self.tree_hist.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self._update_buttons()

    # -------------------------------------------------------------- Calibração
    def _build_calibration(self):
        px, t = self.th.px, self.tab_calib
        t.columnconfigure(0, weight=1)
        t.rowconfigure(0, weight=1)
        self.calib_canvas = ImageCanvas(t, "Clique em Capturar tela do jogo.\nDepois arraste o mouse sobre a imagem "
                                        "para selecionar.", on_select=self._on_calib_select)
        self.calib_canvas.grid(row=0, column=0, sticky="nsew", padx=(0, px(12)))
        side = ScrollFrame(t, self.th, width=390)
        side.grid(row=0, column=1, sticky="ns")
        s = side.inner
        s.columnconfigure(0, weight=1)
        self.btn_capture = ttk.Button(s, text="Capturar tela do jogo", style="Primary.TButton",
                                      command=self.calib_capture)
        self.btn_capture.grid(row=0, column=0, sticky="we")
        self.lbl_sel = ttk.Label(s, text="Nenhuma seleção.", style="SurfaceMuted.TLabel")
        self.lbl_sel.grid(row=1, column=0, sticky="w", pady=(px(6), px(10)))
        # seis páginas não cabem como abas na coluna (no Windows os nomes ficavam cortados): botões em duas
        # linhas escolhem a página e o caderno, sem abas, só troca o conteúdo
        pages = ttk.Frame(s, style="Surface.TFrame")
        pages.grid(row=2, column=0, sticky="we")
        for col in range(3):
            pages.columnconfigure(col, weight=1, uniform="pages")
        sub = ttk.Notebook(s, style="Sub.TNotebook")
        sub.grid(row=3, column=0, sticky="we", pady=(px(2), 0))
        self.calib_nb = sub
        self.calib_page = tk.StringVar()
        self.calib_page_buttons: list[ttk.Radiobutton] = []

        def page(title, hint):
            f = ttk.Frame(sub, style="Surface.TFrame", padding=px(10))
            f.columnconfigure(0, weight=1)
            sub.add(f, text=title)
            i = len(self.calib_page_buttons)
            b = ttk.Radiobutton(pages, text=title, value=str(f), variable=self.calib_page,
                                style="Segment.TRadiobutton", command=lambda: sub.select(f))
            b.grid(row=i // 3, column=i % 3, sticky="we", padx=(0 if i % 3 == 0 else px(4), 0), pady=(0, px(4)))
            self.calib_page_buttons.append(b)
            ttk.Label(f, text=hint, style="SurfaceMuted.TLabel", wraplength=px(320), justify="left").grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(0, px(8)))
            return f

        f = self.page_pending = page("Pendências", "O que falta para a atividade escolhida no Início jogar sozinha. "
                                     "Escolha um item: a instrução aparece embaixo e Fazer agora abre o lugar certo.")
        self.tree_pending = ttk.Treeview(f, columns=("item",), show="tree", selectmode="browse", height=7)
        self.tree_pending.column("#0", width=0, stretch=False)
        self.tree_pending.column("item", width=px(300), stretch=True)
        self.tree_pending.tag_configure("obrigatorio", foreground="#B3261E")
        self.tree_pending.tag_configure("recomendado", foreground=T.MUTED)
        self.tree_pending.grid(row=1, column=0, sticky="we")
        self.tree_pending.bind("<<TreeviewSelect>>", lambda e: self._on_pending_select())
        self.lbl_pending = ttk.Label(f, text="", style="SurfaceMuted.TLabel", wraplength=px(320), justify="left")
        self.lbl_pending.grid(row=2, column=0, sticky="w", pady=(px(6), 0))
        self.btn_pending = ttk.Button(f, text="Fazer agora", command=self._do_pending)
        self.btn_pending.grid(row=3, column=0, sticky="we", pady=(px(6), 0))
        self._pending: list = []

        f = self.page_regions = page("Regiões", "Selecione onde ficam o ângulo, o vento, a barra de força, o indicador "
                                     "de turno e a área de jogo. Numa batalha, Sugerir regiões tenta achá-las sozinho.")
        self.cb_region = ttk.Combobox(f, state="readonly", values=list(REGION_KEYS.values()))
        self.cb_region.current(0)
        self.cb_region.grid(row=1, column=0, sticky="we")
        ttk.Button(f, text="Salvar região", command=self.save_region).grid(row=2, column=0, sticky="we",
                                                                           pady=(px(6), 0))
        sug = ttk.Frame(f, style="Surface.TFrame")
        sug.grid(row=3, column=0, sticky="we", pady=(px(6), 0))
        sug.columnconfigure(0, weight=1, uniform="sug")
        sug.columnconfigure(1, weight=1, uniform="sug")
        ttk.Button(sug, text="Sugerir regiões", command=self.suggest_regions).grid(row=0, column=0, sticky="we")
        ttk.Button(sug, text="Ângulo pelas teclas", command=self.find_angle_by_keys).grid(
            row=0, column=1, sticky="we", padx=(px(6), 0))
        self.btn_use_suggest = ttk.Button(f, text="Usar as sugestões", command=self.use_suggestions)
        self.btn_use_suggest.grid(row=4, column=0, sticky="we", pady=(px(6), 0))
        self.btn_use_suggest.state(["disabled"])
        self.lbl_suggest = ttk.Label(f, text="", style="SurfaceMuted.TLabel", wraplength=px(320), justify="left")
        self.lbl_suggest.grid(row=5, column=0, sticky="w", pady=(px(6), 0))
        self._suggestions: list = []

        f = self.page_models = page("Modelos", "Selecione um pedaço que identifique a tela ou o botão e salve com o "
                                    "nome certo. Capture 2 ou 3 amostras de cada um.")
        self._tpl_keys = [f"estado_{st}" for st in STATES] + list(COMMON_TEMPLATES) \
            + list(self.svc.catalog.difficulty_templates())
        tpl_labels = [f"Tela: {STATE_LABELS.get(st, st)}" for st in STATES] + list(COMMON_TEMPLATES.values()) \
            + list(self.svc.catalog.difficulty_templates().values())
        self.cb_tpl = ttk.Combobox(f, state="readonly", values=tpl_labels)
        self.cb_tpl.current(0)
        self.cb_tpl.grid(row=1, column=0, sticky="we")
        ttk.Button(f, text="Salvar modelo", command=self.save_template).grid(row=2, column=0, sticky="we",
                                                                             pady=(px(6), 0))
        self.lbl_tpl = ttk.Label(f, text="", style="SurfaceMuted.TLabel", wraplength=px(300))
        self.lbl_tpl.grid(row=3, column=0, sticky="w", pady=(px(6), 0))

        f = self.page_digits = page("Números", "Com a região já salva, digite o número que aparece no jogo e clique em "
                                    "Aprender. Repita até cobrir os dígitos de 0 a 9. No vento, a região deve pegar "
                                    "só os números (sem a seta): o sentido vem das setas salvas em Modelos.")
        self.digit_kind = tk.StringVar(value="angle")
        row = ttk.Frame(f, style="Surface.TFrame")
        row.grid(row=1, column=0, sticky="w")
        ttk.Radiobutton(row, text="Ângulo", value="angle", variable=self.digit_kind,
                        style="Surface.TRadiobutton").pack(side="left")
        ttk.Radiobutton(row, text="Vento", value="wind", variable=self.digit_kind,
                        style="Surface.TRadiobutton").pack(side="left", padx=(px(12), 0))
        row2 = ttk.Frame(f, style="Surface.TFrame")
        row2.grid(row=2, column=0, sticky="we", pady=(px(8), 0))
        ttk.Label(row2, text="Valor mostrado", style="Surface.TLabel").pack(side="left")
        self.digit_value = ttk.Entry(row2, width=8)
        self.digit_value.pack(side="left", padx=(px(8), 0))
        ttk.Button(f, text="Aprender", command=self.learn_digits).grid(row=3, column=0, sticky="we", pady=(px(8), 0))

        f = self.page_menu = page("Menu", "Abra no jogo o menu de instâncias (ou de partidas), capture e clique em "
                                  "Detectar. Escolha a opção e diga o que ela é: uma instância da lista já fica "
                                  "pronta; outra opção vira uma atividade nova.")
        ttk.Button(f, text="Detectar opções", command=self.detect_options).grid(row=1, column=0, sticky="we")
        self.lst_tiles = tk.Listbox(f, height=5, exportselection=False, relief="flat", highlightthickness=1,
                                    highlightbackground=T.LINE, font=self.th.fonts["body"],
                                    selectbackground=T.PRIMARY, activestyle="none")
        self.lst_tiles.grid(row=2, column=0, sticky="we", pady=(px(6), px(6)))
        self.lst_tiles.bind("<<ListboxSelect>>", self._on_tile_select)
        g = ttk.Frame(f, style="Surface.TFrame")
        g.grid(row=3, column=0, sticky="we")
        g.columnconfigure(1, weight=1)
        ttk.Label(g, text="Esta opção é", style="Surface.TLabel").grid(row=0, column=0, sticky="w", pady=px(2))
        self._opt_targets = [(tpl, name) for tpl, name in self.svc.catalog.option_templates().items()]
        self.opt_what = ttk.Combobox(g, state="readonly", values=[n for _, n in self._opt_targets]
                                     + ["Outra instância (nova atividade)", "Uma partida (nova atividade)"])
        self.opt_what.current(0)
        self.opt_what.grid(row=0, column=1, sticky="we", padx=(px(8), 0))
        self.opt_what.bind("<<ComboboxSelected>>", lambda e: self._on_option_kind())
        ttk.Label(g, text="Nome", style="Surface.TLabel").grid(row=1, column=0, sticky="w", pady=px(2))
        self.opt_name = ttk.Entry(g)
        self.opt_name.grid(row=1, column=1, sticky="we", padx=(px(8), 0))
        ttk.Label(g, text="Categoria", style="Surface.TLabel").grid(row=2, column=0, sticky="w", pady=px(2))
        self._cat_keys = list(CATEGORIES)
        self.opt_cat = ttk.Combobox(g, state="readonly", values=list(CATEGORIES.values()))
        self.opt_cat.current(0)
        self.opt_cat.grid(row=2, column=1, sticky="we", padx=(px(8), 0))
        self.btn_create_opt = ttk.Button(f, text="Salvar opção", command=self.create_option)
        self.btn_create_opt.grid(row=4, column=0, sticky="we", pady=(px(8), 0))
        ttk.Button(f, text="Ver opções conhecidas nesta captura", command=self.check_visible_options).grid(
            row=5, column=0, sticky="we", pady=(px(4), 0))
        self._on_option_kind()

        f = self.page_targets = page("Alvos", "Numa batalha da instância escolhida no Início, capture cada alvo e "
                                     "estado especial (2 ou 3 amostras). As dificuldades da mesma instância usam "
                                     "as mesmas capturas.")
        ttk.Label(f, text="Estratégia da atividade", style="Surface.TLabel").grid(row=1, column=0, sticky="w")
        self._strategy_keys: list[str | None] = [None] + [p.key for p in self.svc.strategies()]
        self.cb_strategy = ttk.Combobox(f, state="readonly", values=["Genérica (inimigo mais à esquerda)"]
                                        + [p.name for p in self.svc.strategies()])
        self.cb_strategy.grid(row=2, column=0, sticky="we")
        self.cb_strategy.bind("<<ComboboxSelected>>", lambda e: self.set_strategy())
        ttk.Label(f, text="Alvo ou estado a capturar", style="Surface.TLabel").grid(row=3, column=0, sticky="w",
                                                                                   pady=(px(8), 0))
        self.cb_role = ttk.Combobox(f, state="readonly")
        self.cb_role.grid(row=4, column=0, sticky="we")
        self._role_keys: list[str] = []
        self.btn_role = ttk.Button(f, text="Salvar alvo ou estado", command=self.save_role_template)
        self.btn_role.grid(row=5, column=0, sticky="we", pady=(px(6), 0))
        self.lbl_strategy = ttk.Label(f, text="", style="SurfaceMuted.TLabel", wraplength=px(320), justify="left")
        self.lbl_strategy.grid(row=6, column=0, sticky="w", pady=(px(6), 0))
        # o seletor acompanha as trocas feitas pelo código (Ver pendências, Fazer agora...)
        sub.bind("<<NotebookTabChanged>>", lambda e: (self.calib_page.set(sub.select()), self._fill_strategy_page(),
                                                      self._fill_pending()), add="+")
        self.calib_page.set(str(self.page_pending))

        ttk.Separator(s).grid(row=4, column=0, sticky="we", pady=px(14))
        ttk.Label(s, text="Conferir os controles", style="SurfaceSection.TLabel").grid(row=5, column=0, sticky="w")
        ttk.Label(s, text="No seu turno, aperta ↑ e depois ↓ e confere se o ângulo mudou. Não atira.",
                  style="SurfaceMuted.TLabel", wraplength=px(300), justify="left").grid(row=6, column=0, sticky="w")
        ttk.Button(s, text="Testar teclas do ângulo", command=self.test_controls).grid(row=7, column=0, sticky="we",
                                                                                       pady=(px(6), 0))
        ttk.Separator(s).grid(row=8, column=0, sticky="we", pady=px(14))
        ttk.Button(s, text="Excluir a atividade capturada", style="Danger.TButton",
                   command=self.delete_activity).grid(row=9, column=0, sticky="we")

    # ------------------------------------------------------------- Diagnóstico
    def _build_diagnostics(self):
        px, t = self.th.px, self.tab_diag
        t.columnconfigure(0, weight=1)
        t.rowconfigure(1, weight=1)
        bar = ttk.Frame(t)
        bar.grid(row=0, column=0, columnspan=2, sticky="we", pady=(0, px(8)))
        ttk.Button(bar, text="Analisar agora", style="Primary.TButton", command=self.diag_once).pack(side="left")
        ttk.Checkbutton(bar, text="Atualizar ao vivo", variable=self.live_diag).pack(side="left", padx=px(12))
        ttk.Button(bar, text="Salvar captura", command=self.save_capture).pack(side="left")
        self.assist_on = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Mira assistida ao vivo (só sugere, não joga)", variable=self.assist_on,
                        command=self.toggle_assist).pack(side="right")
        self.diag_canvas = ImageCanvas(t, "Clique em Analisar agora para ver o que o bot reconhece na tela do jogo.")
        self.diag_canvas.grid(row=1, column=0, sticky="nsew")
        side = Panel(t, self.th, "Leituras", "Cada leitura traz a confiança, de 0 a 1.")
        side.grid(row=1, column=1, sticky="ns", padx=(px(12), 0))
        self.txt_diag = tk.Text(side.body, width=40, wrap="word", font=self.th.fonts["mono"], relief="flat",
                                background=T.SURFACE, foreground=T.INK, highlightthickness=0)
        self.txt_diag.grid(row=0, column=0, sticky="nsew")
        side.body.rowconfigure(0, weight=1)

    # -------------------------------------------------------------------- Mira
    def _build_aim(self):
        px, t = self.th.px, self.tab_aim
        t.columnconfigure(1, weight=1)
        t.rowconfigure(1, weight=1)
        calc = Panel(t, self.th, "Calculadora", "Distância em décimos da tela, a régua do jogo.")
        calc.grid(row=0, column=0, sticky="nsew", padx=(0, px(12)))
        self.aim_inputs = {}
        for i, (k, label, default) in enumerate((("distance", "Distância", "10"), ("wind", "Vento (+ a favor)", "0"),
                                                 ("dy", "Altura do alvo (+ acima)", "0"))):
            ttk.Label(calc.body, text=label, style="Surface.TLabel").grid(row=i, column=0, sticky="w", pady=px(3))
            e = ttk.Entry(calc.body, width=8)
            e.insert(0, default)
            e.grid(row=i, column=1, padx=(px(10), 0), pady=px(3))
            e.bind("<Return>", lambda ev: self.calc_aim())
            self.aim_inputs[k] = e
        ttk.Button(calc.body, text="Calcular", style="Primary.TButton", command=self.calc_aim).grid(
            row=3, column=0, columnspan=2, sticky="we", pady=(px(10), 0))
        opts = Panel(t, self.th, "Opções de disparo", "Ordenadas pela chance estimada de acerto.")
        opts.grid(row=0, column=1, sticky="nsew")
        opts.body.rowconfigure(0, weight=1)
        # as 7 opções inteiras; em janela baixa, 5 e a rolagem (senão a lista dos disparos ficava sem linhas)
        self.tree_aim = ttk.Treeview(opts.body, columns=("met", "ang", "for", "p", "base"), show="headings",
                                     height=5 if self.compact else 7)
        for col, text, w in (("met", "Método", 120), ("ang", "Ângulo", 64), ("for", "Força", 64),
                             ("p", "Chance", 70), ("base", "De onde vem", 400)):
            self.tree_aim.heading(col, text=text, anchor="w")
            self.tree_aim.column(col, width=px(w), stretch=col == "base", anchor="w")
        self.tree_aim.grid(row=0, column=0, sticky="nsew")
        asb = ttk.Scrollbar(opts.body, orient="vertical", command=self.tree_aim.yview)
        self.tree_aim.configure(yscrollcommand=asb.set)
        asb.grid(row=0, column=1, sticky="ns")
        shots = Panel(t, self.th, "Disparos registrados",
                      "Marque o resultado dos disparos para a mira aprender com o seu jogo.")
        shots.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(px(12), 0))
        sb = shots.body
        sb.rowconfigure(0, weight=1)
        self.tree_shots = ttk.Treeview(sb, columns=("id", "ang", "for", "vento", "dist", "prev", "imp", "res", "met",
                                                    "orig", "inst"), show="headings", height=5)
        for col, text, w in (("id", "#", 44), ("ang", "Ângulo", 60), ("for", "Força", 60), ("vento", "Vento", 60),
                             ("dist", "Alvo em", 70), ("prev", "Previsto", 70), ("imp", "Caiu em", 70),
                             ("res", "Resultado", 92), ("met", "Método", 80), ("orig", "Origem", 86),
                             ("inst", "Instância", 150)):
            self.tree_shots.heading(col, text=text, anchor="w")
            self.tree_shots.column(col, width=px(w), anchor="w")
        self.tree_shots.grid(row=0, column=0, sticky="nsew")
        ssb = ttk.Scrollbar(sb, orient="vertical", command=self.tree_shots.yview)
        self.tree_shots.configure(yscrollcommand=ssb.set)
        ssb.grid(row=0, column=1, sticky="ns")
        act = ttk.Frame(sb, style="Surface.TFrame")
        act.grid(row=1, column=0, columnspan=2, sticky="we", pady=(px(8), 0))
        ttk.Button(act, text="Acertou", command=lambda: self.mark_shot(True)).pack(side="left")
        ttk.Button(act, text="Errou", command=lambda: self.mark_shot(False)).pack(side="left", padx=(px(6), 0))
        ttk.Label(act, text="Caiu na distância", style="Surface.TLabel").pack(side="left", padx=(px(18), px(6)))
        self.impact_entry = ttk.Entry(act, width=7)
        self.impact_entry.pack(side="left")
        ttk.Button(act, text="Salvar", command=self.mark_impact).pack(side="left", padx=(px(6), 0))
        ttk.Button(act, text="Reajustar o modelo", command=self.refit).pack(side="right")
        self.lbl_stats = ttk.Label(sb, text="", style="SurfaceMuted.TLabel", wraplength=px(1000), justify="left")
        self.lbl_stats.grid(row=2, column=0, columnspan=2, sticky="w", pady=(px(6), 0))
        self.refresh_shots()

    # ---------------------------------------------------------- Configurações
    CFG_GROUPS = [
        ("Teclas do jogo", [
            ("automation.keys.angle_up", "Aumentar ângulo", str),
            ("automation.keys.angle_down", "Diminuir ângulo", str),
            ("automation.keys.fire", "Disparar", str),
            ("automation.keys.pass_turn", "Passar o turno (opcional)", str),
        ]),
        ("Força do disparo", [
            ("automation.power_mode", "Como controlar a força", ("timed", "visual")),
            ("automation.power_full_time_s", "Segundos até a força 100", float),
            ("automation.power_start_delay_s", "Espera até a barra começar (s)", float),
            ("automation.power_offset", "Compensação (pontos de força)", float),
            ("automation.min_seconds_between_shots", "Intervalo entre disparos (s)", float),
        ]),
        ("Limites da rotina", [
            ("instances.max_defeats", "Parar depois de quantas derrotas", int),
            ("instances.max_minutes", "Tempo máximo (minutos)", float),
            ("instances.unknown_state_timeout_s", "Pausar após tela desconhecida (s)", float),
            ("instances.action_timeout_s", "Recuperar se a tela parar (s)", float),
        ]),
        ("Reconhecimento", [
            ("thresholds.template", "Semelhança mínima das imagens (0 a 1)", float),
            ("thresholds.vision_min_confidence", "Confiança mínima para atirar (0 a 1)", float),
            ("ruler.units_per_screen", "Partes da régua na tela", float),
            ("safety.emergency_hotkey", "Tecla de emergência (vale ao reabrir)", str),
        ]),
    ]
    POWER_LABELS = {"timed": "Pelo tempo segurando a tecla", "visual": "Lendo a barra na tela"}

    def _build_config(self):
        px = self.th.px
        scroll = ScrollFrame(self.tab_cfg, self.th, width=900, style="TFrame")
        scroll.canvas.configure(background=T.BG)
        scroll.pack(fill="both", expand=True)
        s = scroll.inner
        s.columnconfigure(0, weight=1, uniform="cfg")
        s.columnconfigure(1, weight=1, uniform="cfg")
        c = self.svc.config
        self.cfg_vars: dict[str, tk.Variable] = {}
        self.cfg_types: dict[str, object] = {}
        auth = Panel(s, self.th, "Automação",
                     "As regras do DDClássico sobre programas de automação não puderam ser verificadas, e muitos "
                     "servidores punem bots. Leia os Termos do servidor antes de autorizar. O bot só joga sozinho "
                     "atividades PvE ou solo e nunca compra itens nem gasta moeda premium.")
        auth.grid(row=0, column=0, columnspan=2, sticky="we")
        self._cfg_check(auth.body, "automation.server_rules_confirmed",
                        "Li as regras do servidor e autorizo o modo automático por minha conta e risco")
        self._cfg_check(auth.body, "safety.require_foreground", "Só enviar comandos com a janela do jogo na frente")
        for i, (title, fields) in enumerate(self.CFG_GROUPS):
            p = Panel(s, self.th, title)
            p.grid(row=1 + i // 2, column=i % 2, sticky="nsew", pady=(px(12), 0),
                   padx=(0, px(12)) if i % 2 == 0 else (0, 0))
            p.body.columnconfigure(0, weight=1)
            for r, (key, label, typ) in enumerate(fields):
                ttk.Label(p.body, text=label, style="Surface.TLabel").grid(row=r, column=0, sticky="w", pady=px(3))
                cur = c.get(key)
                if isinstance(typ, tuple):
                    v = tk.StringVar(value=self.POWER_LABELS.get(cur, self.POWER_LABELS[typ[0]]))
                    ttk.Combobox(p.body, textvariable=v, state="readonly", width=26,
                                 values=[self.POWER_LABELS[o] for o in typ]).grid(row=r, column=1, sticky="e",
                                                                                   padx=(px(10), 0))
                else:
                    v = tk.StringVar(value="" if cur is None else str(cur))
                    ttk.Entry(p.body, textvariable=v, width=12).grid(row=r, column=1, sticky="e", padx=(px(10), 0))
                self.cfg_vars[key] = v
                self.cfg_types[key] = typ
        paid = Panel(s, self.th, "Botões pagos liberados",
                     "Nomes dos modelos de botão que gastam recursos e você autoriza, separados por vírgula. "
                     "Deixe vazio para bloquear todos.")
        paid.grid(row=3, column=0, columnspan=2, sticky="we", pady=(px(12), 0))
        self.paid_var = tk.StringVar(value=", ".join(c.get("automation.allowed_paid_templates", []) or []))
        ttk.Entry(paid.body, textvariable=self.paid_var).grid(row=0, column=0, sticky="we")
        foot = ttk.Frame(s)
        foot.grid(row=4, column=0, columnspan=2, sticky="we", pady=(px(14), 0))
        ttk.Button(foot, text="Salvar configurações", style="Primary.TButton", command=self.save_config).pack(
            side="left")
        ttk.Label(foot, text=f"Pasta de dados: {self.svc.paths.root}", style="Muted.TLabel").pack(side="left",
                                                                                                 padx=px(16))

    def _cfg_check(self, parent, key, text):
        v = tk.BooleanVar(value=bool(self.svc.config.get(key)))
        ttk.Checkbutton(parent, text=text, variable=v, style="Surface.TCheckbutton").grid(
            sticky="w", pady=(self.th.px(4), 0))
        self.cfg_vars[key] = v

    def _build_log(self):
        self.txt_log = tk.Text(self.tab_log, wrap="none", font=self.th.fonts["mono"], relief="flat",
                               background=T.SURFACE, foreground=T.INK, highlightthickness=0,
                               padx=self.th.px(8), pady=self.th.px(6))
        sb = ttk.Scrollbar(self.tab_log, orient="vertical", command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=sb.set)
        self.txt_log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _bind_keys(self):
        self.root.bind("<F5>", lambda e: self.btn_start.instate(["!disabled"]) and self.start())
        self.root.bind("<F6>", lambda e: self.btn_pause.instate(["!disabled"]) and self.toggle_pause())
        self.root.bind("<F8>", lambda e: self.btn_stop.instate(["!disabled"]) and self.stop())

    # ================================================================= ações
    def info(self, text, error=False):
        self.notice(text, error)

    def refresh_windows(self):
        """Procura o jogo (em thread: consultar janelas e processos leva alguns ms)."""
        if self._locating or self.detect_dialog is not None:
            return
        self._locating = True

        def work():
            try:
                self._locate_queue.put((self.svc.auto_connect(), None))
            except Exception as exc:
                log.exception("procura da janela do jogo")
                self._locate_queue.put((None, exc))
            finally:
                self._locating = False
        threading.Thread(target=work, daemon=True, name="procura-janela").start()

    def _drain_locate(self):
        try:
            found, exc = self._locate_queue.get_nowait()
        except queue.Empty:
            return
        if exc is not None or found is None:
            self.lbl_window.configure(text="erro ao procurar a janela")
            return
        state = found.state
        if state == "jogo" and not found.confident and self.svc.window is None:
            state = "confirmar"
        self.window_state = state
        self._show_window_label()

    def _show_window_label(self):
        self._update_buttons()  # Iniciar no jogo real depende da janela conectada
        w = self.svc.window
        if w is not None:
            title = (w.title or w.exe or "janela").strip()
            if len(title) > 40:
                title = title[:39] + "…"
            self.lbl_window.configure(text=f"conectado: {title} ({w.width}×{w.height})")
            self.btn_detect.configure(style="TButton")
            return
        self.btn_detect.configure(style="Primary.TButton")
        self.lbl_window.configure(text={
            "launcher_sem_jogo": "launcher aberto, aguardando o jogo",
            "confirmar": "encontrado; clique em Detectar jogo para confirmar",
            "escolher": "mais de uma janela possível; clique em Detectar jogo",
            "nada": "não encontrado",
        }.get(self.window_state, "procurando..."))

    def open_detect(self):
        if self.detect_dialog is not None:
            try:
                self.detect_dialog.deiconify()
                self.detect_dialog.lift()
                return
            except tk.TclError:
                self.detect_dialog = None
        if self.svc.runner and self.svc.runner.alive:
            self.notice("Pare a rotina antes de detectar o jogo de novo.", True)
            return
        from .detect_dialog import DetectDialog
        self.detect_dialog = DetectDialog(self, self.svc, on_done=self._detect_done)

    def _detect_done(self):
        self.detect_dialog = None
        self.window_state = "jogo" if self.svc.window is not None else self.window_state
        self._show_window_label()
        if self.svc.window is not None:
            self.notice("Jogo conectado. O JonFlow reencontra essa janela sozinho nas próximas vezes.")
        self.refresh_windows()

    def _toggle_demo(self):
        self.refresh_activities()
        self.notice("Modo demonstração ligado: nada é enviado ao jogo." if self.simulated.get()
                    else "Modo demonstração desligado.")

    def refresh_activities(self):
        defs, errors = self.svc.activities()
        for e in errors:
            self.notice(f"Arquivo de atividade inválido: {e}", True)
        if self.simulated.get():
            defs = defs + [demo_activity("partida")]
        self.activities = {d.key: d for d in defs}
        self._fill_activity_list()

    def _status_of(self, d: ActivityDef) -> tuple[str, str]:
        """Texto curto e cor da coluna Estado da lista de atividades."""
        from ..catalog import MISSING, USER_OFF
        if self.simulated.get() or d.key.startswith(DEMO_KEY):
            return "▶ demo", "pronta"
        if not d.auto_allowed:
            return "○ só assistida", "vazio"
        state, _ = self.svc.availability_of(d)
        if state == USER_OFF:
            return "✕ indisponível", "ausente"
        if state == MISSING:
            return "✕ não achada", "ausente"
        if any(m.required for m in self.svc.readiness(d)):
            return "! calibrar", "pendente"
        return "✓ pronta", "pronta"

    def _fill_activity_list(self):
        """Duas seções sempre visíveis; a atividade escolhida antes continua escolhida."""
        tree = self.tree_act
        sel = tree.selection()
        if sel and not sel[0].startswith(("sec_", "vazio_")):
            self._chosen = sel[0]  # a escolha atual vale mesmo que o evento de seleção ainda não tenha chegado
        tree.delete(*tree.get_children())
        for kind in ("instancia", "partida"):
            sec = f"sec_{kind}"
            tree.insert("", "end", iid=sec, text=KIND_LABELS[kind], open=True, tags=("secao",))
            items = [d for d in self.activities.values() if d.kind == kind]
            for d in items:
                text, tag = self._status_of(d)
                tree.insert(sec, "end", iid=d.key, text=self._label(d), values=(text,), tags=(tag,))
            if not items:
                tree.insert(sec, "end", iid=f"vazio_{kind}", text="nenhuma ainda",
                            values=("veja como",), tags=("vazio",))
        keep = self._chosen if self._chosen in self.activities else None
        target = keep or next((d.key for d in self.activities.values() if d.kind == "instancia"), None)
        if target:
            tree.selection_set(target)
            tree.see(target)
        self._describe()
        self._update_buttons()

    def _on_activity_selected(self):
        sel = self.tree_act.selection()
        if sel and sel[0].startswith("sec_"):
            # a linha da seção não é atividade: vai para a primeira dela
            kids = self.tree_act.get_children(sel[0])
            if kids:
                self.tree_act.selection_set(kids[0])
                return
        d = self.selected_activity()
        if d is not None:
            self._chosen = d.key
        self._describe()
        self._update_buttons()
        if hasattr(self, "cb_strategy"):
            self._fill_strategy_page()

    def _label(self, d: ActivityDef):
        if d.key.startswith(DEMO_KEY):
            return d.name
        return d.name if d.builtin else f"{d.name} (capturada)"

    def selected_activity(self) -> ActivityDef | None:
        sel = self.tree_act.selection() if hasattr(self, "tree_act") else ()
        return self.activities.get(sel[0]) if sel else None

    def _describe(self):
        d = self.selected_activity()
        sel = self.tree_act.selection()
        self._show_readiness(d)
        if d is None:
            kind = sel[0].split("_", 1)[-1] if sel and sel[0].startswith("vazio_") else "instancia"
            self.lbl_act_title.configure(text="Nenhuma modalidade de partida" if kind == "partida"
                                         else "Escolha uma atividade")
            if kind == "partida":
                text = ("As modalidades de partida vêm do seu cliente: com o jogo no menu de partidas, vá em "
                        "Calibração > Menu, capture a tela e nomeie cada modalidade contra o computador (PvE). "
                        "Partidas contra jogadores nunca são automáticas.")
            else:
                text = "Escolha uma instância na lista ao lado."
            if not self.simulated.get():
                text += " Para conhecer o programa sem o jogo, ligue o modo demonstração."
            self.lbl_desc.configure(text=text)
            self.lbl_state.configure(text="")
            return
        self.lbl_act_title.configure(text=d.name)
        prof = self.svc.profile_for(d)
        if d.key.startswith(DEMO_KEY):
            self.lbl_desc.configure(text="Simulação para testar o programa: lobby, menu, sala, batalha e resultado "
                                    "acontecem num jogo de mentira. Nada é enviado ao DDClássico.")
        elif not d.auto_allowed:
            self.lbl_desc.configure(text="Envolve outros jogadores: o bot não joga sozinho (use a mira assistida).")
        elif prof is not None:
            stages = " → ".join(st.name for st in prof.stages)
            solo = SOLO_LABELS.get(prof.solo, prof.solo)
            conf = CONFIDENCE_LABELS.get(prof.confidence, prof.confidence)
            self.lbl_desc.configure(text=f"Estratégia {prof.name}: {stages}. {solo.capitalize()}; fontes de "
                                    f"confiança {conf}.")
        elif d.kind == "instancia":
            self.lbl_desc.configure(text="Sem estratégia de instância: mira o inimigo mais à esquerda (troque em "
                                    "Calibração > Alvos).")
        else:
            self.lbl_desc.configure(text="Partida capturada do menu do seu jogo.")
        self.lbl_state.configure(text=self._state_text(d))

    def _state_text(self, d: ActivityDef) -> str:
        if self.simulated.get() or d.key.startswith(DEMO_KEY):
            return "Modo demonstração: roda no jogo simulado; nada é enviado ao DDClássico."
        w = self.svc.window
        conn = (f"Jogo conectado ({w.width}×{w.height})." if w is not None else
                "Jogo não conectado (Detectar jogo, no topo).")
        _, avail = self.svc.availability_of(d)
        known = self._known_items(d, self.svc.readiness(d))
        return f"{conn} No seu jogo: {avail}. {known}"

    def _known_items(self, d: ActivityDef, missing) -> str:
        """Quanto da calibração desta atividade o bot já reconhece (sem nomes técnicos)."""
        from ..readiness import check
        everything = check(d, lambda k: False, _Blank(), False, False, profile=self.svc.profile_for(d),
                           difficulty_labels=self.svc.catalog.difficulty_templates(),
                           option_labels=self.svc.catalog.option_templates())
        total = sum(1 for m in everything if m.required)
        done = total - sum(1 for m in missing if m.required)
        return f"Reconhecidos: {done} de {total} itens obrigatórios."

    def _show_readiness(self, d):
        """Diz antes de iniciar o que falta calibrar para a atividade rodar sozinha no jogo."""
        from ..catalog import MISSING, USER_OFF
        self._missing_required = ""
        if d is None:
            self.lbl_ready.configure(text="")
            self.btn_goto_calib.configure(text="Capturar opções do jogo", command=self._goto_options)
            self.btn_avail.pack_forget()
            return
        demo = d.key.startswith(DEMO_KEY) or self.simulated.get()
        if demo or not d.auto_allowed:
            self.lbl_ready.configure(text="", style="SurfaceMuted.TLabel")
            self.btn_goto_calib.pack_forget()
            self.btn_avail.pack_forget()
            return
        from ..readiness import summary
        missing = self.svc.readiness(d)
        req = summary(missing, limit=3)
        first = summary(missing, limit=1)  # uma linha: a lista inteira, com instruções, fica em Ver pendências
        self._missing_required = req
        state, _ = self.svc.availability_of(d)
        if state in (MISSING, USER_OFF):
            self.lbl_ready.configure(text="Esta atividade não foi encontrada no seu jogo: o bot não a inicia "
                                     "nem escolhe outra no lugar. Se ela aparecer no menu, capture-a de novo em "
                                     "Calibração > Menu ou clique em Aparece no meu jogo.", style="SurfaceError.TLabel")
        elif req:
            n = sum(1 for m in missing if m.required)
            self.lbl_ready.configure(text=f"Falta calibrar ({n}): {first}.", style="SurfaceError.TLabel")
        else:
            self.lbl_ready.configure(text="✓ Calibração completa para esta atividade.", style="SurfaceMuted.TLabel")
        self.btn_goto_calib.configure(text="Ver pendências" if req else "Conferir a calibração",
                                      command=self._goto_pending)
        self.btn_goto_calib.pack(side="left")
        self.btn_avail.configure(text="Aparece no meu jogo" if state in (MISSING, USER_OFF)
                                 else "Não aparece no meu jogo")
        self.btn_avail.pack(side="left", padx=(self.th.px(8), 0))
        if state in (MISSING, USER_OFF):
            self._missing_required = req or "a atividade não está no seu jogo"

    def _toggle_availability(self):
        from ..catalog import MISSING, USER_OFF, UNVERIFIED
        d = self.selected_activity()
        if d is None or d.key.startswith(DEMO_KEY):
            return
        state, _ = self.svc.availability_of(d)
        if state in (MISSING, USER_OFF):
            self.svc.set_availability(d, UNVERIFIED, "marcada por você para conferir de novo")
            self.notice(f"{d.name}: o bot volta a procurá-la no menu do jogo.")
        else:
            self.svc.set_availability(d, USER_OFF, "marcada por você")
            self.notice(f"{d.name}: marcada como indisponível no seu jogo.")
        self._fill_activity_list()

    def _goto_calibration(self):
        self.nb.select(self.tab_calib)

    def _goto_pending(self):
        self.nb.select(self.tab_calib)
        if hasattr(self, "page_pending"):
            self.calib_nb.select(self.page_pending)
            self._fill_pending()

    def _goto_options(self):
        self.nb.select(self.tab_calib)
        if hasattr(self, "page_menu"):
            self.calib_nb.select(self.page_menu)

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
            self.notice("Escolha uma instância ou partida antes de iniciar.", True)
            return
        simulated = self.simulated.get() or d.key.startswith(DEMO_KEY)
        if not simulated and self.svc.window is None:
            self.notice("Conecte o jogo (Detectar jogo, no topo) antes de iniciar.", True)
            return
        self.btn_start.state(["disabled"])
        if simulated:
            self._start_finished(self.svc.start(d, self._runs(), simulated=True), True)
            return
        # no jogo real, iniciar procura a janela e espera o jogo vir para a frente (até ~2 s):
        # fora da thread da interface, que não pode travar
        self._starting = True
        result: "queue.Queue[tuple[bool, str]]" = queue.Queue(maxsize=1)
        runs = self._runs()

        def work():
            try:
                result.put(self.svc.start(d, runs, simulated=False))
            except Exception as exc:  # erro inesperado vira mensagem, não trava o botão
                log.exception("falha ao iniciar")
                result.put((False, str(exc)))

        def wait():
            try:
                res = result.get_nowait()
            except queue.Empty:
                self.root.after(100, wait)
                return
            self._starting = False
            self._start_finished(res, False)
        self.notice("Iniciando: conferindo a janela do jogo...")
        threading.Thread(target=work, daemon=True, name="iniciar").start()
        self.root.after(100, wait)

    def _start_finished(self, res: tuple[bool, str], simulated: bool):
        ok, why = res
        if not ok:
            tip = advice(why)
            self.notice(f"Não foi possível iniciar: {why}. {tip}".strip(), True)
            if not headless():
                messagebox.showwarning("Não foi possível iniciar", f"{why}\n\n{tip}".strip())
        elif not simulated and self.svc.config.get("ui.minimize_during_run", True):
            # a janela do JonFlow não pode ficar por cima do jogo (captura e cliques); volta ao pausar ou terminar
            self._minimized_for_run = True
            self.root.iconify()
        self.progress.configure(value=0)
        self._update_buttons()

    def toggle_pause(self):
        if self.svc.status == RunStatus.PAUSED:
            self.svc.resume()
        else:
            self.svc.pause()
        self._update_buttons()

    def stop(self):
        # parar não pode travar a interface: espera em thread
        threading.Thread(target=self.svc.stop, daemon=True, name="parar").start()
        self.btn_stop.state(["disabled"])
        self.root.after(300, self._update_buttons)

    def _update_buttons(self):
        st = self.svc.status
        running = self.svc.runner is not None and self.svc.runner.alive
        d = self.selected_activity()
        demo = d is not None and (d.key.startswith(DEMO_KEY) or self.simulated.get())
        ready = d is not None and (d.auto_allowed or d.key.startswith(DEMO_KEY))
        if ready and not demo:
            # no jogo real: só com o jogo conectado, a calibração obrigatória completa e a atividade não marcada
            # como ausente do jogo (o motivo aparece na faixa de estado e embaixo da atividade)
            ready = self.svc.window is not None and not self._missing_required
        busy = running or self._starting
        self.btn_start.state(["disabled"] if busy or not ready else ["!disabled"])
        if self._minimized_for_run and (not running or st != RunStatus.RUNNING):
            # pausou (precisa de você), terminou ou falhou: a janela volta para mostrar o motivo
            self._minimized_for_run = False
            try:
                self.root.deiconify()
                self.root.lift()
            except tk.TclError:
                pass
        self.btn_pause.state(["!disabled"] if running else ["disabled"])
        paused = st == RunStatus.PAUSED
        self.btn_pause.configure(text="Retomar (F6)" if paused else "Pausar (F6)",
                                 style="Primary.TButton" if paused else "TButton")
        self.btn_stop.state(["!disabled"] if running else ["disabled"])

    # ------------------------------------------------------------- calibração
    def _on_tab_changed(self):
        if not hasattr(self, "tree_act"):
            return
        tab = self.nb.select()
        if tab == str(self.tab_home):
            self._fill_activity_list()  # o que falta pode ter mudado na Calibração
        elif tab == str(self.tab_calib) and hasattr(self, "tree_pending"):
            self._fill_pending()

    def calib_capture(self, then=None):
        """Captura a tela do jogo fora da thread da interface (a captura confere a imagem com a tela)."""
        if getattr(self, "_capturing", False):
            return
        self._capturing = True
        self.btn_capture.state(["disabled"])
        self.notice("Capturando a tela do jogo...")

        def done(frame, why):
            self._capturing = False
            self.btn_capture.state(["!disabled"])
            if frame is None:
                self.notice(f"Não foi possível capturar: {why or 'conecte o jogo em Detectar jogo'}. "
                            "Deixe a janela do jogo visível (não minimizada).", True)
                return
            self.calib_canvas.show(frame)
            self._tiles = []
            self.lst_tiles.delete(0, "end")
            self._suggestions = []
            self.btn_use_suggest.state(["disabled"])
            self.lbl_suggest.configure(text="")
            self.notice("Tela capturada. Arraste sobre a imagem para selecionar.")
            if then is not None:
                then()
        self.capture_game(done)

    def capture_game(self, done, hide_if_covered=True):
        """``done(frame, motivo)`` na thread da interface.

        Se a imagem for recusada porque a janela do JonFlow está na frente do jogo, ela sai da frente só
        durante a captura e volta logo depois (sem camada escura nem janela por cima do jogo).
        """
        result: "queue.Queue[tuple]" = queue.Queue(maxsize=1)

        def work():
            try:
                frame = self.svc.grab()
                src = self.svc.source
                why = "" if frame is not None else (getattr(src, "unavailable", "") if src is not None
                                                     else "o jogo não está conectado")
            except Exception as exc:
                log.exception("captura do jogo")
                frame, why = None, str(exc)
            finally:
                self.svc.release_thread()
            result.put((frame, why))

        def poll():
            try:
                frame, why = result.get_nowait()
            except queue.Empty:
                self.root.after(50, poll)
                return
            covered = frame is None and ("na frente" in why or "visível" in why)
            if covered and hide_if_covered and winapi_is_windows() and self.root.state() != "iconic":
                self.root.iconify()

                def back(frame2, why2):
                    try:
                        self.root.deiconify()
                        self.root.lift()
                    except tk.TclError:
                        pass
                    done(frame2, why2)
                self.root.after(450, lambda: self.capture_game(back, hide_if_covered=False))
                return
            done(frame, why)
        threading.Thread(target=work, daemon=True, name="captura-jogo").start()
        self.root.after(50, poll)

    def _on_calib_select(self, rect):
        self.lbl_sel.configure(text=f"Seleção: {rect[2]}×{rect[3]} px em ({rect[0]}, {rect[1]})")

    # pendências: a lista da atividade escolhida no Início, com a instrução de cada item
    def _fill_pending(self):
        if not hasattr(self, "tree_pending"):
            return
        d = self.selected_activity()
        tree = self.tree_pending
        tree.delete(*tree.get_children())
        self._pending = []
        if d is None or d.key.startswith(DEMO_KEY) or not d.auto_allowed:
            self.lbl_pending.configure(text="Escolha no Início uma instância ou partida (a de demonstração não "
                                       "precisa de calibração).")
            self.btn_pending.state(["disabled"])
            return
        items = sorted(self.svc.readiness(d), key=lambda m: not m.required)
        self._pending = items
        for i, m in enumerate(items):
            mark = "obrigatório" if m.required else "recomendado"
            tree.insert("", "end", iid=str(i), values=(f"{m.label} — {mark}",),
                        tags=("obrigatorio" if m.required else "recomendado",))
        if items:
            tree.selection_set("0")
            self._on_pending_select()
            self.btn_pending.state(["!disabled"])
        else:
            self.lbl_pending.configure(text=f"Nada pendente para {d.name}: a calibração está completa.")
            self.btn_pending.state(["disabled"])

    def _pending_item(self):
        sel = self.tree_pending.selection()
        return self._pending[int(sel[0])] if sel and sel[0].isdigit() and int(sel[0]) < len(self._pending) else None

    def _on_pending_select(self):
        m = self._pending_item()
        if m is not None:
            self.lbl_pending.configure(text=f"{m.how} (em {m.where})")

    def _do_pending(self):
        """Abre a página certa já com o item escolhido; sem imagem ainda, captura a tela do jogo."""
        m = self._pending_item()
        if m is None:
            return
        where = m.where
        if where.endswith("Modelos"):
            self.calib_nb.select(self.page_models)
            if m.key in self._tpl_keys:
                self.cb_tpl.current(self._tpl_keys.index(m.key))
        elif where.endswith("Regiões"):
            self.calib_nb.select(self.page_regions)
            if m.key in REGION_KEYS:
                self.cb_region.current(list(REGION_KEYS).index(m.key))
        elif where.endswith("Números"):
            self.calib_nb.select(self.page_digits)
            if m.key in ("angle", "wind"):
                self.digit_kind.set(m.key)
        elif where.endswith("Menu"):
            self.calib_nb.select(self.page_menu)
            keys = [k for k, _ in self._opt_targets]
            if m.key in keys:
                self.opt_what.current(keys.index(m.key))
                self._on_option_kind()
        else:
            self.calib_nb.select(self.page_targets)
            self._fill_strategy_page()
            if m.key in self._role_keys:
                self.cb_role.current(self._role_keys.index(m.key))
        self.notice(m.how)
        if self.calib_canvas.frame is None:
            self.calib_capture()

    # sugestões automáticas de regiões (confirmadas pelo usuário antes de salvar)
    def suggest_regions(self):
        frame = self.calib_canvas.frame
        if frame is None:
            self.calib_capture(then=self.suggest_regions)
            return
        from ..vision.autodetect import suggest_regions
        found = suggest_regions(frame)
        self._suggestions = found
        self._suggest_replace = False
        if not found:
            self.lbl_suggest.configure(text="Nenhuma região reconhecida nesta imagem. Capture uma batalha, de "
                                       "preferência no seu turno, ou marque cada região arrastando.")
            self.btn_use_suggest.state(["disabled"])
            return
        from ..vision.autodetect import draw_suggestions
        self.calib_canvas.show(draw_suggestions(frame, found), keep_selection=False)
        self.calib_canvas.frame = frame  # a seleção continua sobre a imagem original
        lines = [f"{REGION_KEYS.get(x.key, x.key)}: {x.why} (confiança {x.confidence:.2f})" for x in found]
        self.lbl_suggest.configure(text="Confira na imagem antes de usar:\n" + "\n".join(lines))
        self.btn_use_suggest.state(["!disabled"])

    def find_angle_by_keys(self):
        """No seu turno: aperta ↑ e ↓ (não atira) e sugere como região do ângulo o que mudou na tela."""
        self.notice("Achando o ângulo: no seu turno, o bot aperta ↑ e depois ↓ (não atira)...")
        result: "queue.Queue[tuple]" = queue.Queue(maxsize=1)

        def work():
            try:
                result.put(self.svc.find_angle_region() + ("",))
            except Exception as exc:
                result.put((None, None, str(exc)))

        def poll():
            try:
                found, frame, err = result.get_nowait()
            except queue.Empty:
                self.root.after(100, poll)
                return
            if err:
                self.notice(f"Não foi possível achar o ângulo: {err}", True)
                return
            if found is None:
                self.notice("Nada mudou só no número do ângulo: confira se é o seu turno e se as teclas do ângulo "
                            "estão certas (Configurações), ou marque a região arrastando.", True)
                return
            from ..vision.autodetect import draw_suggestions
            self._suggestions = [found]
            self._suggest_replace = True  # pedido explícito: troca a região do ângulo que já existia
            self.calib_canvas.show(draw_suggestions(frame, [found]))
            self.calib_canvas.frame = frame
            self.lbl_suggest.configure(text=f"{REGION_KEYS['angle']}: {found.why}. Confira na imagem antes de usar.")
            self.btn_use_suggest.state(["!disabled"])
        threading.Thread(target=work, daemon=True, name="angulo-pelas-teclas").start()
        self.root.after(100, poll)

    def use_suggestions(self):
        """Salva as regiões sugeridas que ainda não existem (as que você já marcou ficam como estão)."""
        saved, kept = [], []
        for x in self._suggestions:
            key = "ruler.playfield" if x.key == "playfield" else f"regions.{x.key}"
            if self.svc.config.get(key) and x.key != "playfield" and not getattr(self, "_suggest_replace", False):
                kept.append(REGION_KEYS.get(x.key, x.key))
                continue
            self.svc.config.set(key, list(x.roi))
            saved.append(REGION_KEYS.get(x.key, x.key))
        if saved and self._save_config_file():
            msg = f"Regiões salvas: {', '.join(saved)}."
            if kept:
                msg += f" Mantidas as que você já tinha marcado: {', '.join(kept)}."
            self.notice(msg)
        elif kept:
            self.notice(f"Nada mudou: você já tinha marcado {', '.join(kept)}. Para trocar, marque arrastando.")
        self.btn_use_suggest.state(["disabled"])

    def save_region(self):
        frame, sel = self.calib_canvas.frame, self.calib_canvas.selection_px
        if frame is None or not sel:
            self.notice("Capture a tela e arraste sobre a região antes de salvar.", True)
            return
        key = list(REGION_KEYS)[self.cb_region.current()]
        frac = px_to_frac(sel, frame.shape)
        self.svc.config.set("ruler.playfield" if key == "playfield" else f"regions.{key}", frac)
        if self._save_config_file():
            self.notice(f"Região salva: {REGION_KEYS[key]}.")

    def save_template(self):
        img = self.calib_canvas.selection_image()
        if img is None:
            self.notice("Capture a tela e arraste sobre o elemento antes de salvar.", True)
            return
        key = self._tpl_keys[self.cb_tpl.current()]
        self.svc.templates.add(key, img)
        n = len(self.svc.templates.get(key))
        self.lbl_tpl.configure(text=f"{self.cb_tpl.get()}: {n} amostra(s).")
        self.notice(f"Modelo salvo: {self.cb_tpl.get()}.")

    def _strategy_target(self):
        """Atividade do Início que a página Alvos edita (as de demonstração não são gravadas)."""
        d = self.selected_activity()
        return None if d is None or d.key.startswith(DEMO_KEY) or d.kind != "instancia" else d

    def _fill_strategy_page(self):
        d = self._strategy_target()
        prof = self.svc.profile_for(d) if d else None
        key = prof.key if prof else None
        if key is not None and key not in self._strategy_keys:
            key = None
        self.cb_strategy.current(self._strategy_keys.index(key) if key in self._strategy_keys else 0)
        if d is not None and d.builtin and prof is not None:
            self.cb_strategy.set(prof.name)  # pré-cadastrada: estratégia fixa, mostrada sem poder trocar
        self.cb_strategy.state(["!disabled"] if d and not d.builtin else ["disabled"])
        tpls = prof.templates() if prof else {}
        needed = prof.required_templates() if prof else {}
        self._role_keys = list(tpls)
        self.cb_role["values"] = [f"{label.split(' (')[0]}{' (obrigatório)' if k in needed else ''} — "
                                  f"{len(self.svc.templates.get(k))} amostra(s)" for k, label in tpls.items()]
        if tpls:
            self.cb_role.current(0)
        else:
            self.cb_role.set("")
        for w in (self.cb_role, self.btn_role):
            w.state(["!disabled"] if tpls else ["disabled"])
        if d is None:
            text = "Escolha no Início uma instância."
        elif prof is None:
            text = "Sem estratégia: o bot mira o inimigo mais à esquerda em todas as etapas."
        else:
            fixed = "Estratégia pré-cadastrada. " if d.builtin else ""
            text = (f"{fixed}{prof.describe()} Confiança das fontes: "
                    f"{CONFIDENCE_LABELS.get(prof.confidence, prof.confidence)}. "
                    + " ".join(prof.limits[:2])).strip()
        self.lbl_strategy.configure(text=text)

    def set_strategy(self):
        d = self._strategy_target()
        if d is None:
            return
        try:
            self.svc.set_strategy(d, self._strategy_keys[max(0, self.cb_strategy.current())])
        except (ValueError, OSError) as exc:
            self.notice(f"Não foi possível trocar a estratégia: {exc}", True)
        self._fill_strategy_page()
        self._describe()

    def save_role_template(self):
        img = self.calib_canvas.selection_image()
        if img is None or not self._role_keys or self.cb_role.current() < 0:
            self.notice("Escolha a estratégia, capture a tela da batalha e arraste sobre o alvo.", True)
            return
        key = self._role_keys[self.cb_role.current()]
        self.svc.templates.add(key, img)
        self._fill_strategy_page()
        self.notice(f"Modelo salvo: {key}.")

    def learn_digits(self):
        frame = self.calib_canvas.frame
        kind = self.digit_kind.get()
        roi = self.svc.config.get(f"regions.{kind}")
        name = "ângulo" if kind == "angle" else "vento"
        if frame is None or roi is None:
            self.notice(f"Capture a tela e salve a região do {name} em Regiões primeiro.", True)
            return
        sub, _ = crop(frame, roi)
        reader = self.svc.perception.angle_reader if kind == "angle" else self.svc.perception.wind_reader
        text = self.digit_value.get().strip()
        if kind == "wind":
            # o sentido do vento vem das setas (Modelos); um "-" aprendido como dígito inverteria a leitura
            text = text.lstrip("-+").strip()
        if not text or not reader.learn(sub, text):
            self.notice(f"Não consegui separar os dígitos. Confira o número digitado e a região do {name}.", True)
            return
        status = "pronto para ler" if reader.trained else "precisa de mais exemplos"
        self.notice(f"Aprendido o {name} {text}: {status}.")

    def detect_options(self):
        frame = self.calib_canvas.frame
        if frame is None:
            self.notice("Capture a tela com o menu do jogo aberto primeiro.", True)
            return
        self._tiles = detect_option_tiles(frame)
        self.lst_tiles.delete(0, "end")
        for i, (x, y, w, h) in enumerate(self._tiles):
            self.lst_tiles.insert("end", f"Opção {i + 1}  ({w}×{h} px)")
        self.notice(f"{len(self._tiles)} opção(ões) encontrada(s). Escolha uma e dê um nome." if self._tiles else
                    "Nenhuma opção encontrada. Arraste sobre a opção na imagem para selecioná-la.")

    def _on_tile_select(self, _e=None):
        sel = self.lst_tiles.curselection()
        if sel:
            self.calib_canvas.selection_px = self._tiles[sel[0]]
            self.calib_canvas.redraw()

    def _on_option_kind(self):
        """Opção de uma instância da lista: só salva a imagem. Outra opção: nome e categoria da atividade nova."""
        i = self.opt_what.current()
        known = 0 <= i < len(self._opt_targets)
        for w in (self.opt_name, self.opt_cat):
            w.state(["disabled"] if known else ["!disabled"])
        self.btn_create_opt.configure(text="Salvar opção" if known else "Criar atividade")

    def create_option(self):
        img = self.calib_canvas.selection_image()
        if img is None:
            self.notice("Selecione uma opção (na lista ou arrastando) antes de salvar.", True)
            return
        i = self.opt_what.current()
        if 0 <= i < len(self._opt_targets):
            tpl, name = self._opt_targets[i]
            self.svc.templates.add(tpl, img)
            seen = self.svc.mark_options_seen([tpl])
            self.refresh_activities()
            self.notice(f"Opção {name} salva ({len(self.svc.templates.get(tpl))} amostra(s)). Vale para "
                        f"{', '.join(seen) or 'todas as dificuldades dela'}.")
            return
        name = self.opt_name.get().strip()
        if not name:
            self.notice("Digite um nome para a atividade nova.", True)
            return
        kind = "partida" if i == len(self._opt_targets) + 1 else "instancia"
        category = self._cat_keys[max(0, self.opt_cat.current())]
        try:
            d = self.svc.create_activity_from_image(img, name, kind, category)
        except ValueError as exc:
            self.notice(str(exc), True)
            return
        self._chosen = d.key
        self.refresh_activities()
        self.notice(f"Atividade criada: {d.name}. Capture também os botões comuns em Modelos, se ainda não fez.")

    def check_visible_options(self):
        frame = self.calib_canvas.frame
        if frame is None:
            self.notice("Capture a tela primeiro.", True)
            return
        th = float(self.svc.config.get("thresholds.template", 0.8))
        found = find_known_options(frame, self.svc.templates, th, "instancia_") + \
            find_known_options(frame, self.svc.templates, th, "partida_")
        names = self.svc.mark_options_seen([k for k, _ in found])
        labels = dict(self._opt_targets)
        text = "\n".join(f"{labels.get(k, k)} (semelhança {s:.2f})" for k, s in found) or \
            "Nenhuma opção conhecida aparece nesta captura."
        if names:
            text += "\n\nMarcadas como vistas no menu: " + ", ".join(names)
            self.refresh_activities()
        if headless():
            self.notice(text.replace("\n", "; "))
        else:
            messagebox.showinfo("Opções conhecidas nesta captura", text)

    def test_controls(self):
        self.notice("Testando as teclas do ângulo...")

        def work():
            try:
                msg = self.svc.test_controls()
            except Exception as exc:
                msg = f"Teste de controles: {exc}"
            self.svc.push_event("etapa" if msg.startswith("OK") else "aviso", msg)
        threading.Thread(target=work, daemon=True, name="teste-controles").start()

    def delete_activity(self):
        d = self.selected_activity()
        if d is None or d.key.startswith(DEMO_KEY) or d.builtin:
            self.notice("Escolha no Início uma atividade capturada por você (as pré-cadastradas não são excluídas).",
                        True)
            return
        if headless() or messagebox.askyesno("Excluir atividade",
                                             f"Excluir a atividade {d.name}? Os modelos capturados ficam."):
            self.svc.delete_activity(d)
            self.refresh_activities()
            self.notice(f"Atividade excluída: {d.name}.")

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
                self.svc.release_thread()  # cada thread abre a própria captura: libera ao sair
                self._diag_busy = False
        threading.Thread(target=work, daemon=True, name="diagnostico").start()

    def save_capture(self):
        def done(frame, why):
            if frame is None:
                self.notice(f"Não foi possível capturar a janela do jogo: {why or 'conecte o jogo'}.", True)
                return
            self.notice(f"Captura salva em {self.svc.save_capture(frame)}")
        self.capture_game(done)

    def toggle_assist(self):
        if self.assist_on.get():
            try:
                self.svc.start_assist()
                self.notice("Mira assistida ligada: as sugestões aparecem no Início.")
            except RuntimeError as exc:
                self.assist_on.set(False)
                self.notice(str(exc), True)
        else:
            self.svc.stop_assist()
            self.notice("Mira assistida desligada.")

    # ------------------------------------------------------------------ mira
    def calc_aim(self):
        try:
            vals = {k: float(e.get().replace(",", ".")) for k, e in self.aim_inputs.items()}
        except ValueError:
            self.notice("Use números na calculadora, por exemplo 7,5.", True)
            return
        rec = self.svc.recommend(vals["distance"], vals["wind"], vals["dy"])
        self.tree_aim.delete(*self.tree_aim.get_children())
        for c in pick_options(rec.candidates):
            self.tree_aim.insert("", "end", values=(method_label(c.method), f"{c.angle}°", f"{c.force:.1f}",
                                                    f"{c.hit_probability:.0%}", "; ".join(c.basis)))
        if not rec.candidates:
            self.notice(f"Sem opções: {rec.reason}.", True)

    def refresh_shots(self):
        self.tree_shots.delete(*self.tree_shots.get_children())
        names = {p.key: p.name for p in self.svc.profiles.values()}
        for r in self.svc.store.all(limit=200):
            res = "acerto" if r.hit else ("erro" if r.hit is False else "sem resultado")
            origin = "jogo real" if r.source == "observado" else r.source
            self.tree_shots.insert("", "end", iid=str(r.id), values=(
                r.id, f"{r.angle:.0f}°", f"{r.force:.1f}", f"{r.wind:+.1f}", f"{r.distance:.2f}",
                "—" if r.predicted_x is None else f"{r.predicted_x:.2f}",
                "—" if r.impact_x is None else f"{r.impact_x:.2f}", res, method_label(r.method), origin,
                names.get(r.instance, r.instance or "—")))
        st = self.svc.calibrator.stats()
        if not st["disparos"] and not st["outros_cenarios"]:
            self.lbl_stats.configure(text="Nenhum disparo registrado no jogo real ainda. As previsões vêm do modelo "
                                     "ajustado às tabelas; os disparos simulados da demonstração não entram aqui.")
            return
        rate = "sem dados" if st["taxa_acerto"] is None else f"{st['taxa_acerto']:.0%}"
        err = "sem dados" if st["erro_abs_medio"] is None else f"{st['erro_abs_medio']:.2f}"
        n_corr = sum(v["n"] for k, v in st["modelos"].items() if k.endswith("|*"))
        text = (f"No jogo real, neste cenário: {st['disparos']} disparos, {st['avaliados']} com resultado. "
                f"Acerto observado: {rate}. Erro médio de onde caiu: {err}. Correções aprendidas com {n_corr} "
                "disparo(s).")
        if st["outros_cenarios"]:
            text += (f" {st['outros_cenarios']} disparo(s) de outro cenário (outro modo de força, outro cliente ou "
                     "versão anterior) ficam guardados, mas não corrigem a mira atual.")
        self.lbl_stats.configure(text=text)

    def _selected_shot(self):
        sel = self.tree_shots.selection()
        if not sel:
            self.notice("Escolha um disparo na tabela.", True)
            return None
        return int(sel[0])

    def mark_shot(self, hit: bool):
        sid = self._selected_shot()
        if sid is None:
            return
        rec = self.svc.store.get(sid)
        self.svc.calibrator.set_result(sid, rec.impact_x if rec else None, hit)
        self.refresh_shots()
        self.notice(f"Disparo #{sid} marcado como {'acerto' if hit else 'erro'}.")

    def mark_impact(self):
        sid = self._selected_shot()
        if sid is None:
            return
        try:
            impact = float(self.impact_entry.get().replace(",", "."))
        except ValueError:
            self.notice("Digite a distância em que o tiro caiu, por exemplo 9,8.", True)
            return
        rec = self.svc.store.get(sid)
        half = float(self.svc.config.get("aim.target_width", 0.35)) / 2 + 0.25
        hit = None if rec is None else abs(impact - rec.distance) <= half
        self.svc.calibrator.set_result(sid, impact, hit)
        self.refresh_shots()
        self.notice(f"Disparo #{sid}: caiu em {impact:.2f}.")

    def refit(self):
        res = self.svc.calibrator.refit_params()
        if res is None:
            self.notice(f"Para reajustar, registre onde caíram pelo menos {self.svc.calibrator.MIN_SHOTS_REFIT} "
                        "disparos.", True)
            return
        params, info = res
        if messagebox.askyesno("Reajustar o modelo", f"Erro antes: {info['perda_antes']:.3f}\n"
                               f"Erro depois: {info['perda_depois']:.3f}\n\nUsar o modelo reajustado?"):
            self.svc.apply_params(params, info)
            self.refresh_shots()
            self.notice("Modelo reajustado com os seus disparos.")

    # ---------------------------------------------------------- configurações
    def _save_config_file(self) -> bool:
        try:
            self.svc.config.save()
            return True
        except OSError as exc:
            self.notice(f"Não foi possível gravar a configuração ({exc}). Feche outros programas que usem a pasta "
                        "de dados e tente de novo.", True)
            return False

    def save_config(self):
        c = self.svc.config
        new = {}
        labels = {k: lbl for _, fields in self.CFG_GROUPS for k, lbl, _t in fields}
        for key, var in self.cfg_vars.items():
            if isinstance(var, tk.BooleanVar):
                new[key] = bool(var.get())
                continue
            raw = var.get().strip()
            typ = self.cfg_types[key]
            if isinstance(typ, tuple):
                new[key] = next((k for k, v in self.POWER_LABELS.items() if v == raw), typ[0])
                continue
            if raw == "":
                if key in OPTIONAL_FIELDS:
                    new[key] = None
                    continue
                self.notice(f"Preencha '{labels.get(key, key)}'. Nada foi salvo.", True)
                return
            try:
                new[key] = raw if typ is str else typ(raw.replace(",", "."))
            except ValueError:
                self.notice(f"Valor inválido em '{labels.get(key, key)}': {raw}. Nada foi salvo.", True)
                return
        problems = c.validate_values(new)
        if problems:
            self.notice("Nada foi salvo: " + "; ".join(problems), True)
            return
        for key, value in new.items():
            c.set(key, value)
        c.set("automation.allowed_paid_templates", [s.strip() for s in self.paid_var.get().split(",") if s.strip()])
        if self._save_config_file():
            self.notice(f"Configurações salvas às {time.strftime('%H:%M')}.")

    # ================================================================== laço
    def _tick(self):
        if self._closing:
            return
        try:
            self._drain_events()
            self._drain_locate()
            self._ticks = getattr(self, "_ticks", 0) + 1
            # não procura durante o Iniciar em thread: a troca de janela fecharia a captura do runner novo
            if self._ticks % 15 == 0 and not self._starting and not (self.svc.runner and self.svc.runner.alive):
                self.refresh_windows()  # a cada ~3 s: o jogo pode abrir/fechar pelo launcher
            self._drain_logs()
            self._drain_diag()
            self._update_status()
            self._update_buttons()
            if self.live_diag.get() and self.nb.select() == str(self.tab_diag):
                self.diag_once()
            if self.assist_on.get() and not self.svc.assist_alive:
                self.assist_on.set(False)
                self.notice("A mira assistida parou (veja o Registro técnico).", True)
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
            tag = e.kind if e.kind in T.RESULT_COLORS else ""
            kind = f"{HIST_ICONS[e.kind]} {e.kind}" if e.kind in HIST_ICONS else e.kind
            self.tree_hist.insert("", 0, values=(time.strftime("%H:%M:%S", time.localtime(e.when)), kind,
                                                 humanize(e.message)), tags=(tag,))
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
                                                   if snap else "Sem imagem: escolha a janela do jogo.")
        self.txt_diag.insert("1.0", text)

    def ui_snapshot(self) -> UiSnapshot:
        r, d = self.svc.runner, self.selected_activity()
        eng = self.svc.engine
        obs = eng.last_observation if eng else None
        alive = bool(r and r.alive)
        return UiSnapshot(
            has_window=self.svc.window is not None, demo=self.simulated.get() or self.svc.simulated,
            activity_name=(r.d.name if alive else (d.name if d else None)),
            activity_auto=(d.auto_allowed if d else True),
            status=self.svc.status, alive=alive, reason=(r.reason if r else ""),
            screen=(r.current_state if r else "desconhecido"),
            emergency=self.svc.kill.triggered, emergency_reason=self.svc.kill.reason,
            my_turn=(obs.my_turn if obs else None),
            unknown_screen=bool(alive and r.unknown_screen),
            completed=(r.counters.completed if r else 0), runs=(r.limits.runs if r else self._runs()),
            window_state=self.window_state)

    def _update_status(self):
        b = describe(self.ui_snapshot())
        self.banner.set(b.kind, b.title, b.detail)
        r = self.svc.runner
        if r:
            c = r.counters.as_dict()
            for k, w in self.counters.items():
                w.set(c.get(k, 0))
            total = r.limits.runs
            self.lbl_progress.configure(text=f"{c['concluidas']} de {total} concluída(s)" if total else
                                        f"{c['concluidas']} concluída(s), repetição contínua")
            self.progress.configure(value=100 * c["concluidas"] / total if total else 0)
        eng = self.svc.engine
        active = bool(r and r.alive) or self.svc.assist_alive
        if eng is None or not active:
            # nada rodando: não mostrar números velhos como se fossem atuais
            for ro in (self.ro_angle, self.ro_force, self.ro_wind):
                ro.set(None)
            self.lbl_target.configure(text="Os valores aparecem durante o combate.")
            return
        obs, rec = eng.last_observation, eng.last_recommendation
        if rec is not None and rec.best:
            bst = rec.best
            self.ro_angle.set(f"{bst.angle}")
            self.ro_force.set(f"{bst.force:.1f}".replace(".", ","))
            target = ""
            if obs is not None and obs.distance is not None:
                target = f"Alvo a {obs.distance:.1f} de distância, altura {obs.dy:+.1f}".replace(".", ",")
                if not obs.target_visible:
                    target += " (invisível: posição estimada)"
                target += ". "
            stage = f"Etapa {obs.stage}. " if obs is not None and obs.stage else ""
            self.lbl_target.configure(text=f"{stage}{target}{method_label(bst.method)}, chance estimada "
                                           f"{bst.hit_probability:.0%}.")
        elif obs is not None and (obs.wait_reason or obs.pause_reason):
            stage = f"Etapa {obs.stage}: " if obs.stage else ""
            self.lbl_target.configure(text=f"{stage}{obs.pause_reason or obs.wait_reason}.")
        if obs is not None:
            self.ro_wind.set(None if obs.wind is None else f"{obs.wind:+.1f}".replace(".", ","))

    def on_close(self):
        if self.svc.runner and self.svc.runner.alive and not headless():
            if not messagebox.askyesno("Sair", "Uma rotina está em execução. Parar e sair?"):
                return
        self._closing = True
        try:
            self.svc.close()
        finally:
            self.root.destroy()


# ============================================================ inicialização
def winapi_is_windows() -> bool:
    from .. import winapi
    return winapi.IS_WINDOWS


def _smoke(app: MainWindow, seconds: float, report: dict, done):
    """Exercita a interface sem o jogo: demonstração, iniciar, pausar, retomar, parar e emergência."""
    root = app.root
    steps = []

    def at(delay, fn):
        steps.append((delay, fn))

    def check(name, cond):
        report.setdefault("checks", {})[name] = bool(cond)

    six = ["formigueiro_facil", "formigueiro_normal", "galinheiro_facil", "galinheiro_normal", "galinheiro_dificil",
           "olimpiadas_bugou_normal"]

    def listed():
        return list(app.tree_act.get_children("sec_instancia"))

    def s_demo():
        # sem o jogo e sem o modo demonstração: as seis instâncias pré-cadastradas já aparecem
        check("seis_instancias_sem_jogo", listed()[:6] == six and app.svc.window is None)
        names = [app.tree_act.item(k, "text") for k in listed()]
        check("castelo_fora_da_lista_principal", not any("Castelo" in n for n in names))
        check("secao_partidas", app.tree_act.exists("sec_partida"))
        app.simulated.set(True)
        app.refresh_activities()
        app.tree_act.selection_set("formigueiro_normal")
        root.update_idletasks()
        app.run_mode.set("cont")
        app._update_status()
        check("demonstracao_listada", app.selected_activity() is not None and listed()[:6] == six)
        check("demonstracao_com_estrategia", (app.selected_activity() or demo_activity("instancia")).strategy
              is not None)
        check("faixa_pronto", app.banner.kind == "ready")

    def s_start():
        app.btn_start.invoke()
        check("iniciou", app.svc.runner is not None and app.svc.runner.alive)

    def s_pause():
        check("executando", app.svc.status == RunStatus.RUNNING)
        app._update_status()
        check("faixa_executando", app.banner.kind in ("running", "combat", "warning"))
        app.btn_pause.invoke()
        check("pausou", app.svc.status == RunStatus.PAUSED)

    def s_paused_still():
        r = app.svc.runner
        report["leituras_pausado_a"] = getattr(r.reader, "reads", None)
        app._update_status()
        check("faixa_pausado", app.banner.kind == "paused")
        check("botao_vira_retomar", str(app.btn_pause.cget("text")).startswith("Retomar"))

    def s_resume():
        r = app.svc.runner
        check("pausa_congela_leituras", getattr(r.reader, "reads", 0) == report.get("leituras_pausado_a"))
        app.btn_pause.invoke()
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

    def s_detect_open():
        report["estado_antes_detectar"] = root.state()
        app.open_detect()
        root.update()
        report["estado_durante_detectar"] = root.state()
        if winapi_is_windows():  # sem gerenciador de janelas (Xvfb) minimizar não é verificável
            check("detectar_minimiza_principal", root.state() == "iconic")
        check("detectar_janela_aberta", app.detect_dialog is not None and app.detect_dialog.winfo_exists())

    def s_detect_close():
        app.detect_dialog.close()
        root.update()
        report["estado_depois_detectar"] = root.state()
        check("detectar_restaura_principal", root.state() == "normal" and app.detect_dialog is None)
        check("estado_preservado", app.simulated.get() and app.selected_activity() is not None)

    def s_kinds():
        app.tree_act.selection_set(DEMO_KEY + "partida")
        root.update_idletasks()
        d = app.selected_activity()
        check("partida_demo_listada", d is not None and d.kind == "partida")
        check("iniciar_habilitado_com_atividade", app.btn_start.instate(["!disabled"]))
        app.tree_act.selection_set("olimpiadas_bugou_normal")
        root.update_idletasks()
        check("instancia_escolhida_de_novo", (app.selected_activity() or d).key == "olimpiadas_bugou_normal")
        # sem o modo demonstração e sem o jogo: Iniciar fica desativado (no jogo real precisa da janela)
        app.simulated.set(False)
        app.refresh_activities()
        check("escolha_mantida", (app.selected_activity() or d).key == "olimpiadas_bugou_normal")
        check("iniciar_bloqueado_sem_jogo", app.btn_start.instate(["disabled"]))
        check("pendencias_listadas", bool(app.svc.readiness(app.selected_activity())))
        app.simulated.set(True)
        app.refresh_activities()

    def s_emergency():
        app.run_mode.set("cont")
        app.btn_start.invoke()
        root.after(400, lambda: (app.svc.emergency_stop(), root.after(1200, s_emergency_check)))

    def s_emergency_check():
        check("emergencia_para", not (app.svc.runner and app.svc.runner.alive))
        app._update_status()
        check("faixa_emergencia", app.banner.kind == "emergency")
        done()

    span = max(6.0, seconds)
    at(0.3, s_demo)
    at(0.6, s_start)
    at(span * 0.30, s_pause)
    at(span * 0.38, s_paused_still)
    at(span * 0.46, s_resume)
    at(span * 0.55, s_tabs)
    at(span * 0.65, s_stop)
    at(span * 0.76, s_stopped)
    at(span * 0.78, s_detect_open)    # com a rotina já parada (Detectar jogo é recusado durante uma rotina)
    at(span * 0.83, s_detect_close)
    at(span * 0.86, s_kinds)
    at(span * 0.89, s_emergency)

    lags = []

    t0 = time.monotonic()
    beat = [t0]
    tk_thread = threading.get_ident()

    def watchdog():
        """Se a interface parar de responder por mais de 1 s, guarda onde cada thread estava (diagnóstico)."""
        import sys
        import traceback
        while not report.get("resultado") and root_alive[0]:
            time.sleep(0.2)
            if time.monotonic() - beat[0] > 1.0 and "pilhas_no_atraso" not in report:
                frames = sys._current_frames()
                names = {t.ident: t.name for t in threading.enumerate()}
                report["pilhas_no_atraso"] = {
                    ("tk" if ident == tk_thread else names.get(ident, str(ident))):
                        [line.strip() for line in traceback.format_stack(f)[-8:]]
                    for ident, f in frames.items() if ident != threading.get_ident()}
                report["pilhas_no_atraso_em_s"] = round(time.monotonic() - t0, 2)
                report["pilhas_no_atraso_depois_de"] = report.get("ultimo_passo", "")
    root_alive = [True]
    root.bind("<Destroy>", lambda e: root_alive.__setitem__(0, False) if e.widget is root else None, add="+")
    threading.Thread(target=watchdog, daemon=True, name="vigia-da-interface").start()

    def probe(last=[time.monotonic()]):
        now = time.monotonic()
        beat[0] = now
        lag = now - last[0] - 0.1
        if not lags or lag > max(lags):
            # onde a interface travou: segundos desde o início e o último passo executado
            report["atraso_max_em_s"] = round(now - t0, 2)
            report["atraso_max_depois_de"] = report.get("ultimo_passo", "")
        lags.append(lag)
        last[0] = now
        report["atraso_max_ms"] = round(max(lags) * 1000)
        root.after(100, probe)
    root.after(100, probe)
    for delay, fn in steps:
        root.after(int(delay * 1000), lambda fn=fn: (report.__setitem__("ultimo_passo", fn.__name__), fn()))


def _install_error_hooks(root: tk.Tk):
    """No .exe sem console, erros de botões e de threads iriam para lugar nenhum."""
    def on_tk_error(exc_type, exc, tb):
        log.error("erro na interface", exc_info=(exc_type, exc, tb))
        if not headless():
            try:
                messagebox.showerror("JonFlow", f"Ocorreu um erro: {exc}\n\nOs detalhes estão no Registro "
                                     "técnico e no arquivo dados\\logs\\ddbot.log.")
            except tk.TclError:
                pass
    root.report_callback_exception = on_tk_error


def run_gui(home: Path | None = None, smoke_seconds: float = 0.0, screenshots: Path | None = None) -> int:
    report: dict = {}
    smoke_out = os.environ.get("DDBOT_SMOKE_OUT")
    automated = smoke_seconds > 0 or screenshots is not None
    if automated:
        os.environ.setdefault("DDBOT_HEADLESS", "1")
    try:
        svc = BotService(home, start_hotkey=not automated)
    except Exception as exc:
        log.exception("falha ao iniciar")
        if smoke_out:
            Path(smoke_out).write_text(json.dumps({"erro": str(exc)}), encoding="utf-8")
        if not automated:
            try:
                r = tk.Tk()
                r.withdraw()
                messagebox.showerror("JonFlow", f"O programa não conseguiu iniciar: {exc}\n\n"
                                     "Verifique se a pasta do programa permite gravar arquivos.")
                r.destroy()
            except Exception:
                pass
        return 1
    root = tk.Tk()
    _install_error_hooks(root)
    try:
        app = MainWindow(root, svc)
    except Exception as exc:
        log.exception("falha ao montar a interface")
        if smoke_out:
            Path(smoke_out).write_text(json.dumps({"erro": f"interface: {exc}"}), encoding="utf-8")
        if not automated:
            messagebox.showerror("JonFlow", f"Erro ao montar a interface: {exc}")
        svc.close()
        root.destroy()
        return 1
    finished: list = []

    def finish():
        if finished:
            return
        finished.append(True)
        if smoke_seconds > 0:
            checks = report.get("checks", {})
            report["atraso_ok"] = report.get("atraso_max_ms", 0) < 1500
            report["resultado"] = "OK" if checks and all(checks.values()) and report["atraso_ok"] else "FALHOU"
            if smoke_out:
                Path(smoke_out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        app._closing = True
        svc.close()
        root.destroy()

    if screenshots is not None:
        from .screenshots import run_screenshots
        run_screenshots(app, Path(screenshots), report, finish)
    elif smoke_seconds > 0:
        _smoke(app, smoke_seconds, report, finish)
        root.after(int((max(6.0, smoke_seconds) + 20) * 1000), lambda: (report.setdefault("checks", {}).update(
            {"terminou_no_prazo": False}), finish()))
    root.mainloop()
    if automated:
        return 0 if report.get("resultado") == "OK" else 1
    return 0
