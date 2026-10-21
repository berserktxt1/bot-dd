"""Atividades pré-cadastradas: as instâncias prioritárias aparecem no Início sem captura manual.

O catálogo (``data/knowledge/catalogo.json``) diz quais atividades existem, com a instância, a
dificuldade e a estratégia de cada uma. O fluxo é o mesmo das atividades capturadas, montado a
partir de modelos compartilhados: os botões comuns (Instâncias, Iniciar...) são capturados uma
vez; a opção de cada instância no menu, uma vez para todas as dificuldades; e o botão de cada
dificuldade, uma vez para todas as instâncias.

O catálogo não garante que a atividade exista no cliente do usuário. A disponibilidade
(``dados/atividades_estado.json``) só muda com evidência: a opção vista no menu, a opção não
encontrada no menu durante uma rotina, ou o próprio usuário marcando. Uma atividade que não
aparece no menu nunca é trocada por outra: a rotina pausa e explica.

Uma atividade do usuário com o mesmo ``id`` (``instancias/<id>.json``) substitui a do catálogo:
ajustes feitos para o cliente do usuário não se perdem quando o programa é atualizado.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from .activities import INSTANCE_START_STATES, Action, ActivityDef, valid_name
from .util import atomic_write_text

log = logging.getLogger(__name__)

AVAILABLE, MISSING, UNVERIFIED, USER_OFF = "disponivel", "nao_encontrada", "nao_verificada", "indisponivel"
AVAILABILITY_LABELS = {
    AVAILABLE: "vista no menu do jogo",
    MISSING: "não encontrada no menu do jogo",
    UNVERIFIED: "ainda não conferida no jogo",
    USER_OFF: "marcada como indisponível por você",
}


@dataclass(frozen=True)
class Difficulty:
    key: str
    name: str
    template: str


@dataclass
class CatalogEntry:
    key: str
    name: str
    instance: str              # id da instância (nome do modelo da opção no menu)
    instance_name: str
    difficulty: str | None
    strategy: str | None
    option: str                # modelo da opção no menu (``instancia_<instancia>``)
    kind: str = "instancia"
    category: str = "pve"
    notes: tuple[str, ...] = ()
    order: int = 0


@dataclass
class Catalog:
    entries: list[CatalogEntry] = field(default_factory=list)
    difficulties: dict[str, Difficulty] = field(default_factory=dict)
    replaced: list[dict] = field(default_factory=list)  # fora da lista principal, com o motivo
    flow: dict | None = None    # fluxo padrão com {opcao} e {dificuldade}

    def get(self, key: str) -> CatalogEntry | None:
        return next((e for e in self.entries if e.key == key), None)

    def difficulty_templates(self) -> dict[str, str]:
        """Modelos dos botões de dificuldade (nome -> descrição para a Calibração)."""
        return {d.template: f"Botão da dificuldade {d.name}" for d in self.difficulties.values()}

    def option_templates(self) -> dict[str, str]:
        """Opções de instância no menu (nome do modelo -> nome da instância), sem repetir."""
        out: dict[str, str] = {}
        for e in self.entries:
            out.setdefault(e.option, e.instance_name)
        return out


# lobby -> Cais de Expedição -> Criar sala -> sala sem instância -> escolher a instância -> sala -> Iniciar
# (activities.instance_room_flow); a escolha é refeita a cada ida
DEFAULT_FLOW = {
    "lobby": [{"clicar": "botao_cais", "espera": 1.5}],
    "cais_expedicao": [{"clicar": "botao_criar_sala", "espera": 1.5}],
    "sala": [{"clicar": "botao_escolher_instancia", "espera": 1.5, "se": "sem_escolha"},
             {"clicar": "botao_iniciar", "espera": 2.0, "se": "com_escolha"}],
    "menu_instancias": [{"clicar": "{opcao}", "espera": 1.0}, {"clicar": "{dificuldade}", "espera": 1.0},
                        {"clicar_opcional": "botao_confirmar", "espera": 1.5}],
    # aviso do jogo ao iniciar sozinho uma instância difícil: só confirma com a permissão do usuário
    "aviso_sozinho": [{"confirmar_aviso": "botao_confirmar_aviso", "espera": 1.5}],
    "carregando": [{"aguardar": 1.0}],
    "batalha": [{"combate": True}],
    "etapa_concluida": [{"clicar_opcional": "botao_continuar", "espera": 1.5}],
    "recompensa": [{"clicar_opcional": "carta_recompensa", "espera": 1.0},
                   {"clicar_opcional": "botao_sair", "espera": 1.5}],
    "vitoria": [{"concluir": "vitoria"}, {"clicar_opcional": "botao_sair", "espera": 1.5}],
    "derrota": [{"concluir": "derrota"}, {"clicar_opcional": "botao_sair", "espera": 1.5}],
}


def load_catalog(path: Path) -> tuple[Catalog, list[str]]:
    """Catálogo válido e erros legíveis (uma entrada inválida não derruba as outras)."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return Catalog(), [f"{Path(path).name}: {exc}"]
    errors: list[str] = []
    diffs = {}
    for key, d in (raw.get("dificuldades") or {}).items():
        tpl = d.get("modelo") if isinstance(d, dict) else None
        if not valid_name(key) or not valid_name(tpl):
            errors.append(f"dificuldade inválida: {key!r}")
            continue
        diffs[key] = Difficulty(key, str(d.get("nome", key)), tpl)
    entries = []
    for i, e in enumerate(raw.get("atividades") or []):
        try:
            key, inst = e.get("id"), e.get("instancia")
            if not valid_name(key) or not valid_name(inst):
                raise ValueError(f"id ou instância inválidos: {key!r}/{inst!r}")
            diff = e.get("dificuldade")
            if diff is not None and diff not in diffs:
                raise ValueError(f"{key}: dificuldade desconhecida {diff!r}")
            option = e.get("opcao") or f"instancia_{inst}"
            if not valid_name(option):
                raise ValueError(f"{key}: modelo da opção inválido {option!r}")
            strategy = e.get("estrategia")
            if strategy is not None and not valid_name(strategy):
                raise ValueError(f"{key}: estratégia inválida {strategy!r}")
            iname = str(e.get("nome_instancia", inst))
            name = str(e.get("nome") or (f"{iname} — {diffs[diff].name}" if diff else iname))
            entries.append(CatalogEntry(key, name, inst, iname, diff, strategy, option,
                                        str(e.get("tipo", "instancia")), str(e.get("categoria", "pve")),
                                        tuple(e.get("observacoes", [])), int(e.get("ordem", i + 1))))
        except (AttributeError, TypeError, ValueError) as exc:
            errors.append(str(exc))
    entries.sort(key=lambda x: x.order)
    flow = raw.get("fluxo_padrao") if isinstance(raw.get("fluxo_padrao"), dict) else None
    return Catalog(entries, diffs, list(raw.get("fora_da_lista_principal") or []), flow), errors


def _fill(value, entry: CatalogEntry, catalog: Catalog):
    if not isinstance(value, str):
        return value
    diff = catalog.difficulties.get(entry.difficulty) if entry.difficulty else None
    return value.replace("{opcao}", entry.option).replace("{dificuldade}", diff.template if diff else "")


def build_activity(entry: CatalogEntry, catalog: Catalog) -> ActivityDef:
    """Definição de atividade de uma entrada do catálogo (não é gravada na pasta do usuário)."""
    flow = {}
    for state, acts in (catalog.flow or DEFAULT_FLOW).items():
        out = []
        for a in acts:
            a = {k: _fill(v, entry, catalog) for k, v in a.items()}
            if any(a.get(k) == "" for k in ("clicar", "clicar_opcional")):
                continue  # sem dificuldade (atividade de dificuldade única): o passo não existe
            out.append(Action.parse(a))
        flow[state] = out
    start = INSTANCE_START_STATES if entry.kind == "instancia" else ("lobby", "menu_partidas", "sala")
    level = f", dificuldade {catalog.difficulties[entry.difficulty].name}" if entry.difficulty else ""
    return ActivityDef(key=entry.key, name=entry.name, kind=entry.kind, category=entry.category,
                       description=f"Pré-cadastrada: {entry.instance_name}{level}.", flow=flow,
                       start_states=start, strategy=entry.strategy, builtin=True,
                       instance=entry.instance, difficulty=entry.difficulty, option=entry.option)


class AvailabilityStore:
    """Se cada atividade do catálogo aparece no cliente do usuário (só com evidência)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict[str, dict] = {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
            self.data = {k: v for k, v in raw.items() if valid_name(k) and isinstance(v, dict)}
        except (OSError, ValueError) as exc:
            log.warning("estado das atividades ilegível (%s); começando do zero", exc)

    def status(self, key: str) -> str:
        return self.data.get(key, {}).get("estado", UNVERIFIED)

    def detail(self, key: str) -> str:
        info = self.data.get(key, {})
        label = AVAILABILITY_LABELS.get(info.get("estado", UNVERIFIED), "")
        when = info.get("quando")
        return f"{label} em {when}" if when and info.get("estado") != UNVERIFIED else label

    def set(self, key: str, state: str, why: str = "") -> bool:
        """Grava o estado; devolve True se mudou."""
        if state not in AVAILABILITY_LABELS or not valid_name(key):
            raise ValueError(f"estado inválido: {state!r}")
        old = self.data.get(key, {})
        if old.get("estado") == state and old.get("motivo", "") == why:
            return False
        self.data[key] = {"estado": state, "quando": time.strftime("%d/%m/%Y %H:%M"), "motivo": why}
        try:
            atomic_write_text(self.path, json.dumps(self.data, indent=1, ensure_ascii=False))
        except OSError as exc:
            log.warning("não foi possível gravar o estado das atividades: %s", exc)
        return True
