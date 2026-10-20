"""O que a faixa de estado mostra em cada situação (sem Tkinter: testável)."""
from __future__ import annotations

from dataclasses import dataclass

from ..activities import COMMON_TEMPLATES, RunStatus
from ..vision.perception import STATE_LABELS


@dataclass
class UiSnapshot:
    has_window: bool
    demo: bool
    activity_name: str | None
    activity_auto: bool = True
    status: RunStatus = RunStatus.IDLE
    alive: bool = False
    reason: str = ""
    screen: str = "desconhecido"
    emergency: bool = False
    emergency_reason: str = ""
    my_turn: bool | None = None
    unknown_screen: bool = False
    completed: int = 0
    runs: int = 1
    window_state: str = ""   # jogo | launcher_sem_jogo | escolher | confirmar | nada | "" (desconhecido)


@dataclass
class Banner:
    kind: str
    title: str
    detail: str = ""


# orientação para os motivos mais comuns de pausa/erro (trecho do motivo -> o que fazer)
ADVICE = [
    ("regras do servidor", "Abra Configurações, leia o aviso e marque a autorização."),
    ("falta calibrar", "Abra a aba Calibração, capture a tela do jogo e salve cada item da lista (uma vez só)."),
    ("selecione a janela", "Abra o DDClássico pelo launcher e clique em Detectar jogo, no topo."),
    ("confirme a janela", "Clique em Detectar jogo e confira na prévia se é a tela do jogo."),
    ("launcher está aberto", "Entre no jogo pelo launcher. O bot conecta sozinho quando o jogo abrir."),
    ("na frente do jogo", "Deixe a janela do jogo visível; não coloque outras janelas por cima durante a rotina."),
    ("foco do teclado", "Clique uma vez dentro da área do jogo (não no launcher) e depois em Retomar."),
    ("não foi encontrad", "Abra o DDClássico pelo launcher e clique em Detectar jogo, no topo."),
    ("tela desconhecida", "Deixe o jogo numa tela conhecida (lobby) ou capture o modelo dessa tela em Calibração."),
    ("não reconhecida", "Deixe o jogo numa tela conhecida (lobby) ou capture o modelo dessa tela em Calibração."),
    ("não encontrado na tela", "Capture de novo esse botão em Calibração > Modelos (a aparência pode ter mudado)."),
    ("não avançou", "Confira se o jogo pede alguma confirmação e resolva no jogo; depois clique em Retomar."),
    ("muitos cliques", "Confira o jogo: o botão pode estar desativado (energia, ingressos). Depois clique em Retomar."),
    ("desconex", "Entre no jogo de novo e clique em Iniciar."),
    ("foco", "Deixe a janela do jogo na frente e não use o mouse/teclado enquanto o bot joga."),
    ("PvE", "Escolha uma instância ou partida contra o computador."),
    ("proibido", "Esse botão gasta recursos. Libere-o em Configurações só se tiver certeza."),
    ("tempo máximo", "Aumente o tempo máximo em Configurações se quiser rotinas mais longas."),
    ("derrotas", "O limite de derrotas foi atingido. Ajuste a mira em Mira e disparos ou aumente o limite."),
    ("ângulo atual desconhecido", "Treine os números do ângulo em Calibração > Números."),
]


METHOD_LABELS = {"fisica": "Modelo físico", "a20": "Tabela 20°", "a30": "Tabela 30°", "a50": "Tabela 50°",
                 "a65": "Tabela 65°", "high": "Tiro alto", "medium": "Tiro médio"}


def method_label(key: str) -> str:
    return METHOD_LABELS.get(key, key)


def pick_options(candidates, limit=8, per_method=2):
    """Opções para mostrar: as melhores de cada método, sem dezenas de variações quase iguais."""
    out, seen = [], {}
    for c in candidates:
        if seen.get(c.method, 0) >= per_method:
            continue
        seen[c.method] = seen.get(c.method, 0) + 1
        out.append(c)
        if len(out) >= limit:
            break
    return out


def advice(reason: str) -> str:
    low = (reason or "").lower()
    for key, text in ADVICE:
        if key.lower() in low:
            return text
    return ""


def describe(s: UiSnapshot) -> Banner:
    """Faixa de estado. Numa demonstração, o título sempre diz que é simulação (nada é do jogo real)."""
    b = _describe(s)
    run_states = s.alive or s.status in (RunStatus.FINISHED, RunStatus.FAILED)
    if s.demo and run_states and b.kind != "emergency":
        b = Banner(b.kind, f"Demonstração · {b.title}", f"{b.detail} Simulação: nada disto aconteceu no jogo.".strip())
    return b


def _describe(s: UiSnapshot) -> Banner:
    if s.emergency:
        return Banner("emergency", "Parada de emergência",
                      "Nenhum comando será enviado ao jogo. Clique em Iniciar quando quiser recomeçar.")
    running = s.alive and s.status in (RunStatus.RUNNING, RunStatus.PAUSED)
    if running and s.status == RunStatus.PAUSED:
        tip = advice(s.reason)
        title = ("Pausado" if not s.reason else s.reason[:1].upper() + s.reason[1:]
                 if s.reason.lower().startswith("pausado") else f"Pausado: {s.reason}")
        return Banner("paused", title,
                      tip or "Clique em Retomar para continuar ou em Parar para encerrar.")
    if running:
        progress = (f"{s.completed} de {s.runs} concluída(s)." if s.runs
                    else f"{s.completed} concluída(s), repetição contínua.")
        where = STATE_LABELS.get(s.screen, s.screen)
        if s.unknown_screen:
            return Banner("warning", f"{s.activity_name}: tela não reconhecida",
                          "Tentando recuperar pelos meios normais do jogo. Se não conseguir, o bot pausa.")
        if s.screen == "batalha":
            turn = {True: "seu turno, mirando", False: "turno do adversário", None: "lendo o turno"}[s.my_turn]
            return Banner("combat", f"Em combate: {turn}", f"{s.activity_name}. {progress}")
        return Banner("running", f"Executando {s.activity_name}", f"Tela atual: {where}. {progress}")
    if s.status == RunStatus.FINISHED:
        return Banner("done", "Concluído", s.reason or "A quantidade configurada foi concluída.")
    if s.status == RunStatus.FAILED:
        tip = advice(s.reason)
        return Banner("error", f"Interrompido: {s.reason}", tip)
    if not s.has_window and not s.demo:
        if s.window_state == "launcher_sem_jogo":
            return Banner("idle", "Launcher aberto, aguardando o jogo",
                          "Entre no jogo pelo launcher. O bot conecta sozinho quando a janela do jogo aparecer.")
        if s.window_state in ("escolher", "confirmar"):
            return Banner("warning", "Confirme a janela do jogo",
                          "O bot achou o jogo, mas precisa que você confira na prévia. Clique em Detectar jogo.")
        return Banner("warning", "Jogo não encontrado",
                      "Abra o DDClássico pelo launcher e clique em Detectar jogo, no topo. "
                      "Para conhecer o programa sem o jogo, ligue o modo demonstração.")
    if not s.activity_name:
        return Banner("idle", "Escolha o que jogar",
                      "As instâncias e partidas aparecem aqui depois de capturadas do menu do jogo "
                      "(Calibração > Menu). No modo demonstração há uma de cada para testar.")
    if not s.activity_auto:
        return Banner("warning", f"{s.activity_name} envolve outros jogadores",
                      "O bot não joga sozinho contra pessoas. Use a mira assistida na aba Diagnóstico.")
    if s.status == RunStatus.IDLE and s.reason.startswith("parado"):
        return Banner("ready", "Parado", f"Pronto para iniciar {s.activity_name} de novo.")
    return Banner("ready", "Pronto para iniciar",
                  f"{s.activity_name}." + (" Modo demonstração: nada é enviado ao jogo." if s.demo else ""))


def humanize(message: str) -> str:
    """Troca nomes internos (telas e modelos) pelos nomes que o usuário vê na Calibração."""
    import re
    names = {**{f"estado_{k}": f"tela {v}" for k, v in STATE_LABELS.items()},
             **{k: v.split(" (")[0] for k, v in COMMON_TEMPLATES.items()}}

    def tela(m):
        return f"Tela: {STATE_LABELS.get(m.group(1), m.group(1))}"
    message = re.sub(r"^tela: (\w+)$", tela, message)
    message = re.sub(r"\b(botao_\w+|carta_recompensa|estado_\w+)\b", lambda m: names.get(m.group(1), m.group(1)),
                     message)
    message = re.sub(r"\b(instancia|partida)_(\w+)", lambda m: m.group(2).replace("_", " "), message)
    message = message.replace(" -> ", ": ")
    return message[:1].upper() + message[1:]
