"""Percorre os estados da interface e salva capturas da janela (revisão visual).

Também audita o layout: widgets com texto cortado (pedem mais espaço do que receberam), abas
espremidas, widgets que saem da janela ou do painel onde estão e listas sem espaço para duas
linhas. Roda em modo demonstração; nada é enviado a jogo nenhum.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from ..activities import RunStatus

log = logging.getLogger(__name__)
MIN_LIST_ROWS = 2  # uma lista (Treeview) precisa mostrar ao menos estas linhas inteiras


def _grab(root, path: Path) -> bool:
    root.update_idletasks()
    root.update()
    try:
        from PIL import ImageGrab
        x, y = root.winfo_rootx(), root.winfo_rooty()
        w, h = root.winfo_width(), root.winfo_height()
        ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(path)
        return True
    except Exception as exc:  # sem tela (ex.: CI sem desktop)
        log.warning("captura de tela falhou: %s", exc)
        return False


def _text(w) -> str:
    try:
        return str(w.cget("text"))[:60] if "text" in w.keys() else ""
    except Exception:
        return ""


def _ints(value) -> list[int]:
    """Números de uma opção de estilo: o ttk devolve tupla ((10, 5)) ou texto ("10 5")."""
    items = value if isinstance(value, (tuple, list)) else str(value).translate(str.maketrans("{}(),", "     ")).split()
    try:
        return [int(float(str(v))) for v in items]
    except ValueError:
        return []


def _squeezed_tabs(nb) -> dict | None:
    """Abas de um ttk.Notebook mais largas, somadas, que o próprio caderno (o Tk as espreme e corta os nomes).

    A largura natural de cada aba é pelo menos o texto mais o espaço interno do estilo; cadernos com as abas
    escondidas (layout vazio) não entram."""
    import tkinter as tk
    from tkinter import ttk
    st = ttk.Style(nb)
    style = str(nb.cget("style") or "TNotebook")
    tab = f"{style}.Tab"
    try:
        layout = st.layout(tab)
    except tk.TclError:
        layout = None  # sem layout próprio: usa o do estilo pai, com as abas visíveis
    if layout and all(name == "null" for name, _ in layout):
        return None
    pad = _ints(st.lookup(tab, "padding")) or [0]
    pad_x = pad[0] + (pad[2] if len(pad) > 2 else pad[0])
    margins = _ints(st.lookup(style, "tabmargins")) or [0]
    font = st.lookup(tab, "font") or "TkDefaultFont"
    texts = [str(nb.tab(t, "text")) for t in nb.tabs()]
    need = sum(int(nb.tk.call("font", "measure", font, t)) + pad_x for t in texts)
    need += margins[0] + (margins[2] if len(margins) > 2 else margins[0])
    if need > nb.winfo_width() + 2:
        return {"tipo": "abas cortadas", "widget": "TNotebook", "texto": " | ".join(texts)[:60],
                "pedido": need, "recebido": nb.winfo_width()}
    return None


def _list_rows(tree, visible_h: int) -> float:
    from tkinter import ttk
    style = str(tree.cget("style") or "Treeview")
    row_h = (_ints(ttk.Style(tree).lookup(style, "rowheight")) or [20])[0] or 20
    heading = row_h if "headings" in str(tree.cget("show")) else 0  # o cabeçalho tem mais ou menos uma linha
    return (visible_h - heading) / row_h


def audit_layout(root) -> list[dict]:
    """Problemas de layout da janela ``root`` (a janela principal ou um diálogo).

    - texto cortado: label/botão que pede mais largura do que recebeu (sem quebra de linha);
    - abas cortadas: as abas de um caderno não cabem e o Tk espreme os nomes;
    - fora da janela / cortado: widget que passa da borda da janela ou do painel onde está (áreas com
      rolagem, dentro de um Canvas, não contam);
    - lista sem espaço: Treeview que mostra menos de ``MIN_LIST_ROWS`` linhas inteiras.
    Só o widget mais externo de cada corte é listado (os de dentro dele são consequência).
    """
    import tkinter as tk
    problems = []
    ox, oy = root.winfo_rootx(), root.winfo_rooty()
    # (widget, área visível herdada (x0, y0, x1, y1) ou None dentro de rolagem, corte já informado acima)
    stack = [(root, (0, 0, root.winfo_width(), root.winfo_height()), False)]
    while stack:
        w, clip, reported = stack.pop()
        if w is not root and isinstance(w, tk.Toplevel):
            continue  # outra janela (diálogo): auditada à parte
        if not w.winfo_ismapped():
            continue
        cls = w.winfo_class()
        x, y = w.winfo_rootx() - ox, w.winfo_rooty() - oy
        ww, wh = w.winfo_width(), w.winfo_height()
        child_clip = clip
        if ww > 1 and wh > 1:
            if cls in ("TLabel", "TButton", "TCheckbutton", "TRadiobutton", "Label"):
                try:
                    wrap = int(str(w.cget("wraplength")) or 0)
                except Exception:
                    wrap = 0
                if wrap == 0 and w.winfo_reqwidth() > ww + 2:
                    problems.append({"tipo": "texto cortado", "widget": cls, "texto": _text(w),
                                     "pedido": w.winfo_reqwidth(), "recebido": ww})
            if cls == "TNotebook":
                squeezed = _squeezed_tabs(w)
                if squeezed:
                    problems.append(squeezed)
            visible_h = wh
            if clip is not None:
                vx0, vy0 = max(x, clip[0]), max(y, clip[1])
                vx1, vy1 = min(x + ww, clip[2]), min(y + wh, clip[3])
                visible_h = max(0, vy1 - vy0)
                cut = vx1 - vx0 < ww - 2 or vy1 - vy0 < wh - 2
                if cut and not reported:
                    outside = x + ww > root.winfo_width() + 2 or y + wh > root.winfo_height() + 2
                    problems.append({"tipo": "fora da janela" if outside else "cortado", "widget": cls,
                                     "texto": _text(w), "x": x, "y": y, "w": ww, "h": wh,
                                     "visivel": [max(0, vx1 - vx0), visible_h]})
                    reported = True
                child_clip = (vx0, vy0, max(vx0, vx1), max(vy0, vy1))
            if cls == "Treeview" and _list_rows(w, visible_h) < MIN_LIST_ROWS - 0.05:
                problems.append({"tipo": "lista sem espaço", "widget": cls, "texto": "",
                                 "linhas": round(_list_rows(w, visible_h), 2), "altura_visivel": visible_h})
        if cls == "Canvas":
            child_clip = None  # o conteúdo de uma área com rolagem pode passar da borda
        stack.extend((c, child_clip, reported) for c in w.winfo_children())
    return problems


def run_screenshots(app, out: Path, report: dict, done):
    out.mkdir(parents=True, exist_ok=True)
    root = app.root
    shots: list[str] = []
    layout: dict[str, list] = {}
    scale = app.th.scale
    tag = f"{int(round(scale * 100))}"
    steps = []

    def snap(name):
        root.update_idletasks()
        app._update_status()
        app._update_buttons()
        path = out / f"{tag}_{name}.png"
        if _grab(root, path):
            shots.append(path.name)
        layout[name] = audit_layout(root)

    def add(delay, fn):
        steps.append((delay, fn))

    def snap_dialog(name):
        dlg = app.detect_dialog
        if dlg is None:
            return
        dlg.update_idletasks()
        path = out / f"{tag}_{name}.png"
        if _grab(dlg, path):
            shots.append(path.name)
        layout[name] = audit_layout(dlg)

    def detect_steps():
        from ..detection import CHOOSE, Candidate, Detection
        from ..winapi import WindowInfo
        app.open_detect()
        report["principal_minimizada_ao_detectar"] = root.state() == "iconic"
        root.after(1500, lambda: snap_dialog("01b_detectar_procurando"))

        def choose():
            dlg = app.detect_dialog
            fake = [WindowInfo(1, "DDTank - servidor 1", 0, 0, 1000, 600, pid=1, exe="cliente.exe"),
                    WindowInfo(2, "DDTank - servidor 2", 0, 0, 1000, 600, pid=2, exe="cliente.exe")]
            dlg.mode = "procurando"
            dlg._on_detection(Detection(CHOOSE, candidates=[Candidate(w, 50) for w in fake]))
            root.after(800, lambda: (snap_dialog("01c_detectar_escolher"), confirm()))

        def confirm():
            dlg = app.detect_dialog
            w = WindowInfo(3, "Launcher", 0, 0, 1100, 680, pid=3, exe="launcher.exe")
            dlg.shown, dlg.mode = w, "confirmar"
            dlg._render()
            root.after(800, lambda: (snap_dialog("01d_detectar_confirmar"), dlg.close(),
                                     report.__setitem__("principal_restaurada", root.state() == "normal")))
        root.after(2500, choose)

    t = 0.5
    add(t, lambda: (app.nb.select(app.tab_home), snap("01_inicio_sem_jogo")))
    t += 0.6
    add(t, detect_steps)
    t += 5.5
    add(t, lambda: (app.simulated.set(True), app._toggle_demo(), app.run_mode.set("qtd"), app.run_count.set(3),
                    snap("02_pronto_demonstracao")))
    t += 0.8
    add(t, lambda: app.btn_start.invoke())
    t += 2.5
    add(t, lambda: snap("03_executando"))

    def wait_battle(deadline=[None]):
        if deadline[0] is None:
            deadline[0] = time.monotonic() + 40
        r = app.svc.runner
        if r and r.current_state == "batalha" and app.svc.engine and app.svc.engine.last_recommendation:
            snap("04_combate")
            root.after(300, pause_step)
        elif time.monotonic() > deadline[0]:
            snap("04_combate_timeout")
            root.after(300, pause_step)
        else:
            root.after(300, wait_battle)

    def pause_step():
        app.btn_pause.invoke()
        root.after(700, lambda: (snap("05_pausado"), app.btn_pause.invoke(), root.after(500, finish_run)))

    def finish_run(deadline=[None]):
        if deadline[0] is None:
            deadline[0] = time.monotonic() + 120
        if app.svc.status == RunStatus.FINISHED or not (app.svc.runner and app.svc.runner.alive):
            snap("06_concluido")
            root.after(300, failure_step)
        elif time.monotonic() > deadline[0]:
            snap("06_concluido_timeout")
            app.svc.stop()
            root.after(300, failure_step)
        else:
            root.after(500, finish_run)

    def failure_step():
        d = app.selected_activity()
        app.svc.start(d, 0, simulated=True, faults={"disconnect_at": 6})
        root.after(4000, lambda: (snap("07_erro_desconexao"), unknown_step()))

    def unknown_step():
        d = app.selected_activity()
        app.svc.start(d, 0, simulated=True, faults={"unknown_at": 3, "unknown_for": 100000})
        root.after(2500, lambda: (snap("08_tela_desconhecida"), root.after(23000, paused_unknown)))

    def paused_unknown():
        snap("09_pausado_tela_desconhecida")
        app.svc.stop()
        root.after(800, emergency_step)

    def emergency_step():
        app.run_mode.set("cont")
        app.btn_start.invoke()
        root.after(1500, lambda: (app.svc.emergency_stop(), root.after(1200, lambda: (snap("10_emergencia"),
                                                                                       tabs_step()))))

    def tabs_step():
        names = ["11_calibracao", "12_diagnostico", "13_mira", "14_configuracoes", "15_registro"]
        tabs = [app.tab_calib, app.tab_diag, app.tab_aim, app.tab_cfg, app.tab_log]

        def show(i):
            if i >= len(tabs):
                root.after(300, alvos)
                return
            app.nb.select(tabs[i])
            if tabs[i] is app.tab_aim:
                app.calc_aim()
            root.after(700, lambda: (snap(names[i]), show(i + 1)))
        show(0)

    def alvos():
        # página Alvos da Calibração (estratégias por instância), com a última aba visível
        app.nb.select(app.tab_calib)
        app.calib_nb.select(len(app.calib_nb.tabs()) - 1)
        root.after(700, lambda: (snap("16_calibracao_alvos"), root.after(300, final)))

    def final():
        problems = {k: v for k, v in layout.items() if v}
        report.update({"escala": scale, "capturas": shots, "problemas_layout": problems,
                       "geometria": root.winfo_geometry(),
                       "tela": [root.winfo_screenwidth(), root.winfo_screenheight()]})
        (out / f"{tag}_layout.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        report["resultado"] = "OK"
        done()

    for delay, fn in steps:
        root.after(int(delay * 1000), fn)
    root.after(int((t + 0.5) * 1000), wait_battle)
