"""Detectar jogo: descobre sozinho qual janela é o jogo e qual é o launcher.

Nada de nomes de processo, títulos ou coordenadas fixos. As pistas vêm do computador:

- **parentesco de processos**: o launcher abre o cliente do jogo; a janela de um processo
  aberto por outro processo com janela é o jogo, e o processo que o abriu é o launcher;
- **janela nova**: durante a espera, uma janela grande que aparece na mesma família de
  processos é o jogo que acabou de abrir;
- **área interna**: quando o jogo aparece dentro do launcher, ele ocupa uma janela interna
  grande; essa área (não a janela inteira, com os botões do launcher) recebe os comandos;
- **perfil salvo**: o programa e a classe da janela da última detecção confirmada;
- **palavras-chave** (``window.title_keywords``): só dizem onde começar a procurar. São
  editáveis e a família de processos é descoberta a partir delas.

Quando a escolha não é segura (duas candidatas parecidas), devolve as candidatas para o
usuário escolher numa lista com prévia. Nunca escolhe a janela do próprio bot.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .game_window import GameWindowProfile
from .winapi import WindowInfo

GAME, LAUNCHER_ONLY, CHOOSE, NOTHING = "jogo", "launcher_sem_jogo", "escolher", "nada"
MIN_W, MIN_H = 400, 300           # menor área em que uma batalha cabe
EMBED_FRACTION = 0.55             # janela interna que ocupa mais que isso da janela é a área do jogo
CLEAR_MARGIN = 25                 # vantagem de pontos para escolher sozinho
# processos do próprio Windows que abrem programas (área de trabalho, menu iniciar): não são launcher
SHELL_CLASSES = ("Progman", "Shell_TrayWnd", "WorkerW")


@dataclass
class Candidate:
    window: WindowInfo
    score: int = 0
    reasons: list[str] = field(default_factory=list)

    def add(self, points: int, why: str):
        self.score += points
        self.reasons.append(why)


@dataclass
class Detection:
    state: str                          # jogo | launcher_sem_jogo | escolher | nada
    game: WindowInfo | None = None
    launcher: WindowInfo | None = None
    candidates: list[Candidate] = field(default_factory=list)
    same_window: bool = False           # o jogo é desenhado dentro da janela do launcher
    confident: bool = False             # escolhido por evidência forte (não só por ser o único)

    @property
    def message(self) -> str:
        if self.state == GAME:
            where = "dentro da janela do launcher" if self.same_window else (
                "aberto pelo launcher" if self.launcher is not None else "em janela própria")
            return f"Jogo encontrado ({where})"
        return {LAUNCHER_ONLY: "Launcher aberto; aguardando o jogo abrir",
                CHOOSE: "Mais de uma janela parece o jogo: escolha qual",
                NOTHING: "Jogo não encontrado"}[self.state]


def big_enough(w: WindowInfo) -> bool:
    return w.visible and w.width >= MIN_W and w.height >= MIN_H


def _family(windows, parents: dict[int, int], seeds: set[int], shell_pids: set[int], own_pid: int) -> set[int]:
    """Processos aparentados às sementes: elas, seus filhos/netos e quem as abriu (se tiver janela)."""
    with_window = {w.pid for w in windows if not w.parent}
    fam = set(seeds)
    changed = True
    while changed:
        changed = False
        for pid, ppid in parents.items():
            if pid in fam or pid == own_pid:
                continue
            if ppid in fam and pid not in shell_pids:
                fam.add(pid)
                changed = True
        for pid in list(fam):
            ppid = parents.get(pid)
            if ppid and ppid not in fam and ppid in with_window and ppid not in shell_pids and ppid != own_pid:
                fam.add(ppid)
                changed = True
    return fam


def detect(windows: list[WindowInfo], parents: dict[int, int], own_pid: int, keywords=(),
           profile: GameWindowProfile | None = None, baseline: set[int] | None = None,
           rejected: set[int] | None = None) -> Detection:
    """Analisa as janelas (principais e internas) e os processos (pid -> pid do pai).

    ``baseline``: janelas que já existiam quando a espera começou (as novas ganham pontos).
    ``rejected``: janelas que o usuário disse não serem o jogo (ex.: a página do launcher).
    """
    rejected = rejected or set()
    profile = profile or GameWindowProfile()
    kws = [k.lower() for k in keywords or [] if k]
    windows = [w for w in windows if w.pid != own_pid]
    shell_pids = {w.pid for w in windows if w.cls in SHELL_CLASSES}

    by_hwnd = {x.hwnd: x for x in windows}

    def top_of(w: WindowInfo) -> WindowInfo | None:
        seen, cur = 0, w
        while cur is not None and cur.parent and seen < 16:
            cur, seen = by_hwnd.get(cur.parent), seen + 1
        return cur

    def keyword_hit(w: WindowInfo) -> bool:
        text = f"{w.title} {w.exe}".lower()
        return any(k in text for k in kws)

    def is_launcher_rule(w):
        return profile.launcher is not None and profile.launcher.matches(w)

    def is_game_rule(w):
        return profile.game is not None and profile.game.matches(w)

    seeds = {w.pid for w in windows if (keyword_hit(w) or is_game_rule(w) or is_launcher_rule(w))
             and w.pid not in shell_pids}
    if not seeds:
        return Detection(NOTHING)
    fam = _family(windows, parents, seeds, shell_pids, own_pid)
    fam_windows = [w for w in windows if w.pid in fam]
    fam_tops = [w for w in fam_windows if not w.parent]
    # processos da família com janela própria que foram abertos por outro processo da família com janela
    windowed = {w.pid for w in fam_tops}

    def opener(pid) -> int | None:
        """Processo com janela que abriu este (pulando intermediários sem janela, ex.: atualizador)."""
        cur, seen = parents.get(pid), 0
        while cur and seen < 4:
            if cur in windowed and cur != pid:
                return cur
            if cur not in fam or cur in shell_pids:
                return None
            cur, seen = parents.get(cur), seen + 1
        return None

    spawned = {pid for pid in windowed if opener(pid) is not None}

    def opener_window(pid) -> WindowInfo | None:
        ppid = opener(pid)
        opts = [w for w in fam_tops if w.pid == ppid]
        return max(opts, key=lambda w: w.area) if opts else None

    # janelas internas grandes, por janela principal
    embedded: dict[int, WindowInfo] = {}
    for w in fam_windows:
        if not w.parent or not big_enough(w):
            continue
        top = top_of(w)
        if top is None or top.area <= 0 or w.area < EMBED_FRACTION * top.area:
            continue
        cur = embedded.get(top.hwnd)
        # entre áreas aninhadas, fica a mais interna (onde o jogo é desenhado), se for grande
        if cur is None or (w.area <= cur.area and w.parent == cur.hwnd) or w.area > cur.area * 1.2:
            embedded[top.hwnd] = w

    cands: list[Candidate] = []
    launcher_tops: set[int] = set()
    for pid in spawned:
        op = opener_window(pid)
        if op is not None:
            launcher_tops.add(op.hwnd)
    old_launchers = {w.hwnd for w in fam_tops if is_launcher_rule(w) and baseline is not None and w.hwnd in baseline}
    for top in fam_tops:
        if is_launcher_rule(top) and top.pid not in spawned:
            if old_launchers and top.hwnd not in old_launchers:
                continue  # janela nova do mesmo programa do launcher, com o launcher ainda aberto: é o jogo
            launcher_tops.add(top.hwnd)
    for top in fam_tops:
        if not big_enough(top) and top.hwnd not in embedded:
            continue
        surface = embedded.get(top.hwnd)
        target = surface if surface is not None else top
        if not big_enough(target) or target.hwnd in rejected:
            continue
        is_new = baseline is not None and target.hwnd not in baseline
        c = Candidate(target)
        if top.pid in spawned:
            c.add(45, "aberta pelo launcher")
        if is_game_rule(target):
            c.add(40, "mesmo programa da última detecção")
        if is_new and top.hwnd not in baseline:
            c.add(30, "apareceu agora")
        elif is_new and surface is not None:
            c.add(30, "área de jogo apareceu agora")
        if surface is not None:
            c.add(15, "área interna onde o jogo é desenhado")
        if keyword_hit(top) or keyword_hit(target):
            c.add(10, "título ou programa com o nome do jogo")
        if top.hwnd in launcher_tops and top.pid not in spawned:
            if surface is None:
                continue  # a própria janela do launcher, sem área de jogo: nunca é o jogo
            if not is_game_rule(surface) and not is_new:
                continue  # área que já fazia parte do launcher (não é a que o usuário confirmou como jogo)
            if is_launcher_rule(top) and not is_game_rule(target):
                c.add(-20, "janela do launcher")
            if spawned:
                c.add(-30, "launcher com o jogo aberto em outra janela")
        c.add(min(8, target.area // 250_000), "tamanho")
        cands.append(c)
    cands.sort(key=lambda c: (c.score, c.window.area), reverse=True)

    def launcher_for(c: Candidate) -> tuple[WindowInfo | None, bool]:
        top = top_of(c.window)
        if top is None:
            return None, False
        if top.pid in spawned:
            return opener_window(top.pid), False
        if c.window.parent:
            return top, True
        # sem parentesco de processos, só um launcher conhecido é evidência suficiente; com vários
        # abertos, escolher "o maior" ou "o primeiro" associaria o jogo ao launcher errado
        known = {w.pid: w for w in fam_tops if w.hwnd in launcher_tops and w.hwnd != top.hwnd}
        if len(known) == 1:
            pid = next(iter(known))
            return max((w for w in fam_tops if w.pid == pid and w.hwnd in launcher_tops), key=lambda w: w.area), False
        return None, False

    if not cands:
        launchers = [w for w in fam_tops if w.hwnd in launcher_tops or is_launcher_rule(w)]
        if launchers or fam_tops:
            return Detection(LAUNCHER_ONLY, None, max(launchers or fam_tops, key=lambda w: w.area))
        return Detection(NOTHING)
    best = cands[0]
    strong = best.score >= 40
    clear = len(cands) == 1 or best.score - cands[1].score >= CLEAR_MARGIN
    if not clear:
        return Detection(CHOOSE, candidates=cands[:8])
    launcher, same = launcher_for(best)
    if launcher is None and best.window.parent == 0 and not strong and is_launcher_rule(best.window):
        return Detection(LAUNCHER_ONLY, None, best.window)
    return Detection(GAME, best.window, launcher, cands[:8], same_window=same, confident=strong)


def pick_at(windows: list[WindowInfo], x: int, y: int, own_pid: int, hit: int = 0, root_of=None
            ) -> WindowInfo | None:
    """Janela sob o ponto, sem contar as do próprio bot (a camada de seleção fica por cima).

    ``windows`` vem na ordem do Windows (janelas principais da frente para trás, cada uma
    seguida das suas internas). Fica a área interna grande mais funda que contém o ponto,
    para o clique cair na área do jogo e não na moldura do launcher.

    ``hit``: a janela que o próprio Windows diz estar no ponto (``WindowFromPoint``, com a
    camada de seleção escondida). Quando ela é de outro programa que não o bot, só a janela
    principal dela vale: a ordem das janelas sozinha conta janelas que estão na lista mas não
    aparecem no ponto (transparentes ao clique, ocultas pelo Windows) e escolhia uma janela
    sem relação com o alvo.
    """
    def inside(w):
        return w.left <= x < w.left + w.width and w.top <= y < w.top + w.height

    root = root_of(hit) if hit and root_of is not None else 0
    if root and not any(w.hwnd == root and w.pid != own_pid for w in windows):
        root = 0  # a janela do ponto é do bot (ou não está na lista): fica a ordem das janelas
    by_parent: dict[int, list[WindowInfo]] = {}
    for w in windows:
        if w.parent:
            by_parent.setdefault(w.parent, []).append(w)
    for top in windows:
        if top.parent or top.pid == own_pid or not top.visible or not inside(top):
            continue
        if root and top.hwnd != root:
            continue
        best, frontier = top, [top.hwnd]
        while frontier:
            nxt = []
            for h in frontier:
                for c in by_parent.get(h, []):
                    if c.visible and inside(c) and big_enough(c):
                        best = c
                        nxt.append(c.hwnd)
            frontier = nxt[:1]
        return best
    return None
