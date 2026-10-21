"""Atividades automáticas (partidas e instâncias) como máquina de estados reativa.

Cada iteração identifica a tela atual por evidência visual (modelos ``estado_*``) e
executa a ação configurada para essa tela. Nada avança só por temporizador: as
esperas servem apenas para dar tempo à tela de mudar, e a mudança é conferida.

Definições ficam em ``instancias/*.json`` (pasta do usuário) e são criadas a partir
das opções que o próprio cliente mostra (Calibração > Opções do menu). Não existe
lista fixa de instâncias no código.

Travas:
- exige autorização explícita (``automation.server_rules_confirmed``);
- categoria ``pvp``/``matchmaking`` (contra jogadores) não roda sozinha;
- nunca clica em modelos proibidos (compra, moeda premium etc.);
- uma tela só vale depois de lida igual em leituras seguidas (um quadro falso não conta);
- com a tela desconhecida o bot não age às cegas: só fecha um aviso se o botão de fechar
  for reconhecido; senão pausa e informa o motivo;
- cliques repetidos na mesma tela são limitados.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .automation.safety import Aborted, Cancelled, FocusLost, InputBlocked, KillSwitch, NeedsAttention
from .util import atomic_write_text

log = logging.getLogger(__name__)

TERMINAL_RESULTS = ("vitoria", "derrota")
CATEGORIES = {"pve": "PvE / contra o computador", "solo": "Solo", "matchmaking": "Fila (outros jogadores)",
              "pvp": "PvP contra jogadores"}
AUTO_CATEGORIES = ("pve", "solo")
# modelos que nunca são clicados, além dos listados em cada definição e na configuração
DEFAULT_FORBIDDEN = ("botao_comprar", "botao_loja", "botao_recarregar", "botao_cupons", "botao_premium",
                     "botao_ranqueada",
                     # pagos nas instâncias (cupons), segundo um emulador do DDTank 4.1 (sources.json)
                     "botao_ultima_fase", "botao_tentar_novamente", "carta_paga")
NAME_RE = re.compile(r"[a-z0-9_]{1,64}")
# modelos que escolhem QUAL atividade jogar: sem eles na tela, o bot pausa (nunca escolhe outra no lugar)
SELECTION_PREFIXES = ("instancia_", "partida_", "dificuldade_")
# condição de uma ação ("se" no JSON): a escolha da atividade (opção e dificuldade) já foi feita nesta ida?
# Na sala do Cais de Expedição a instância é escolhida dentro da própria sala: a mesma tela pede "escolher a
# instância" antes e "Iniciar" depois.
CONDITIONS = ("sem_escolha", "com_escolha")
CLICKS = ("clicar", "clicar_opcional", "confirmar_aviso")  # ações que clicam num modelo
# aviso do jogo ao iniciar sozinho uma instância difícil: só é confirmado com a permissão do usuário
SOLO_WARNING = "aviso_sozinho"


def is_selection(template: str | None) -> bool:
    return bool(template) and template.startswith(SELECTION_PREFIXES)


def valid_name(name) -> bool:
    """Nomes de modelo/atividade viram nomes de pasta e arquivo: só [a-z0-9_]."""
    return isinstance(name, str) and NAME_RE.fullmatch(name) is not None


@dataclass
class Action:
    kind: str                 # clicar | clicar_opcional | confirmar_aviso | tecla | aguardar | combate | concluir
    target: str | None = None  # modelo (clicar), tecla, resultado (concluir)
    seconds: float = 0.0
    when: str | None = None   # só age nessa condição (CONDITIONS); None = sempre

    @classmethod
    def parse(cls, raw: dict) -> "Action":
        if not isinstance(raw, dict):
            raise ValueError(f"ação inválida: {raw!r}")
        when = raw.get("se")
        if when is not None and when not in CONDITIONS:
            raise ValueError(f"condição inválida: {when!r} (use {' ou '.join(CONDITIONS)})")
        for kind, default_wait in (("clicar", 1.0), ("clicar_opcional", 0.5)):
            if kind in raw:
                if not valid_name(raw[kind]):
                    raise ValueError(f"nome de modelo inválido: {raw[kind]!r}")
                return cls(kind, raw[kind], _seconds(raw.get("espera", default_wait)), when)
        if "confirmar_aviso" in raw:
            # clica só com a permissão do usuário (instances.confirm_solo_warning); sem ela, pausa e explica
            if not valid_name(raw["confirmar_aviso"]):
                raise ValueError(f"nome de modelo inválido: {raw['confirmar_aviso']!r}")
            if when is not None:
                raise ValueError("'se' não vale para confirmar_aviso")
            return cls("confirmar_aviso", raw["confirmar_aviso"], _seconds(raw.get("espera", 1.5)))
        if "tecla" in raw:
            if not isinstance(raw["tecla"], str) or not re.fullmatch(r"[a-z0-9]{1,12}", raw["tecla"].lower()):
                raise ValueError(f"tecla inválida: {raw['tecla']!r}")
            return cls("tecla", raw["tecla"].lower(), _seconds(raw.get("espera", 0.5)), when)
        if when is not None:
            raise ValueError("'se' só vale para clicar, clicar_opcional e tecla")
        if "aguardar" in raw:
            return cls("aguardar", None, _seconds(raw["aguardar"]))
        if raw.get("combate"):
            return cls("combate")
        if "concluir" in raw:
            if raw["concluir"] not in TERMINAL_RESULTS:
                raise ValueError(f"resultado inválido: {raw['concluir']}")
            return cls("concluir", raw["concluir"])
        raise ValueError(f"ação desconhecida: {raw}")

    def to_raw(self) -> dict:
        if self.kind in ("clicar", "clicar_opcional", "tecla", "confirmar_aviso"):
            raw = {self.kind: self.target, "espera": self.seconds}
            if self.when:
                raw["se"] = self.when
            return raw
        if self.kind == "aguardar":
            return {"aguardar": self.seconds}
        if self.kind == "combate":
            return {"combate": True}
        return {"concluir": self.target}


def _seconds(v) -> float:
    s = float(v)
    if not 0 <= s <= 120:
        raise ValueError(f"espera fora da faixa (0-120 s): {v}")
    return s


@dataclass
class ActivityDef:
    key: str
    name: str
    kind: str = "instancia"           # instancia | partida
    category: str = "pve"
    description: str = ""
    flow: dict[str, list[Action]] = field(default_factory=dict)
    start_states: tuple[str, ...] = ("lobby",)
    forbidden: tuple[str, ...] = ()
    validated: bool = False           # validada no cliente real?
    strategy: str | None = None       # perfil de estratégia da instância (strategy.py), se houver
    path: Path | None = None
    builtin: bool = False             # pré-cadastrada (catalog.py): não fica na pasta do usuário
    instance: str | None = None       # instância do catálogo (ex.: "formigueiro")
    difficulty: str | None = None     # dificuldade do catálogo (ex.: "facil")
    option: str | None = None         # modelo da opção no menu que só esta atividade clica

    @property
    def auto_allowed(self) -> bool:
        return self.category in AUTO_CATEGORIES

    def templates_needed(self) -> list[str]:
        out = [f"estado_{s}" for s in self.flow]
        for actions in self.flow.values():
            out += [a.target for a in actions if a.kind in CLICKS and a.target]
        return sorted(set(out))

    def to_raw(self) -> dict:
        raw = {"id": self.key, "nome": self.name, "tipo": self.kind, "categoria": self.category,
               "descricao": self.description, "validada_no_cliente": self.validated,
               "estados_iniciais": list(self.start_states), "proibido": list(self.forbidden),
               "estrategia": self.strategy,
               "fluxo": {s: [a.to_raw() for a in acts] for s, acts in self.flow.items()}}
        for key, value in (("instancia", self.instance), ("dificuldade", self.difficulty), ("opcao", self.option)):
            if value:
                raw[key] = value
        return raw

    def save(self, folder: Path) -> Path:
        if not valid_name(self.key):
            raise ValueError(f"id de atividade inválido: {self.key!r}")
        path = Path(folder) / f"{self.key}.json"
        atomic_write_text(path, json.dumps(self.to_raw(), indent=2, ensure_ascii=False))
        self.path = path
        return path

    @classmethod
    def from_raw(cls, raw: dict, path: Path | None = None) -> "ActivityDef":
        if not isinstance(raw, dict):
            raise ValueError("o arquivo não contém um objeto JSON")
        key = raw.get("id")
        if not valid_name(key):
            raise ValueError(f"id inválido: {key!r} (use letras minúsculas, números e _)")
        fluxo = raw.get("fluxo", {})
        if not isinstance(fluxo, dict):
            raise ValueError("'fluxo' precisa ser um objeto")
        flow = {}
        for state, acts in fluxo.items():
            if not valid_name(state):
                raise ValueError(f"nome de tela inválido: {state!r}")
            flow[state] = [Action.parse(a) for a in acts]
        if not any(a.kind == "concluir" for acts in flow.values() for a in acts):
            raise ValueError("o fluxo precisa de pelo menos uma ação 'concluir'")
        cat = raw.get("categoria", "pve")
        if cat not in CATEGORIES:
            raise ValueError(f"categoria inválida: {cat}")
        kind = raw.get("tipo", "instancia")
        if kind not in ("instancia", "partida"):
            raise ValueError(f"tipo inválido: {kind}")
        strategy = raw.get("estrategia") or None
        if strategy is not None and not valid_name(strategy):
            raise ValueError(f"estratégia inválida: {strategy!r}")
        extra = {}
        for field_name, key_name in (("instance", "instancia"), ("difficulty", "dificuldade"), ("option", "opcao")):
            value = raw.get(key_name) or None
            if value is not None and not valid_name(value):
                raise ValueError(f"{key_name} inválida: {value!r}")
            extra[field_name] = value
        return cls(key=key, name=str(raw.get("nome", key))[:80], kind=kind,
                   category=cat, description=str(raw.get("descricao", ""))[:300], flow=flow,
                   start_states=tuple(raw.get("estados_iniciais", ["lobby"])),
                   forbidden=tuple(raw.get("proibido", [])), validated=bool(raw.get("validada_no_cliente")),
                   strategy=strategy, path=path, **extra)


def load_activities(folder: Path) -> tuple[list[ActivityDef], list[str]]:
    """Carrega todas as definições; devolve (válidas, erros legíveis)."""
    defs, errors = [], []
    for p in sorted(Path(folder).glob("*.json")):
        try:
            defs.append(ActivityDef.from_raw(json.loads(p.read_text(encoding="utf-8-sig")), p))
        except Exception as exc:
            errors.append(f"{p.name}: {exc}")
    return defs, errors


def slug(text: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return (re.sub(r"[^a-z0-9]+", "_", t).strip("_") or "atividade")[:56]


def unique_slug(base: str, taken) -> str:
    """``base`` ou ``base_2``, ``base_3``... sem colidir com nomes já usados."""
    name, n = base, 2
    while name in taken:
        name = f"{base[:52]}_{n}"
        n += 1
    return name


def instance_room_flow(selection: list[Action]) -> dict[str, list[Action]]:
    """Caminho das instâncias no DDClássico (informado pelo usuário em 2026-10-21): lobby -> Cais de Expedição
    -> Criar sala -> sala sem instância -> escolher a instância (opção, dificuldade, confirmar) -> sala -> Iniciar.

    A escolha é refeita a cada ida, mesmo que a sala ainda mostre a instância anterior: nunca inicia outra.
    """
    return {
        "lobby": [Action("clicar", "botao_cais", 1.5)],
        "cais_expedicao": [Action("clicar", "botao_criar_sala", 1.5)],
        "sala": [Action("clicar", "botao_escolher_instancia", 1.5, "sem_escolha"),
                 Action("clicar", "botao_iniciar", 2.0, "com_escolha")],
        "menu_instancias": selection + [Action("clicar_opcional", "botao_confirmar", 1.5)],
        SOLO_WARNING: [Action("confirmar_aviso", "botao_confirmar_aviso", 1.5)],
    }


INSTANCE_START_STATES = ("lobby", "cais_expedicao", "sala", "menu_instancias")


def activity_from_option(option_template: str, name: str, kind: str = "instancia",
                         category: str = "pve", key: str | None = None, strategy: str | None = None) -> ActivityDef:
    """Definição padrão para uma opção capturada na escolha da instância (na sala) ou no menu de partidas.

    Os botões genéricos (``botao_cais``, ``botao_criar_sala``, ``botao_partidas``, ``botao_iniciar``...)
    são os mesmos para todas as atividades e são capturados uma vez na Calibração.
    """
    if kind == "instancia":
        flow = instance_room_flow([Action("clicar", option_template, 1.0)])
        start = INSTANCE_START_STATES
    else:
        flow = {
            "lobby": [Action("clicar", "botao_partidas", 1.5)],
            "menu_partidas": [Action("clicar", option_template, 1.0),
                              Action("clicar_opcional", "botao_confirmar", 1.5)],
            "sala": [Action("clicar", "botao_iniciar", 2.0)],
        }
        start = ("lobby", "menu_partidas", "sala")
    flow.update({
        "carregando": [Action("aguardar", None, 1.0)],
        "batalha": [Action("combate")],
        "etapa_concluida": [Action("clicar_opcional", "botao_continuar", 1.5)],
        "recompensa": [Action("clicar_opcional", "carta_recompensa", 1.0),
                       Action("clicar_opcional", "botao_sair", 1.5)],
        "vitoria": [Action("concluir", "vitoria"), Action("clicar_opcional", "botao_sair", 1.5)],
        "derrota": [Action("concluir", "derrota"), Action("clicar_opcional", "botao_sair", 1.5)],
    })
    return ActivityDef(key=key or slug(f"{kind}_{name}"), name=name, kind=kind, category=category,
                       description="Criada a partir de uma opção capturada no menu do cliente.", flow=flow,
                       start_states=start, strategy=strategy if kind == "instancia" else None)


def instance_from_option(option_template: str, name: str, category: str = "pve") -> ActivityDef:
    return activity_from_option(option_template, name, "instancia", category)


# botões e marcadores que a Calibração pede para capturar (chave -> descrição)
COMMON_TEMPLATES = {
    "botao_cais": "Botão do Cais de Expedição (no lobby)",
    "botao_criar_sala": "Botão Criar sala (no Cais de Expedição)",
    "botao_escolher_instancia": "Botão da sala que abre a escolha da instância",
    "botao_partidas": "Botão que abre o menu de partidas/modalidades (no lobby)",
    "botao_confirmar": "Botão de confirmar/OK depois de escolher a instância ou a partida",
    "botao_confirmar_aviso": "Botão de confirmar no aviso de instância difícil (um jogador)",
    "botao_iniciar": "Botão Iniciar na sala de preparação",
    "botao_continuar": "Botão Continuar/Próxima etapa",
    "botao_sair": "Botão Sair/Voltar após o resultado",
    "botao_fechar": "Botão X para fechar avisos e janelas",
    "carta_recompensa": "Uma carta/recompensa clicável no fim",
    "turno": "Indicador de que é o seu turno",
    "marcador_eu": "Marcador sobre o seu personagem",
    "marcador_inimigo": "Marcador sobre um inimigo",
    "vento_esquerda": "Seta do vento para a esquerda",
    "vento_direita": "Seta do vento para a direita",
}


# --------------------------------------------------------------------------- execução
@dataclass
class ScreenState:
    state: str
    confidence: float
    frame: object = None
    note: str = ""


# estados especiais vindos do leitor (não dependem de modelo de imagem)
WINDOW_GONE = "janela_indisponivel"
NO_FOCUS = "janela_sem_foco"


class ScreenReader:
    def read(self) -> ScreenState:
        raise NotImplementedError


class Actor:
    """Ações normais do cliente.

    ``click`` devolve True (clicou), False (botão não encontrado) ou None (adiado: o mesmo
    botão acabou de ser clicado).
    """

    def click(self, template: str, frame) -> bool | None:
        raise NotImplementedError

    def press(self, key: str):
        raise NotImplementedError


class RunStatus(str, Enum):
    IDLE = "parado"
    RUNNING = "executando"
    PAUSED = "pausado"
    FINISHED = "concluido"
    FAILED = "falhou"


@dataclass
class RunLimits:
    runs: int = 1                 # 0 = contínuo
    max_defeats: int = 2
    max_minutes: float = 60.0     # tempo em pausa não conta
    unknown_state_timeout_s: float = 20.0
    stuck_timeout_s: float = 60.0  # mesma tela sem avançar
    max_clicks_per_visit: int = 4
    battle_timeout_s: float = 900.0
    confirm_reads: int = 2        # leituras iguais para aceitar uma tela nova
    click_retry_s: float = 5.0    # repete o último clique se a tela não mudou
    optional_wait_s: float = 1.5  # tempo procurando um botão opcional antes de pular
    missing_warn_s: float = 5.0   # avisa (uma vez por tela) que um botão obrigatório não aparece
    focus_grace_s: float = 5.0    # sem foco por mais que isso: pausa
    max_consecutive_errors: int = 3

    @classmethod
    def from_config(cls, config, runs: int) -> "RunLimits":
        g = config.get
        return cls(runs=runs, max_defeats=int(g("instances.max_defeats", 2)),
                   max_minutes=float(g("instances.max_minutes", 60)),
                   unknown_state_timeout_s=float(g("instances.unknown_state_timeout_s", 20)),
                   stuck_timeout_s=float(g("instances.action_timeout_s", 60)),
                   battle_timeout_s=float(g("instances.battle_timeout_s", 900)))


@dataclass
class RunCounters:
    completed: int = 0
    victories: int = 0
    defeats: int = 0
    unknown_results: int = 0
    battles: int = 0
    recoveries: int = 0
    started_at: float = field(default_factory=time.monotonic)
    clock: object = field(default=time.monotonic, repr=False)
    paused_total: float = 0.0

    def elapsed(self) -> float:
        return max(0.0, self.clock() - self.started_at - self.paused_total)

    def as_dict(self):
        return {"concluidas": self.completed, "vitorias": self.victories, "derrotas": self.defeats,
                "sem_resultado": self.unknown_results, "batalhas": self.battles, "recuperacoes": self.recoveries,
                "minutos": round(self.elapsed() / 60, 1)}


@dataclass
class RunEvent:
    kind: str      # etapa | resultado | aviso | erro | fim | progresso
    message: str
    data: dict = field(default_factory=dict)


class ActivityRunner:
    """Executa uma ``ActivityDef`` até cumprir os limites, receber parada ou falhar."""

    POLL_S = 0.4
    COMBAT_POLL_S = 0.15   # intervalo entre leituras no combate (CPU e responsividade)

    def __init__(self, definition: ActivityDef, reader: ScreenReader, actor: Actor, combat_step,
                 kill: KillSwitch, config, limits: RunLimits, on_event=None, state_threshold: float = 0.8,
                 clock=time.monotonic, on_battle_start=None, on_failure_frame=None, on_activity_start=None,
                 selection_labels: dict[str, str] | None = None):
        self.d = definition
        self.selection_labels = selection_labels or {}  # modelo de seleção -> nome legível (opção, dificuldade)
        self.reader = reader
        self.actor = actor
        self.combat_step = combat_step  # callable(allow_fire=True) -> None; um passo do combate
        self.kill = kill
        self.config = config
        self.limits = limits
        self.on_event = on_event or (lambda e: None)
        self.state_threshold = state_threshold
        self.clock = clock
        self.on_battle_start = on_battle_start or (lambda: None)
        self.on_activity_start = on_activity_start or (lambda: None)  # nova execução (antes da 1ª batalha)
        self.on_failure_frame = on_failure_frame  # callable(frame, motivo): guarda a tela para diagnóstico
        self.counters = RunCounters(started_at=clock(), clock=clock)
        self.status = RunStatus.IDLE
        self.current_state = "desconhecido"
        self.reason = ""
        self.pause_event = threading.Event()
        self._stop_requested = threading.Event()
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._resume_pending = False
        self._paused_since: float | None = None
        self._last_frame = None
        self._errors = 0
        # tela confirmada e candidata
        self._stable = "desconhecido"
        self._candidate: str | None = None
        self._candidate_n = 0
        # visita à tela atual
        self._visit_started = clock()
        self._visit_clicks = 0
        self._visit_done_actions = 0
        self._last_click_idx: int | None = None
        self._last_click_at = 0.0
        self._action_first_try: float | None = None
        self._missing_warned = False
        self._unknown_since: float | None = None
        self._nofocus_since: float | None = None
        self._recovery_attempts: dict[tuple, int] = {}
        # execução atual (uma ida e volta da atividade)
        self._in_activity = False
        self._pending_result: str | None = None
        self._chosen = False  # a opção (e a dificuldade) desta atividade já foram clicadas nesta ida
        self.blocked: str | None = None  # pausa que pede uma decisão do usuário (ex.: SOLO_WARNING)

    # ------------------------------------------------------------------ util
    def _emit(self, kind, message, **data):
        (log.warning if kind in ("aviso", "erro") else log.info)(message)
        self.on_event(RunEvent(kind, message, data))

    @property
    def unknown_screen(self) -> bool:
        return self._unknown_since is not None

    def forbidden(self) -> set[str]:
        extra = self.config.get("automation.forbidden_templates", []) or []
        allowed = set(self.config.get("automation.allowed_paid_templates", []) or [])
        return (set(DEFAULT_FORBIDDEN) | set(self.d.forbidden) | set(extra)) - allowed

    def check_allowed(self) -> tuple[bool, str]:
        if not self.config.get("automation.server_rules_confirmed", False):
            return False, "automação não autorizada: confirme as regras do servidor em Configurações"
        if not self.d.auto_allowed:
            return False, (f"'{self.d.name}' é da categoria {CATEGORIES.get(self.d.category)}: "
                           "o modo automático só roda atividades PvE/solo")
        for state, actions in self.d.flow.items():
            for a in actions:
                if a.kind in CLICKS and a.target in self.forbidden():
                    return False, f"o fluxo clica em '{a.target}', que está na lista de proibidos"
        return True, ""

    def cancel_reason(self) -> str | None:
        """Para o ``InputController``: interrompe ações em andamento ao pausar/parar."""
        if self._stop_requested.is_set():
            return "parada solicitada"
        if self.pause_event.is_set():
            return "pausa solicitada"
        return None

    def request_stop(self, reason="parada solicitada"):
        with self._lock:
            self.reason = reason
            self._stop_requested.set()

    def pause(self, reason="pausado pelo usuário"):
        with self._lock:
            if self.status != RunStatus.RUNNING:
                return
            self.status = RunStatus.PAUSED
            self.reason = reason
            self.pause_event.set()
            self._paused_since = self.clock()
        self._emit("aviso", f"pausado: {reason}")

    def resume(self):
        with self._lock:
            if self.status != RunStatus.PAUSED:
                return
            self.status = RunStatus.RUNNING
            self.blocked = None
            self._resume_pending = True  # o reset da visita é feito pela thread da rotina
            if self._paused_since is not None:
                self.counters.paused_total += self.clock() - self._paused_since
                self._paused_since = None
            self.pause_event.clear()
        self._emit("etapa", "retomado")

    def _sleep(self, seconds):
        end = self.clock() + seconds
        while True:
            self.kill.check()
            if self._stop_requested.is_set():
                return
            left = end - self.clock()
            if left <= 0:
                return
            self.kill.sleep(min(0.1, left))

    def _reset_visit(self, now=None):
        self._visit_started = self.clock() if now is None else now
        self._visit_clicks = 0
        self._visit_done_actions = 0
        self._last_click_idx = None
        self._action_first_try = None
        self._missing_warned = False

    # -------------------------------------------------------------- limites
    def _limits_reached(self) -> str | None:
        lim, c = self.limits, self.counters
        if lim.runs and c.completed >= lim.runs:
            return f"quantidade configurada concluída ({c.completed}/{lim.runs})"
        if lim.max_defeats and c.defeats >= lim.max_defeats:
            return f"limite de derrotas atingido ({c.defeats})"
        if lim.max_minutes and c.elapsed() / 60 >= lim.max_minutes:
            return f"tempo máximo atingido ({lim.max_minutes:g} min)"
        return None

    def _finish(self, why) -> bool:
        with self._lock:
            self.status = RunStatus.FINISHED
            self.reason = why
        self._emit("fim", f"concluído: {why}", **self.counters.as_dict())
        return False

    # ---------------------------------------------------------------- passo
    def step(self) -> bool:
        """Uma iteração. Devolve False quando a rotina terminou."""
        self.kill.check()
        if self._stop_requested.is_set():
            with self._lock:
                self.status = RunStatus.IDLE
            self._emit("fim", f"parado: {self.reason}")
            return False
        if self.pause_event.is_set():
            self._sleep(0.2)
            return True
        if self._resume_pending:
            with self._lock:
                self._resume_pending = False
            self._reset_visit()
            self._unknown_since = self._nofocus_since = None
            self._recovery_attempts.clear()
            self._candidate, self._candidate_n = None, 0
        now = self.clock()
        screen = self.reader.read()
        self._last_frame = screen.frame
        raw = screen.state if (screen.confidence >= self.state_threshold or screen.state in (WINDOW_GONE, NO_FOCUS)) \
            else "desconhecido"

        # janela: nada de cliques numa tela que o bot não está vendo
        if raw == WINDOW_GONE:
            return self._pause_for_user(screen.note or "a janela do jogo está minimizada ou foi fechada")
        if raw == NO_FOCUS:
            self._nofocus_since = self._nofocus_since or now
            if now - self._nofocus_since > self.limits.focus_grace_s:
                return self._pause_for_user("a janela do jogo não está na frente; deixe o jogo em primeiro plano "
                                            "e clique em Retomar")
            self._sleep(self.POLL_S)
            return True
        self._nofocus_since = None

        state = self._confirm(raw)
        if state is None:
            # leitura ainda não confirmada: no combate só observa, fora dele espera
            if self._stable == "batalha":
                self.combat_step(allow_fire=False)
                self._sleep(self.COMBAT_POLL_S)
            else:
                self._sleep(min(self.POLL_S, 0.2))
            return True
        if state == "desconectado":
            return self._fail("o jogo mostra a tela de desconexão")
        if state == "desconhecido":
            return self._handle_unknown(now, screen)
        self._unknown_since = None
        if state != self.current_state:
            if not self._enter_state(state, now):
                return False
        elif not self._in_activity:
            done = self._limits_reached()
            if done and state in self.d.start_states:
                return self._finish(done)
        actions = self.d.flow.get(state)
        if actions is None:
            # tela reconhecida, mas fora do fluxo desta atividade: não age, tenta recuperar
            if now - self._visit_started > self.limits.stuck_timeout_s / 2:
                return self._recover(f"tela '{state}' não faz parte do fluxo de '{self.d.name}'", screen)
            self._sleep(self.POLL_S)
            return True
        return self._run_actions(state, actions, screen, now)

    def _confirm(self, raw: str) -> str | None:
        """Tela confirmada (lida igual ``confirm_reads`` vezes seguidas) ou None se ainda incerta."""
        if raw == self._stable:
            self._candidate, self._candidate_n = None, 0
            return raw
        if raw == self._candidate:
            self._candidate_n += 1
        else:
            self._candidate, self._candidate_n = raw, 1
        if self._candidate_n >= self.limits.confirm_reads:
            self._stable = raw
            self._candidate, self._candidate_n = None, 0
            return raw
        return None

    def _enter_state(self, state, now) -> bool:
        prev = self.current_state
        self.current_state = state
        self._reset_visit(now)
        self._recovery_attempts.clear()  # a tela avançou: tentativas anteriores não contam mais
        self._emit("etapa", f"tela: {state}", state=state, previous=prev)
        if state == "batalha":
            if not self._in_activity:
                self._in_activity = True
                self._pending_result = None
                self.on_activity_start()
            self.counters.battles += 1
            self.on_battle_start()
        elif state in self.d.start_states and self._in_activity:
            self._close_activity()
        if state in ("lobby", "cais_expedicao"):
            self._chosen = False  # saiu da sala: a próxima sala começa sem instância escolhida
        if state in self.d.start_states and not self._in_activity:
            done = self._limits_reached()
            if done:
                return self._finish(done)
        return True

    def _close_activity(self):
        """Volta a uma tela inicial: a execução terminou. Conta o resultado visto (ou a falta dele)."""
        result = self._pending_result
        self._in_activity = False
        self._pending_result = None
        self._chosen = False  # a próxima ida escolhe de novo (a sala pode ter ficado com outra instância)
        self.counters.completed += 1
        if result == "vitoria":
            self.counters.victories += 1
        elif result == "derrota":
            self.counters.defeats += 1
        else:
            self.counters.unknown_results += 1
            self._emit("aviso", "a atividade terminou sem uma tela de vitória/derrota reconhecida; "
                       "capture os modelos de resultado em Calibração")
        label = {"vitoria": "vitória", "derrota": "derrota"}.get(result, "sem resultado reconhecido")
        total = f"/{self.limits.runs}" if self.limits.runs else ""
        self._emit("resultado", f"{self.d.name}: {label} ({self.counters.completed}{total})",
                   result=result, **self.counters.as_dict())

    def _run_actions(self, state, actions, screen, now) -> bool:
        if any(a.kind == "combate" for a in actions):
            if now - self._visit_started > self.limits.battle_timeout_s:
                return self._fail("a batalha excedeu o tempo máximo")
            self.combat_step(allow_fire=True)
            self._sleep(self.COMBAT_POLL_S)
            return True
        if self._visit_done_actions >= len(actions):
            return self._wait_for_change(state, actions, screen, now)
        idx = self._visit_done_actions
        a = actions[idx]
        if a.when is not None and (a.when == "com_escolha") != self._chosen:
            self._visit_done_actions += 1  # condição não vale agora: a ação não existe nesta visita
            return True
        if a.kind == "concluir":
            if self._in_activity:
                # a derrota prevalece se a mesma execução mostrar os dois (várias etapas)
                if self._pending_result != "derrota":
                    self._pending_result = a.target
            self._visit_done_actions += 1
            return True
        if a.kind == "aguardar":
            self._sleep(a.seconds)
            self._visit_done_actions += 1
            return True
        if a.kind == "tecla":
            self.actor.press(a.target)
            self._visit_done_actions += 1
            self._sleep(a.seconds)
            return True
        if a.kind == "confirmar_aviso" and not self.config.get("instances.confirm_solo_warning", False):
            # decisão do usuário, não do bot: pausa na mesma tela; com a permissão, Retomar continua daqui
            self.blocked = SOLO_WARNING
            return self._pause_for_user(
                "o jogo avisa que esta instância é difícil para um jogador. Para continuar mesmo assim, clique em "
                "Confirmar o aviso e continuar (ou marque a permissão em Configurações e clique em Retomar); para "
                "desistir, clique em Parar")
        # clicar / clicar_opcional / confirmar_aviso (com permissão)
        if a.target in self.forbidden():
            return self._fail(f"clique em '{a.target}' bloqueado (proibido nas configurações)")
        if self._visit_clicks >= self.limits.max_clicks_per_visit:
            return self._recover(f"muitos cliques na tela '{state}' sem avançar", screen)
        result = self.actor.click(a.target, screen.frame)
        if result is True:
            self._visit_clicks += 1
            self._last_click_idx, self._last_click_at = idx, now
            self._action_first_try = None
            data = {"state": state}
            picks = [i for i, x in enumerate(actions) if x.kind == "clicar" and is_selection(x.target)]
            if picks and idx == picks[-1]:
                data["selecao_feita"] = a.target  # a opção (e a dificuldade) desta atividade estavam no menu
                self._chosen = True
            self._emit("etapa", f"clicou em {a.target}", **data)
            self._sleep(a.seconds)
            self._visit_done_actions += 1
            return True
        if result is None:  # adiado: o mesmo botão acabou de ser clicado
            self._sleep(0.3)
            return True
        self._action_first_try = self._action_first_try or now
        if a.kind == "clicar_opcional":
            if now - self._action_first_try >= self.limits.optional_wait_s:
                self._action_first_try = None
                self._visit_done_actions += 1
            else:
                self._sleep(0.3)
            return True
        give_up = self.limits.stuck_timeout_s / 2
        if now - self._visit_started > give_up:
            if is_selection(a.target):
                return self._selection_missing(a.target)
            return self._recover(f"botão '{a.target}' não encontrado na tela '{state}'", screen)
        if not self._missing_warned and now - self._action_first_try >= self.limits.missing_warn_s:
            # não deixa o usuário olhando uma tela parada sem saber o motivo
            self._missing_warned = True
            left = max(1, round(give_up - (now - self._visit_started)))
            self._emit("aviso", f"procurando {a.target} na tela {state}; se não aparecer em {left} s, o bot pausa")
        self._sleep(self.POLL_S)
        return True

    def _wait_for_change(self, state, actions, screen, now) -> bool:
        """Todas as ações da tela foram feitas e ela não mudou."""
        if (self._last_click_idx is not None and now - self._last_click_at >= self.limits.click_retry_s
                and self._visit_clicks < self.limits.max_clicks_per_visit):
            # o jogo pode ter ignorado o clique (atraso): repete a partir dele
            self._visit_done_actions = self._last_click_idx
            return True
        if self._last_click_idx is not None and self._visit_clicks >= self.limits.max_clicks_per_visit \
                and now - self._last_click_at >= self.limits.click_retry_s:
            return self._recover(f"muitos cliques na tela '{state}' sem avançar", screen)
        if now - self._visit_started > self.limits.stuck_timeout_s:
            return self._recover(f"tela '{state}' não avançou", screen)
        self._sleep(self.POLL_S)
        return True

    # ---------------------------------------------------- falhas e recuperação
    def _handle_unknown(self, now, screen) -> bool:
        if self._unknown_since is None:
            self._unknown_since = now
            detail = f": {screen.note}" if screen.note else f" (confiança {screen.confidence:.2f})"
            self._emit("aviso", f"tela não reconhecida{detail}. Se for uma tela do jogo, capture-a em "
                       "Calibração > Modelos; a imagem fica em dados\\capturas se o bot pausar")
        elapsed = now - self._unknown_since
        if self.current_state == "batalha" and elapsed < self.limits.unknown_state_timeout_s:
            # explosões e animações atrapalham a leitura: segue observando, sem disparar
            self.combat_step(allow_fire=False)
            self._sleep(self.COMBAT_POLL_S)
            return True
        if elapsed > self.limits.unknown_state_timeout_s:
            return self._recover("tela desconhecida por tempo demais", screen,
                                 detail=f" ({screen.note})" if screen.note else "")
        self._sleep(self.POLL_S)
        return True

    def _recover(self, why, screen, detail: str = "") -> bool:
        """Recuperação só com evidência: fecha um aviso se o botão de fechar for reconhecido.

        Sem botão reconhecido, ou na segunda vez pelo mesmo motivo na mesma tela, pausa e
        pede intervenção. Nunca envia teclas às cegas (ESC na batalha pode sair dela).
        """
        key = (self.current_state, why)  # sem ``detail``: as notas mudam a cada leitura
        if self._recovery_attempts.get(key, 0) >= 1:
            return self._pause_for_user(why + detail)
        self._recovery_attempts[key] = self._recovery_attempts.get(key, 0) + 1
        if self.actor.click("botao_fechar", screen.frame) is True:
            self.counters.recoveries += 1
            self._emit("aviso", f"{why}; aviso fechado, tentando continuar")
            self._sleep(1.5)
            self._reset_visit()
            self._unknown_since = None
            return True
        return self._pause_for_user(why + detail)

    def _selection_missing(self, template: str) -> bool:
        """A opção (ou a dificuldade) desta atividade não está no menu: pausa, nunca escolhe outra."""
        label = self.selection_labels.get(template) or (
            f"a dificuldade {template.split('_', 1)[-1].replace('_', ' ')}" if template.startswith("dificuldade_")
            else f"a opção {self.d.name}")
        refusal = getattr(self.actor, "last_refusal", "") or ""
        why = (f"{label} não foi encontrada no menu do jogo para {self.d.name}"
               + (f" ({refusal})" if refusal else "")
               + ": o bot não escolhe outra atividade no lugar. Confira se ela existe no seu cliente "
                 "(nível, evento, página do menu) e clique em Retomar, ou escolha outra atividade")
        self._emit("aviso", f"{label}: não encontrada no menu", selecao_ausente=template, motivo=why)
        return self._pause_for_user(why)

    def _save_failure(self, why):
        if self.on_failure_frame is not None and self._last_frame is not None:
            try:
                self.on_failure_frame(self._last_frame, why)
            except Exception:
                log.exception("falha ao salvar captura de diagnóstico")

    def _pause_for_user(self, why) -> bool:
        self._save_failure(why)
        with self._lock:
            if self.status == RunStatus.RUNNING:
                self.status = RunStatus.PAUSED
                self._paused_since = self.clock()
            self.reason = why
            self.pause_event.set()
        self._emit("erro", f"intervenção necessária: {why}")
        return True

    def _fail(self, why) -> bool:
        self._save_failure(why)
        with self._lock:
            self.status = RunStatus.FAILED
            self.reason = why
        self._emit("erro", f"rotina interrompida: {why}")
        return False

    # ------------------------------------------------------------------ laço
    def run_once(self) -> bool:
        """Um passo protegido: erros viram pausa/aviso em vez de derrubar a rotina."""
        try:
            ok = self.step()
            self._errors = 0
            return ok
        except Aborted as exc:
            if self.kill.triggered:
                with self._lock:
                    self.status = RunStatus.IDLE
                    self.reason = f"parada de emergência: {exc}"
                self._emit("fim", f"parada de emergência: {exc}")
                return False
            if isinstance(exc, Cancelled):
                return True  # pausa/parada pedida no meio de uma ação: o próximo passo trata
            if isinstance(exc, (FocusLost, InputBlocked, NeedsAttention)):
                return self._pause_for_user(str(exc))
            self._emit("aviso", f"ação cancelada: {exc}")
            return True
        except Exception as exc:
            log.exception("erro na rotina")
            self._errors += 1
            if self._errors >= self.limits.max_consecutive_errors:
                self._errors = 0
                return self._pause_for_user(f"erros repetidos ({exc})")
            self._emit("aviso", f"erro na rotina ({exc}); tentando de novo")
            try:
                self._sleep(1.0)
            except Aborted:
                pass
            return True

    def run(self):
        ok, why = self.check_allowed()
        if not ok:
            with self._lock:
                self.status = RunStatus.FAILED
                self.reason = why
            self._emit("erro", why)
            return
        with self._lock:
            self.status = RunStatus.RUNNING
        self.counters = RunCounters(started_at=self.clock(), clock=self.clock)
        self._chosen = False
        how = "repetição contínua" if not self.limits.runs else (
            "uma vez" if self.limits.runs == 1 else f"{self.limits.runs} vezes")
        self._emit("etapa", f"iniciando {self.d.name} ({how})")
        try:
            while self.run_once():
                pass
        finally:
            # libera a captura (MSS) aberta por esta thread
            for owner in (self.reader, getattr(self.reader, "source", None)):
                release = getattr(owner, "release_thread", None)
                if callable(release):
                    release()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self.run, daemon=True, name=f"atividade-{self.d.key}")
        self._thread.start()

    def join(self, timeout=None):
        if self._thread:
            self._thread.join(timeout)

    @property
    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())
