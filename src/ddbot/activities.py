"""Atividades automáticas (partidas e instâncias) como máquina de estados reativa.

Cada iteração identifica a tela atual por evidência visual (modelos ``estado_*``) e
executa a ação configurada para essa tela. Nada avança só por temporizador: as
esperas servem apenas para dar tempo à tela de mudar, e a mudança é conferida.

Definições ficam em ``instancias/*.json`` (pasta do usuário) e são criadas a partir
das opções que o próprio cliente mostra (Calibração > Opções do menu). Não existe
lista fixa de instâncias no código.

Travas:
- exige autorização explícita (``automation.server_rules_confirmed``);
- categoria ``pvp`` (contra jogadores) não roda sozinha;
- nunca clica em modelos proibidos (compra, moeda premium etc.);
- cliques repetidos na mesma tela são limitados; tela parada ou desconhecida por
  tempo demais pausa a rotina e informa o motivo.
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

from .automation.safety import Aborted, KillSwitch

log = logging.getLogger(__name__)

TERMINAL_RESULTS = ("vitoria", "derrota")
CATEGORIES = {"pve": "PvE / contra o computador", "solo": "Solo", "matchmaking": "Fila (outros jogadores)",
              "pvp": "PvP contra jogadores"}
AUTO_CATEGORIES = ("pve", "solo")
# modelos que nunca são clicados, além dos listados em cada definição e na configuração
DEFAULT_FORBIDDEN = ("botao_comprar", "botao_loja", "botao_recarregar", "botao_cupons", "botao_premium",
                     "botao_ranqueada")


@dataclass
class Action:
    kind: str                 # clicar | clicar_opcional | tecla | aguardar | combate | concluir
    target: str | None = None  # modelo (clicar), tecla, resultado (concluir)
    seconds: float = 0.0

    @classmethod
    def parse(cls, raw: dict) -> "Action":
        if "clicar" in raw:
            return cls("clicar", raw["clicar"], float(raw.get("espera", 1.0)))
        if "clicar_opcional" in raw:
            return cls("clicar_opcional", raw["clicar_opcional"], float(raw.get("espera", 0.5)))
        if "tecla" in raw:
            return cls("tecla", raw["tecla"], float(raw.get("espera", 0.5)))
        if "aguardar" in raw:
            return cls("aguardar", None, float(raw["aguardar"]))
        if raw.get("combate"):
            return cls("combate")
        if "concluir" in raw:
            if raw["concluir"] not in TERMINAL_RESULTS:
                raise ValueError(f"resultado inválido: {raw['concluir']}")
            return cls("concluir", raw["concluir"])
        raise ValueError(f"ação desconhecida: {raw}")

    def to_raw(self) -> dict:
        if self.kind in ("clicar", "clicar_opcional", "tecla"):
            return {self.kind: self.target, "espera": self.seconds}
        if self.kind == "aguardar":
            return {"aguardar": self.seconds}
        if self.kind == "combate":
            return {"combate": True}
        return {"concluir": self.target}


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
    path: Path | None = None

    @property
    def auto_allowed(self) -> bool:
        return self.category in AUTO_CATEGORIES

    def templates_needed(self) -> list[str]:
        out = [f"estado_{s}" for s in self.flow]
        for actions in self.flow.values():
            out += [a.target for a in actions if a.kind in ("clicar", "clicar_opcional") and a.target]
        return sorted(set(out))

    def to_raw(self) -> dict:
        return {"id": self.key, "nome": self.name, "tipo": self.kind, "categoria": self.category,
                "descricao": self.description, "validada_no_cliente": self.validated,
                "estados_iniciais": list(self.start_states), "proibido": list(self.forbidden),
                "fluxo": {s: [a.to_raw() for a in acts] for s, acts in self.flow.items()}}

    def save(self, folder: Path) -> Path:
        path = Path(folder) / f"{self.key}.json"
        path.write_text(json.dumps(self.to_raw(), indent=2, ensure_ascii=False), encoding="utf-8")
        self.path = path
        return path

    @classmethod
    def from_raw(cls, raw: dict, path: Path | None = None) -> "ActivityDef":
        flow = {state: [Action.parse(a) for a in acts] for state, acts in raw.get("fluxo", {}).items()}
        if not any(a.kind == "concluir" for acts in flow.values() for a in acts):
            raise ValueError("o fluxo precisa de pelo menos uma ação 'concluir'")
        cat = raw.get("categoria", "pve")
        if cat not in CATEGORIES:
            raise ValueError(f"categoria inválida: {cat}")
        return cls(key=raw["id"], name=raw.get("nome", raw["id"]), kind=raw.get("tipo", "instancia"),
                   category=cat, description=raw.get("descricao", ""), flow=flow,
                   start_states=tuple(raw.get("estados_iniciais", ["lobby"])),
                   forbidden=tuple(raw.get("proibido", [])), validated=bool(raw.get("validada_no_cliente")),
                   path=path)


def load_activities(folder: Path) -> tuple[list[ActivityDef], list[str]]:
    """Carrega todas as definições; devolve (válidas, erros legíveis)."""
    defs, errors = [], []
    for p in sorted(Path(folder).glob("*.json")):
        try:
            defs.append(ActivityDef.from_raw(json.loads(p.read_text(encoding="utf-8")), p))
        except Exception as exc:
            errors.append(f"{p.name}: {exc}")
    return defs, errors


def slug(text: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_") or "atividade"


def activity_from_option(option_template: str, name: str, kind: str = "instancia",
                         category: str = "pve") -> ActivityDef:
    """Definição padrão para uma opção capturada no menu de instâncias ou de partidas.

    Os botões genéricos (``botao_instancias``, ``botao_partidas``, ``botao_iniciar``...)
    são os mesmos para todas as atividades e são capturados uma vez na Calibração.
    """
    menu, entry = (("menu_instancias", "botao_instancias") if kind == "instancia"
                   else ("menu_partidas", "botao_partidas"))
    flow = {
        "lobby": [Action("clicar", entry, 1.5)],
        menu: [Action("clicar", option_template, 1.0), Action("clicar_opcional", "botao_confirmar", 1.5)],
        "sala": [Action("clicar", "botao_iniciar", 2.0)],
        "carregando": [Action("aguardar", None, 1.0)],
        "batalha": [Action("combate")],
        "etapa_concluida": [Action("clicar_opcional", "botao_continuar", 1.5)],
        "recompensa": [Action("clicar_opcional", "carta_recompensa", 1.0),
                       Action("clicar_opcional", "botao_sair", 1.5)],
        "vitoria": [Action("concluir", "vitoria"), Action("clicar_opcional", "botao_sair", 1.5)],
        "derrota": [Action("concluir", "derrota"), Action("clicar_opcional", "botao_sair", 1.5)],
    }
    return ActivityDef(key=slug(f"{kind}_{name}"), name=name, kind=kind, category=category,
                       description="Criada a partir de uma opção capturada no menu do cliente.", flow=flow,
                       start_states=("lobby", menu, "sala"))


def instance_from_option(option_template: str, name: str, category: str = "pve") -> ActivityDef:
    return activity_from_option(option_template, name, "instancia", category)


# botões e marcadores que a Calibração pede para capturar (chave -> descrição)
COMMON_TEMPLATES = {
    "botao_instancias": "Botão que abre o menu de instâncias (no lobby)",
    "botao_partidas": "Botão que abre o menu de partidas/modalidades (no lobby)",
    "botao_confirmar": "Botão de confirmar/entrar após escolher a opção",
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


class ScreenReader:
    def read(self) -> ScreenState:
        raise NotImplementedError


class Actor:
    """Ações normais do cliente. ``click`` devolve True se o modelo foi encontrado e clicado."""

    def click(self, template: str, frame) -> bool:
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
    max_minutes: float = 60.0
    unknown_state_timeout_s: float = 20.0
    stuck_timeout_s: float = 60.0  # mesma tela sem avançar
    max_clicks_per_visit: int = 4
    battle_timeout_s: float = 900.0

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
    battles: int = 0
    recoveries: int = 0
    started_at: float = field(default_factory=time.monotonic)
    clock: object = field(default=time.monotonic, repr=False)

    def as_dict(self):
        return {"concluidas": self.completed, "vitorias": self.victories, "derrotas": self.defeats,
                "batalhas": self.battles, "recuperacoes": self.recoveries,
                "minutos": round((self.clock() - self.started_at) / 60, 1)}


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
                 clock=time.monotonic, on_battle_start=None, on_failure_frame=None):
        self.d = definition
        self.reader = reader
        self.actor = actor
        self.combat_step = combat_step  # callable() -> None; um passo do motor de combate
        self.kill = kill
        self.config = config
        self.limits = limits
        self.on_event = on_event or (lambda e: None)
        self.state_threshold = state_threshold
        self.clock = clock
        self.on_battle_start = on_battle_start or (lambda: None)
        self.on_failure_frame = on_failure_frame  # callable(frame, motivo): guarda a tela para diagnóstico
        self._last_frame = None
        self.counters = RunCounters(started_at=clock(), clock=clock)
        self.status = RunStatus.IDLE
        self.current_state = "desconhecido"
        self.reason = ""
        self.pause_event = threading.Event()
        self._stop_requested = threading.Event()
        self._thread: threading.Thread | None = None
        # controle de visita à tela atual
        self._visit_state: str | None = None
        self._visit_started = clock()
        self._visit_clicks = 0
        self._visit_done_actions = 0
        self._unknown_since: float | None = None
        self._result_counted_this_run = False
        self._in_activity = False
        self._recovery_attempts: dict[tuple, int] = {}

    # ------------------------------------------------------------------ util
    def _emit(self, kind, message, **data):
        (log.warning if kind in ("aviso", "erro") else log.info)(message)
        self.on_event(RunEvent(kind, message, data))

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
                if a.kind in ("clicar", "clicar_opcional") and a.target in self.forbidden():
                    return False, f"o fluxo clica em '{a.target}', que está na lista de proibidos"
        return True, ""

    def request_stop(self, reason="parada solicitada"):
        self.reason = reason
        self._stop_requested.set()

    def pause(self, reason="pausado pelo usuário"):
        if self.status == RunStatus.RUNNING:
            self.status = RunStatus.PAUSED
            self.pause_event.set()
            self.reason = reason
            self._emit("aviso", f"pausado: {reason}")

    def resume(self):
        if self.status == RunStatus.PAUSED:
            self.pause_event.clear()
            self.status = RunStatus.RUNNING
            self._reset_visit(self.current_state)
            self._unknown_since = None
            self._recovery_attempts.clear()
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

    def _reset_visit(self, state):
        self._visit_state = state
        self._visit_started = self.clock()
        self._visit_clicks = 0
        self._visit_done_actions = 0

    # -------------------------------------------------------------- limites
    def _limits_reached(self) -> str | None:
        lim, c = self.limits, self.counters
        if lim.runs and c.completed >= lim.runs:
            return f"quantidade configurada concluída ({c.completed}/{lim.runs})"
        if lim.max_defeats and c.defeats >= lim.max_defeats:
            return f"limite de derrotas atingido ({c.defeats})"
        if lim.max_minutes and (self.clock() - c.started_at) / 60 >= lim.max_minutes:
            return f"tempo máximo atingido ({lim.max_minutes:.0f} min)"
        return None

    # ---------------------------------------------------------------- passo
    def step(self) -> bool:
        """Uma iteração. Devolve False quando a rotina terminou."""
        self.kill.check()
        if self._stop_requested.is_set():
            self.status = RunStatus.IDLE
            self._emit("fim", f"parado: {self.reason}")
            return False
        if self.pause_event.is_set():
            self._sleep(0.2)
            return True
        now = self.clock()
        screen = self.reader.read()
        self._last_frame = screen.frame
        state = screen.state if screen.confidence >= self.state_threshold else "desconhecido"
        if state == "desconectado":
            return self._fail("o cliente mostra desconexão: reconecte manualmente e reinicie")
        if state == "desconhecido":
            return self._handle_unknown(now, screen)
        self._unknown_since = None
        if state != self._visit_state:
            prev = self._visit_state
            self._reset_visit(state)
            self.current_state = state
            self._emit("etapa", f"tela: {state}", state=state, previous=prev)
            if state in self.d.start_states and self._in_activity and self._result_counted_this_run:
                self._in_activity = False
                self._result_counted_this_run = False
            if state == "batalha":
                self._in_activity = True
                self.counters.battles += 1
                self.on_battle_start()
            done = self._limits_reached()
            if done and state in self.d.start_states and not self._in_activity:
                self.status = RunStatus.FINISHED
                self._emit("fim", f"concluído: {done}", **self.counters.as_dict())
                return False
        actions = self.d.flow.get(state)
        if actions is None:
            # tela reconhecida, mas fora do fluxo desta atividade: não age, tenta recuperar
            if now - self._visit_started > self.limits.stuck_timeout_s / 2:
                return self._recover(f"tela '{state}' não faz parte do fluxo de '{self.d.name}'", screen)
            self._sleep(self.POLL_S)
            return True
        return self._run_actions(state, actions, screen, now)

    def _run_actions(self, state, actions, screen, now) -> bool:
        if any(a.kind == "combate" for a in actions):
            if now - self._visit_started > self.limits.battle_timeout_s:
                return self._fail("batalha excedeu o tempo máximo")
            self.combat_step()
            self._sleep(self.COMBAT_POLL_S)
            return True
        if self._visit_done_actions >= len(actions):
            # já executou tudo nesta tela; espera ela mudar
            if now - self._visit_started > self.limits.stuck_timeout_s:
                return self._recover(f"tela '{state}' não avançou", screen)
            self._sleep(self.POLL_S)
            return True
        a = actions[self._visit_done_actions]
        if a.kind == "concluir":
            if not self._result_counted_this_run:
                self._count_result(a.target)
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
        # clicar / clicar_opcional
        if a.target in self.forbidden():
            return self._fail(f"clique em '{a.target}' bloqueado (proibido nas configurações)")
        if self._visit_clicks >= self.limits.max_clicks_per_visit:
            return self._recover(f"muitos cliques na tela '{state}' sem avançar", screen)
        clicked = self.actor.click(a.target, screen.frame)
        if clicked:
            self._visit_clicks += 1
            self._emit("etapa", f"clicou em {a.target}", state=state)
            self._sleep(a.seconds)
            # só avança para a próxima ação se a tela continuou a mesma; se mudou, a
            # próxima leitura começa uma nova visita
            self._visit_done_actions += 1
        elif a.kind == "clicar_opcional":
            self._visit_done_actions += 1
        else:
            if now - self._visit_started > self.limits.stuck_timeout_s / 2:
                return self._recover(f"botão '{a.target}' não encontrado na tela '{state}'", screen)
            self._sleep(self.POLL_S)
        return True

    def _count_result(self, result):
        self._result_counted_this_run = True
        self.counters.completed += 1
        if result == "vitoria":
            self.counters.victories += 1
        else:
            self.counters.defeats += 1
        self._emit("resultado", f"{self.d.name}: {result} ({self.counters.completed}"
                   f"{'/' + str(self.limits.runs) if self.limits.runs else ''})", result=result,
                   **self.counters.as_dict())

    # ---------------------------------------------------- falhas e recuperação
    def _handle_unknown(self, now, screen) -> bool:
        if self._unknown_since is None:
            self._unknown_since = now
            self._emit("aviso", f"tela não reconhecida (confiança {screen.confidence:.2f})")
        elapsed = now - self._unknown_since
        if self._visit_state == "batalha" and elapsed < self.limits.unknown_state_timeout_s:
            # animações e explosões atrapalham a leitura no combate; continua tentando
            self.combat_step()
            self._sleep(self.COMBAT_POLL_S)
            return True
        if elapsed > self.limits.unknown_state_timeout_s:
            return self._recover("tela desconhecida por tempo demais", screen, pause_after=True)
        self._sleep(self.POLL_S)
        return True

    def _recover(self, why, screen, pause_after=False) -> bool:
        """Recuperação pelos meios normais: fechar avisos e ESC. Na segunda vez, pausa."""
        key = (self._visit_state, why)
        attempts = self._recovery_attempts.get(key, 0)
        if attempts >= 1:
            self._recovery_attempts.pop(key, None)
            return self._pause_for_user(why)
        self._recovery_attempts[key] = attempts + 1
        self.counters.recoveries += 1
        self._emit("aviso", f"{why}; tentando recuperar")
        if not self.actor.click("botao_fechar", screen.frame):
            self.actor.press(self.config.get("automation.keys.close", "esc") or "esc")
        self._sleep(1.5)
        self._reset_visit(self._visit_state)
        self._unknown_since = None
        if pause_after and attempts:
            return self._pause_for_user(why)
        return True

    def _save_failure(self, why):
        if self.on_failure_frame is not None and self._last_frame is not None:
            try:
                self.on_failure_frame(self._last_frame, why)
            except Exception:
                log.exception("falha ao salvar captura de diagnóstico")

    def _pause_for_user(self, why) -> bool:
        self._save_failure(why)
        self._emit("erro", f"intervenção necessária: {why}")
        self.status = RunStatus.PAUSED
        self.reason = why
        self.pause_event.set()
        return True

    def _fail(self, why) -> bool:
        self._save_failure(why)
        self.status = RunStatus.FAILED
        self.reason = why
        self._emit("erro", f"rotina interrompida: {why}")
        return False

    # ------------------------------------------------------------------ laço
    def run(self):
        ok, why = self.check_allowed()
        if not ok:
            self.status = RunStatus.FAILED
            self.reason = why
            self._emit("erro", why)
            return
        self.status = RunStatus.RUNNING
        self.counters = RunCounters(started_at=self.clock(), clock=self.clock)
        self._emit("etapa", f"iniciando '{self.d.name}' ({'contínuo' if not self.limits.runs else self.limits.runs}"
                   f" execução(ões))")
        try:
            while self.step():
                pass
        except Aborted as exc:
            self.status = RunStatus.IDLE
            self._emit("fim", f"parada de emergência: {exc}")
        except Exception as exc:  # erro inesperado: para sem enviar mais nada
            log.exception("erro na rotina")
            self.status = RunStatus.FAILED
            self.reason = str(exc)
            self._emit("erro", f"erro inesperado: {exc}")

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
