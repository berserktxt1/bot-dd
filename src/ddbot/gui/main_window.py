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
from ..vision.menu import detect_option_tiles, find_known_options
from ..vision.perception import REGION_KEYS, STATE_LABELS, STATES, draw_overlay
from ..vision.regions import crop, px_to_frac
from . import theme as T
from .states import UiSnapshot, advice, describe, humanize, method_label, pick_options
from .widgets import Counter, ImageCanvas, Panel, Readout, ScrollFrame, StatusBanner

log = logging.getLogger(__name__)

DEMO_KEY = "__demonstracao__"
KIND_LABELS = {"instancia": "Instâncias", "partida": "Partidas automáticas"}
HIST_ICONS = {"resultado": "✓", "aviso": "!", "erro": "✕", "fim": "■", "combate": "◎"}
OPTIONAL_FIELDS = {"automation.keys.pass_turn"}


def demo_activity(kind: str) -> ActivityDef:
    name = "Instância de demonstração" if kind == "instancia" else "Partida de demonstração"
    d = activity_from_option(f"{kind}_teste", name, kind, "pve")
    d.key = DEMO_KEY + kind
    d.description = "Simulação interna para conhecer o programa. Nada é enviado ao jogo."
    return d


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
        self._kind_keys: list[str] = []
        self.live_diag = tk.BooleanVar(value=False)
        self.simulated = tk.BooleanVar(value=False)
        self._diag_queue: "queue.Queue[tuple]" = queue.Queue(maxsize=2)
        self._diag_busy = False
        self._tiles: list = []
        self._closing = False
        self._notice_after = None
        root.title(f"DDClássico Bot {__version__}")
        from .. import winapi
        area = winapi.work_area()
        ax, ay, aw, ah = area or (0, 0, root.winfo_screenwidth(), root.winfo_screenheight() - px(48))
        # cabe na área de trabalho (sem a barra de tarefas), descontando borda e barra de título
        w, h = min(px(1220), aw - px(16)), min(px(800), ah - px(40))
        root.geometry(f"{w}x{h}+{ax + max(0, (aw - w) // 2)}+{ay + max(0, (ah - h - px(32)) // 2)}")
        root.minsize(min(px(960), aw), min(px(600), ah - px(40)))
        self._build_top()
        self.nb = ttk.Notebook(root)
        self._build_notice()
        self.nb.pack(fill="both", expand=True, padx=px(12), pady=(0, px(4)))
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
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(200, self._tick)

    # ================================================================ layout
    def _build_top(self):
        px = self.th.px
        top = ttk.Frame(self.root, padding=(px(16), px(12), px(16), px(8)))
        top.pack(fill="x")
        ttk.Label(top, text="DDClássico Bot", style="Section.TLabel").pack(side="left", padx=(0, px(24)))
        ttk.Label(top, text="Janela do jogo").pack(side="left")
        self.cb_window = ttk.Combobox(top, state="readonly", width=40)
        self.cb_window.pack(side="left", padx=(px(8), px(6)))
        self.cb_window.bind("<<ComboboxSelected>>", lambda e: self.select_window())
        ttk.Button(top, text="Atualizar", command=self.refresh_windows).pack(side="left")
        self.all_windows = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Listar todas as janelas", variable=self.all_windows,
                        command=self.refresh_windows).pack(side="left", padx=(px(10), 0))
        ttk.Checkbutton(top, text="Modo demonstração", variable=self.simulated,
                        command=self._toggle_demo).pack(side="right")
        self.lbl_window = ttk.Label(top, text="", style="Muted.TLabel")
        self.lbl_window.pack(side="left", padx=(px(16), 0))

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
        t.columnconfigure(0, weight=5, uniform="home")
        t.columnconfigure(1, weight=4, uniform="home")
        t.rowconfigure(2, weight=1)
        self.banner = StatusBanner(t, self.th)
        self.banner.grid(row=0, column=0, columnspan=2, sticky="we")

        play = Panel(t, self.th, "O que jogar", pad="m")
        play.grid(row=1, column=0, sticky="nsew", pady=(gap, 0), padx=(0, gap))
        b = play.body
        seg = ttk.Frame(b, style="Surface.TFrame")
        seg.grid(row=0, column=0, sticky="w")
        self.area = tk.StringVar(value="instancia")
        for kind in ("instancia", "partida"):
            ttk.Radiobutton(seg, text=KIND_LABELS[kind], value=kind, variable=self.area, style="Segment.TRadiobutton",
                            command=self._fill_activity_list).pack(side="left", padx=(0, px(4)))
        self.cb_act = ttk.Combobox(b, state="readonly", font=self.th.fonts["body"])
        self.cb_act.grid(row=1, column=0, sticky="we", pady=(px(12), px(4)))
        self.cb_act.bind("<<ComboboxSelected>>", lambda e: self._describe())
        self.lbl_desc = ttk.Label(b, text="", style="SurfaceMuted.TLabel", justify="left", wraplength=px(480))
        self.lbl_desc.grid(row=2, column=0, sticky="we")
        self.btn_goto_calib = ttk.Button(b, text="Capturar opções do jogo", command=self._goto_options)
        self.btn_goto_calib.grid(row=3, column=0, sticky="w", pady=(px(6), 0))

        runs = ttk.Frame(b, style="Surface.TFrame")
        runs.grid(row=5, column=0, sticky="w", pady=(px(14), 0))
        self.run_mode = tk.StringVar(value="uma")
        self.run_count = tk.IntVar(value=5)
        ttk.Label(runs, text="Quantas vezes", style="Strong.TLabel").pack(side="left", padx=(0, px(14)))
        ttk.Radiobutton(runs, text="Uma vez", value="uma", variable=self.run_mode,
                        style="Surface.TRadiobutton").pack(side="left")
        ttk.Radiobutton(runs, text="Repetir", value="qtd", variable=self.run_mode,
                        style="Surface.TRadiobutton").pack(side="left", padx=(px(16), px(4)))
        self.sp_runs = ttk.Spinbox(runs, from_=1, to=999, textvariable=self.run_count, width=5,
                                   command=lambda: self.run_mode.set("qtd"))
        self.sp_runs.pack(side="left")
        ttk.Label(runs, text="vezes", style="Surface.TLabel").pack(side="left", padx=(px(4), 0))
        ttk.Radiobutton(runs, text="Até eu parar", value="cont", variable=self.run_mode,
                        style="Surface.TRadiobutton").pack(side="left", padx=(px(16), 0))

        actions = ttk.Frame(b, style="Surface.TFrame")
        actions.grid(row=6, column=0, sticky="w", pady=(px(16), 0))
        self.btn_start = ttk.Button(actions, text="Iniciar  (F5)", style="Primary.TButton", command=self.start)
        self.btn_start.pack(side="left")
        self.btn_pause = ttk.Button(actions, text="Pausar  (F6)", command=self.toggle_pause)
        self.btn_pause.pack(side="left", padx=(px(10), 0))
        self.btn_stop = ttk.Button(actions, text="Parar  (F8)", style="Danger.TButton", command=self.stop)
        self.btn_stop.pack(side="left", padx=(px(10), 0))

        right = ttk.Frame(t)
        right.grid(row=1, column=1, sticky="nsew", pady=(gap, 0))
        right.columnconfigure(0, weight=1)
        prog = Panel(right, self.th, "Progresso", pad="m")
        prog.grid(row=0, column=0, sticky="nsew")
        pb = prog.body
        self.lbl_progress = ttk.Label(pb, text="Nada em execução", style="Strong.TLabel")
        self.lbl_progress.grid(row=0, column=0, columnspan=4, sticky="w")
        self.progress = ttk.Progressbar(pb, mode="determinate")
        self.progress.grid(row=1, column=0, columnspan=4, sticky="we", pady=(px(6), px(12)))
        self.counters = {}
        for i, (k, label) in enumerate((("concluidas", "concluídas"), ("vitorias", "vitórias"),
                                        ("derrotas", "derrotas"), ("batalhas", "batalhas"))):
            c = Counter(pb, self.th, label)
            c.grid(row=2, column=i, sticky="w", padx=(0, px(14)))
            self.counters[k] = c
            pb.columnconfigure(i, weight=1)

        aim = Panel(right, self.th, "Mira", pad="m")
        aim.grid(row=1, column=0, sticky="nsew", pady=(gap, 0))
        ab = aim.body
        self.ro_angle = Readout(ab, self.th, "ângulo", "°")
        self.ro_force = Readout(ab, self.th, "força")
        self.ro_wind = Readout(ab, self.th, "vento")
        for i, ro in enumerate((self.ro_angle, self.ro_force, self.ro_wind)):
            ro.grid(row=0, column=i, sticky="w", padx=(0, px(32)))
            ab.columnconfigure(i, weight=0)
        ab.columnconfigure(3, weight=1)  # sobra de espaço à direita: os três números ficam juntos
        self.lbl_target = ttk.Label(ab, text="Os valores aparecem durante o combate.", style="SurfaceMuted.TLabel",
                                    justify="left", wraplength=px(380))
        self.lbl_target.grid(row=1, column=0, columnspan=4, sticky="w", pady=(px(8), 0))

        hist = Panel(t, self.th, "Histórico", pad="m")
        hist.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(gap, 0))
        t.rowconfigure(2, weight=1, minsize=px(150))  # sempre algumas linhas visíveis
        hb = hist.body
        hb.rowconfigure(0, weight=1)
        self.tree_hist = ttk.Treeview(hb, columns=("hora", "tipo", "msg"), show="headings", height=4)
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
        ttk.Button(s, text="Capturar tela do jogo", style="Primary.TButton", command=self.calib_capture).grid(
            row=0, column=0, sticky="we")
        self.lbl_sel = ttk.Label(s, text="Nenhuma seleção.", style="SurfaceMuted.TLabel")
        self.lbl_sel.grid(row=1, column=0, sticky="w", pady=(px(6), px(10)))
        sub = ttk.Notebook(s, style="Sub.TNotebook")
        sub.grid(row=2, column=0, sticky="we")
        self.calib_nb = sub

        def page(title, hint):
            f = ttk.Frame(sub, style="Surface.TFrame", padding=px(10))
            f.columnconfigure(0, weight=1)
            sub.add(f, text=title)
            ttk.Label(f, text=hint, style="SurfaceMuted.TLabel", wraplength=px(320), justify="left").grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(0, px(8)))
            return f

        f = page("Regiões", "Selecione onde ficam o ângulo, o vento, a barra de força, o indicador de turno e a "
                 "área de jogo.")
        self.cb_region = ttk.Combobox(f, state="readonly", values=list(REGION_KEYS.values()))
        self.cb_region.current(0)
        self.cb_region.grid(row=1, column=0, sticky="we")
        ttk.Button(f, text="Salvar região", command=self.save_region).grid(row=2, column=0, sticky="we",
                                                                           pady=(px(6), 0))

        f = page("Modelos", "Selecione um pedaço que identifique a tela ou o botão e salve com o nome certo. "
                 "Capture 2 ou 3 amostras de cada um.")
        self._tpl_keys = [f"estado_{st}" for st in STATES] + list(COMMON_TEMPLATES)
        tpl_labels = [f"Tela: {STATE_LABELS.get(st, st)}" for st in STATES] + list(COMMON_TEMPLATES.values())
        self.cb_tpl = ttk.Combobox(f, state="readonly", values=tpl_labels)
        self.cb_tpl.current(0)
        self.cb_tpl.grid(row=1, column=0, sticky="we")
        ttk.Button(f, text="Salvar modelo", command=self.save_template).grid(row=2, column=0, sticky="we",
                                                                             pady=(px(6), 0))
        self.lbl_tpl = ttk.Label(f, text="", style="SurfaceMuted.TLabel", wraplength=px(300))
        self.lbl_tpl.grid(row=3, column=0, sticky="w", pady=(px(6), 0))

        f = page("Números", "Com a região já salva, digite o número que aparece no jogo e clique em Aprender. "
                 "Repita até cobrir os dígitos de 0 a 9.")
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

        f = page("Menu", "Abra no jogo o menu de instâncias ou de partidas, capture e clique em Detectar. "
                 "Cada opção que você nomear vira uma atividade no Início.")
        ttk.Button(f, text="Detectar opções", command=self.detect_options).grid(row=1, column=0, sticky="we")
        self.lst_tiles = tk.Listbox(f, height=5, exportselection=False, relief="flat", highlightthickness=1,
                                    highlightbackground=T.LINE, font=self.th.fonts["body"],
                                    selectbackground=T.PRIMARY, activestyle="none")
        self.lst_tiles.grid(row=2, column=0, sticky="we", pady=(px(6), px(6)))
        self.lst_tiles.bind("<<ListboxSelect>>", self._on_tile_select)
        g = ttk.Frame(f, style="Surface.TFrame")
        g.grid(row=3, column=0, sticky="we")
        g.columnconfigure(1, weight=1)
        ttk.Label(g, text="Nome", style="Surface.TLabel").grid(row=0, column=0, sticky="w", pady=px(2))
        self.opt_name = ttk.Entry(g)
        self.opt_name.grid(row=0, column=1, sticky="we", padx=(px(8), 0))
        ttk.Label(g, text="Tipo", style="Surface.TLabel").grid(row=1, column=0, sticky="w", pady=px(2))
        self.opt_kind = ttk.Combobox(g, state="readonly", values=[KIND_LABELS["instancia"], KIND_LABELS["partida"]])
        self.opt_kind.current(0)
        self.opt_kind.grid(row=1, column=1, sticky="we", padx=(px(8), 0))
        ttk.Label(g, text="Categoria", style="Surface.TLabel").grid(row=2, column=0, sticky="w", pady=px(2))
        self._cat_keys = list(CATEGORIES)
        self.opt_cat = ttk.Combobox(g, state="readonly", values=list(CATEGORIES.values()))
        self.opt_cat.current(0)
        self.opt_cat.grid(row=2, column=1, sticky="we", padx=(px(8), 0))
        ttk.Button(f, text="Criar atividade", command=self.create_option).grid(row=4, column=0, sticky="we",
                                                                                pady=(px(8), 0))
        ttk.Button(f, text="Ver opções conhecidas nesta captura", command=self.check_visible_options).grid(
            row=5, column=0, sticky="we", pady=(px(4), 0))

        ttk.Separator(s).grid(row=3, column=0, sticky="we", pady=px(14))
        ttk.Label(s, text="Conferir os controles", style="SurfaceSection.TLabel").grid(row=4, column=0, sticky="w")
        ttk.Label(s, text="No seu turno, aperta ↑ e depois ↓ e confere se o ângulo mudou. Não atira.",
                  style="SurfaceMuted.TLabel", wraplength=px(300), justify="left").grid(row=5, column=0, sticky="w")
        ttk.Button(s, text="Testar teclas do ângulo", command=self.test_controls).grid(row=6, column=0, sticky="we",
                                                                                       pady=(px(6), 0))
        ttk.Separator(s).grid(row=7, column=0, sticky="we", pady=px(14))
        ttk.Button(s, text="Excluir a atividade escolhida no Início", style="Danger.TButton",
                   command=self.delete_activity).grid(row=8, column=0, sticky="we")

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
        self.tree_aim = ttk.Treeview(opts.body, columns=("met", "ang", "for", "p", "base"), show="headings", height=7)
        for col, text, w in (("met", "Método", 120), ("ang", "Ângulo", 64), ("for", "Força", 64),
                             ("p", "Chance", 70), ("base", "De onde vem", 400)):
            self.tree_aim.heading(col, text=text, anchor="w")
            self.tree_aim.column(col, width=px(w), stretch=col == "base", anchor="w")
        self.tree_aim.grid(row=0, column=0, sticky="nsew")
        shots = Panel(t, self.th, "Disparos registrados",
                      "Marque o resultado dos disparos para a mira aprender com o seu jogo.")
        shots.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(px(12), 0))
        sb = shots.body
        sb.rowconfigure(0, weight=1)
        self.tree_shots = ttk.Treeview(sb, columns=("id", "ang", "for", "vento", "dist", "imp", "res", "met", "modo"),
                                       show="headings", height=7)
        for col, text, w in (("id", "#", 44), ("ang", "Ângulo", 64), ("for", "Força", 64), ("vento", "Vento", 64),
                             ("dist", "Distância", 80), ("imp", "Caiu em", 76), ("res", "Resultado", 100),
                             ("met", "Método", 80), ("modo", "Modo", 96)):
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
        try:
            self.windows = self.svc.find_windows(self.all_windows.get())
        except Exception as exc:
            self.windows = []
            self.notice(f"Não foi possível listar as janelas: {exc}", True)
        self.cb_window["values"] = [f"{w.title}  ({w.width}×{w.height})" for w in self.windows]
        if self.windows and self.svc.window is None:
            self.cb_window.current(0)
            self.select_window()
        elif not self.windows:
            self.cb_window.set("")
            self.lbl_window.configure(text="Jogo não encontrado")

    def select_window(self):
        i = self.cb_window.current()
        if 0 <= i < len(self.windows):
            self.svc.select_window(self.windows[i])
            w = self.windows[i]
            self.lbl_window.configure(text=f"Conectado, {w.width}×{w.height}")

    def _toggle_demo(self):
        self.refresh_activities()
        self.notice("Modo demonstração ligado: nada é enviado ao jogo." if self.simulated.get()
                    else "Modo demonstração desligado.")

    def refresh_activities(self):
        defs, errors = self.svc.activities()
        for e in errors:
            self.notice(f"Arquivo de atividade inválido: {e}", True)
        if self.simulated.get():
            defs = [demo_activity("instancia"), demo_activity("partida")] + defs
        self.activities = {d.key: d for d in defs}
        self._fill_activity_list()

    def _fill_activity_list(self):
        kind = self.area.get()
        items = [d for d in self.activities.values() if d.kind == kind]
        self._kind_keys = [d.key for d in items]
        self.cb_act["values"] = [self._label(d) for d in items]
        if items:
            self.cb_act.current(0)
            self.btn_goto_calib.grid_remove()
        else:
            self.cb_act.set("")
            self.btn_goto_calib.grid()
        self._describe()

    def _label(self, d: ActivityDef):
        if d.key.startswith(DEMO_KEY):
            return f"{d.name} (simulação)"
        tag = "" if d.validated else " (ainda não validada no jogo)"
        return f"{d.name}, {CATEGORIES.get(d.category, d.category)}{tag}"

    def selected_activity(self) -> ActivityDef | None:
        i = self.cb_act.current()
        return self.activities.get(self._kind_keys[i]) if 0 <= i < len(self._kind_keys) else None

    def _describe(self):
        d = self.selected_activity()
        if d is None:
            what = "instância" if self.area.get() == "instancia" else "partida"
            self.lbl_desc.configure(text=f"Nenhuma {what} capturada ainda. Abra o menu no jogo e capture as opções "
                                    "para escolher aqui.")
            return
        auto = "O bot joga sozinho." if d.auto_allowed else "Envolve outros jogadores: o bot não joga sozinho."
        self.lbl_desc.configure(text=f"{d.description} {auto}")

    def _goto_options(self):
        self.nb.select(self.tab_calib)
        self.calib_nb.select(3)

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
            self.notice("Escolha a janela do jogo no topo antes de iniciar.", True)
            return
        self.btn_start.state(["disabled"])
        ok, why = self.svc.start(d, self._runs(), simulated=simulated)
        if not ok:
            tip = advice(why)
            self.notice(f"Não foi possível iniciar: {why}. {tip}".strip(), True)
            if not headless():
                messagebox.showwarning("Não foi possível iniciar", f"{why}\n\n{tip}".strip())
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
        self.btn_start.state(["disabled"] if running else ["!disabled"])
        self.btn_pause.state(["!disabled"] if running else ["disabled"])
        paused = st == RunStatus.PAUSED
        self.btn_pause.configure(text="Retomar  (F6)" if paused else "Pausar  (F6)",
                                 style="Primary.TButton" if paused else "TButton")
        self.btn_stop.state(["!disabled"] if running else ["disabled"])

    # ------------------------------------------------------------- calibração
    def calib_capture(self):
        frame = self.svc.grab()
        if frame is None:
            self.notice("Não foi possível capturar: escolha a janela do jogo e deixe-a visível (não minimizada).",
                        True)
            return
        self.calib_canvas.show(frame)
        self._tiles = []
        self.lst_tiles.delete(0, "end")
        self.notice("Tela capturada. Arraste sobre a imagem para selecionar.")

    def _on_calib_select(self, rect):
        self.lbl_sel.configure(text=f"Seleção: {rect[2]}×{rect[3]} px em ({rect[0]}, {rect[1]})")

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

    def create_option(self):
        img = self.calib_canvas.selection_image()
        name = self.opt_name.get().strip()
        if img is None or not name:
            self.notice("Selecione uma opção (na lista ou arrastando) e digite um nome.", True)
            return
        kind = "instancia" if self.opt_kind.current() == 0 else "partida"
        category = self._cat_keys[max(0, self.opt_cat.current())]
        try:
            d = self.svc.create_activity_from_image(img, name, kind, category)
        except ValueError as exc:
            self.notice(str(exc), True)
            return
        self.area.set(kind)
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
        text = "\n".join(f"{k} (semelhança {s:.2f})" for k, s in found) or \
            "Nenhuma opção conhecida aparece nesta captura."
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
        if d is None or d.key.startswith(DEMO_KEY):
            self.notice("Escolha no Início uma atividade capturada para excluir.", True)
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
        frame = self.svc.grab()
        if frame is None:
            self.notice("Não foi possível capturar a janela do jogo.", True)
            return
        self.notice(f"Captura salva em {self.svc.save_capture(frame)}")

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
        for r in self.svc.store.all(limit=200):
            res = "acerto" if r.hit else ("erro" if r.hit is False else "sem resultado")
            self.tree_shots.insert("", "end", iid=str(r.id), values=(
                r.id, f"{r.angle:.0f}°", f"{r.force:.1f}", f"{r.wind:+.1f}", f"{r.distance:.2f}",
                "—" if r.impact_x is None else f"{r.impact_x:.2f}", res, r.method, r.mode))
        st = self.svc.calibrator.stats()
        if not st["disparos"]:
            self.lbl_stats.configure(text="Nenhum disparo registrado ainda.")
            return
        rate = "sem dados" if st["taxa_acerto"] is None else f"{st['taxa_acerto']:.0%}"
        err = "sem dados" if st["erro_abs_medio"] is None else f"{st['erro_abs_medio']:.2f}"
        n_corr = sum(v["n"] for k, v in st["modelos"].items() if k.endswith("|*"))
        self.lbl_stats.configure(text=f"{st['disparos']} disparos, {st['avaliados']} com resultado. Acerto: {rate}. "
                                 f"Erro médio de onde caiu: {err}. Correções aprendidas com {n_corr} disparo(s).")

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
            has_window=self.svc.window is not None, demo=self.simulated.get(),
            activity_name=(r.d.name if alive else (d.name if d else None)),
            activity_auto=(d.auto_allowed if d else True),
            status=self.svc.status, alive=alive, reason=(r.reason if r else ""),
            screen=(r.current_state if r else "desconhecido"),
            emergency=self.svc.kill.triggered, emergency_reason=self.svc.kill.reason,
            my_turn=(obs.my_turn if obs else None),
            unknown_screen=bool(alive and r.unknown_screen),
            completed=(r.counters.completed if r else 0), runs=(r.limits.runs if r else self._runs()))

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
            self.lbl_target.configure(text=f"{target}{method_label(bst.method)}, chance estimada "
                                           f"{bst.hit_probability:.0%}.")
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
def _smoke(app: MainWindow, seconds: float, report: dict, done):
    """Exercita a interface sem o jogo: demonstração, iniciar, pausar, retomar, parar e emergência."""
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
        app._fill_activity_list()
        app.run_mode.set("cont")
        app._update_status()
        check("demonstracao_listada", app.selected_activity() is not None)
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
    at(span * 0.80, s_stopped)
    at(span * 0.85, s_emergency)

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


def _install_error_hooks(root: tk.Tk):
    """No .exe sem console, erros de botões e de threads iriam para lugar nenhum."""
    def on_tk_error(exc_type, exc, tb):
        log.error("erro na interface", exc_info=(exc_type, exc, tb))
        if not headless():
            try:
                messagebox.showerror("DDClássico Bot", f"Ocorreu um erro: {exc}\n\nOs detalhes estão no Registro "
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
                messagebox.showerror("DDClássico Bot", f"O programa não conseguiu iniciar: {exc}\n\n"
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
            messagebox.showerror("DDClássico Bot", f"Erro ao montar a interface: {exc}")
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
