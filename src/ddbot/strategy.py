"""Estratégias por instância: etapa atual, alvo prioritário e estados especiais dos chefes.

O motor de mira e combate é o mesmo para todas as instâncias; o que muda é *quem* atacar
e *quando*. Cada perfil (``data/knowledge/instances.json``) descreve as etapas, os papéis
dos alvos (rainha, Barão, Midas...), os estados especiais (escudo, pavio) e a regra de
escolha de cada etapa. Os perfis vêm de guias de jogadores com fonte registrada; nada é
tratado como confirmado no servidor do jogo.

Reconhecimento: cada papel e estado é um modelo de imagem capturado pelo usuário no
próprio cliente (``alvo_<instancia>_<papel>``, ``status_<instancia>_<estado>``). Nada de
coordenadas fixas. Sem o modelo de um papel, a etapa usa o marcador genérico de inimigo e
avisa uma vez.

Travas (na dúvida, não atira):
- alvo marcado como imune não é atacado; se só ele está visível, espera;
- chefe que sumiu (invisível) não é trocado na hora: espera algumas leituras;
- estado com efeito "pausar" ou etapa fora do escopo pede intervenção;
- disparos demais na mesma etapa sem diminuir os inimigos pede intervenção;
- papéis marcados para evitar (ex.: o juiz) nunca são alvo, e o disparo não mira perto deles;
- etapas que exigem reconhecimento (pontuação, corrida, papéis a evitar) pausam sem os modelos,
  em vez de mirar "qualquer inimigo".

Dificuldades: um perfil pode herdar de outro (``base``) e mudar só o que difere; os modelos de
imagem ficam no nome da instância (``modelos``), então as dificuldades compartilham as capturas.

Tipos de etapa: ``combate`` (derrotar alvos), ``pontuacao`` (acertar os alvos que somam pontos e
evitar os que tiram) e ``corrida`` (objetivo que não é derrotar alvos: só segue com o que o perfil
descreve; sem isso, pausa e explica).
"""
from __future__ import annotations

import copy
import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

from .activities import slug, valid_name

log = logging.getLogger(__name__)

GENERIC_ROLE = "inimigo"  # inimigo achado pelo marcador genérico, sem papel reconhecido
PICKS = ("mais_proximo", "agrupado", "ameaca")
EFFECTS = ("imune", "so_por_cima", "pausar", "vulneravel")
STAGE_KINDS = ("combate", "pontuacao", "corrida")
SUPPORT_LABELS = {"implementado": "estratégia própria", "pesquisa": "só pesquisa (o bot não joga sozinho)"}
SOLO_LABELS = {"possivel": "possível sozinho", "dificil": "difícil sozinho", "muito_dificil": "muito difícil sozinho",
               "desconhecido": "sozinho: não informado"}
CONFIDENCE_LABELS = {"alta": "alta", "media": "média", "media-alta": "média-alta", "baixa": "baixa",
                     "nenhuma": "nenhuma"}
HIGH_ARC_MIN_ANGLE = 60
DIFFICULTY_WORDS = ("facil", "normal", "dificil", "avancado", "epico")


@dataclass(frozen=True)
class Role:
    key: str
    name: str
    boss: bool = False
    points: float | None = None   # etapa de pontuação: quanto vale atingir (negativo = tira pontos)
    avoid: bool = False           # nunca atingir (ex.: o juiz): o disparo não mira perto dele


@dataclass(frozen=True)
class StatusRule:
    key: str
    name: str
    roles: tuple[str, ...]   # papéis em que o estado aparece (ex.: Midas nas duas fases)
    effect: str
    message: str


@dataclass
class Stage:
    key: str
    name: str
    objective: str
    targets: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    pick: str = "mais_proximo"
    enters_with: tuple[str, ...] = ()
    max_shots: int = 15
    out_of_scope: bool = False
    kind: str = "combate"          # combate | pontuacao | corrida
    avoid: tuple[str, ...] = ()    # papéis que o disparo não pode atingir nesta etapa
    needs_models: bool = False     # sem os modelos dos papéis desta etapa, pausa (não mira qualquer inimigo)
    goal: str = ""                 # condição de avanço descrita pelas fontes (só informativa)
    required: tuple[str, ...] = ()  # papéis sem os quais a etapa não age (em vez da regra padrão do tipo)


@dataclass
class InstanceProfile:
    key: str
    name: str
    aliases: tuple[str, ...] = ()
    difficulties: tuple[str, ...] = ()
    solo: str = "desconhecido"
    support: str = "pesquisa"
    confidence: str = "baixa"
    summary: str = ""
    roles: dict[str, Role] = field(default_factory=dict)
    statuses: dict[str, StatusRule] = field(default_factory=dict)
    stages: list[Stage] = field(default_factory=list)
    aim_refs: tuple[str, ...] = ()
    limits: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    models: str = ""               # prefixo dos modelos de imagem (o mesmo nas dificuldades da instância)
    base: str | None = None        # perfil de que este herdou (mesma instância, outra dificuldade)

    @property
    def runnable(self) -> bool:
        return self.support == "implementado" and bool(self.stages)

    @property
    def model_key(self) -> str:
        return self.models or self.key

    def role_template(self, role: str) -> str:
        return f"alvo_{self.model_key}_{role}"

    def status_template(self, status: str) -> str:
        return f"status_{self.model_key}_{status}"

    def templates(self) -> dict[str, str]:
        """Modelos que a Calibração pede para esta instância (nome -> descrição)."""
        out = {self.role_template(r.key): f"Alvo: {r.name} ({self.name})" for r in self.roles.values()}
        out.update({self.status_template(s.key): f"Estado: {s.name} ({self.name})" for s in self.statuses.values()})
        return out

    def blocking_roles(self, st: Stage, known=lambda role: False) -> list[str]:
        """Papéis cujo modelo falta e sem os quais a etapa não pode agir com segurança.

        - papéis a evitar: sem reconhecê-los, o disparo pode cair neles;
        - pontuação: os alvos que tiram pontos (um alvo bom colado num ruim não seria percebido) e pelo
          menos um alvo que soma;
        - corrida (e outros tipos que não são combate comum): pelo menos um dos alvos da etapa.
        Combate comum não bloqueia: sem o modelo do papel, mira qualquer inimigo e avisa.
        """
        if not st.needs_models:
            return []
        named = [r for r in st.targets if r in self.roles]
        out = [r for r in st.avoid if r in self.roles and not known(r)]
        if st.required:
            out += [r for r in st.required if not known(r)]
        elif st.kind == "pontuacao":
            out += [r for r in named if (self.roles[r].points or 0) < 0 and not known(r)]
            good = [r for r in named if (self.roles[r].points or 0) > 0]
            if good and not any(known(r) for r in good):
                out += good[:1]
        elif st.kind != "combate" and named and not any(known(r) for r in named):
            out += named[:1]
        return list(dict.fromkeys(out))

    def required_templates(self) -> dict[str, str]:
        """Modelos sem os quais alguma etapa não age (pontuação, corrida, papéis a evitar)."""
        out = {}
        for st in self.stages:
            for role in self.blocking_roles(st):
                out[self.role_template(role)] = f"Alvo: {self.roles[role].name} ({self.name})"
        return out

    def describe(self) -> str:
        stages = " → ".join(s.name for s in self.stages) or "etapas não descritas"
        return f"{self.summary} Etapas: {stages}. {SOLO_LABELS.get(self.solo, self.solo).capitalize()}."

    @classmethod
    def from_raw(cls, raw: dict) -> "InstanceProfile":
        key = raw.get("id")
        if not valid_name(key):
            raise ValueError(f"id de instância inválido: {key!r}")
        roles = {}
        for r in raw.get("papeis", []):
            if not valid_name(r.get("id")) or r["id"] == GENERIC_ROLE:
                raise ValueError(f"{key}: papel inválido {r.get('id')!r}")
            points = r.get("pontos")
            roles[r["id"]] = Role(r["id"], str(r.get("nome", r["id"])), bool(r.get("chefe")),
                                  None if points is None else float(points), bool(r.get("evitar")))
        known = set(roles) | {GENERIC_ROLE}
        statuses = {}
        for s in raw.get("estados", []):
            on = tuple(s.get("papeis") or [s.get("papel")])
            if not valid_name(s.get("id")) or s.get("efeito") not in EFFECTS or not set(on) <= set(roles):
                raise ValueError(f"{key}: estado inválido {s!r}")
            statuses[s["id"]] = StatusRule(s["id"], str(s.get("nome", s["id"])), on, s["efeito"],
                                           str(s.get("mensagem", s.get("nome", s["id"]))))
        stages = []
        for st in raw.get("etapas", []):
            if not valid_name(st.get("id")):
                raise ValueError(f"{key}: etapa inválida {st.get('id')!r}")
            targets = tuple(st.get("alvos", []))
            avoid = tuple(st.get("evitar", [])) + tuple(r for r in roles if roles[r].avoid
                                                         and r not in st.get("evitar", []))
            refs = set(targets) | set(st.get("ignorar", [])) | set(st.get("entra_com", [])) | set(avoid) \
                | set(st.get("requer", []))
            if refs - known:
                raise ValueError(f"{key}/{st['id']}: papéis desconhecidos {sorted(refs - known)}")
            pick = st.get("escolha", "mais_proximo")
            if pick not in PICKS:
                raise ValueError(f"{key}/{st['id']}: escolha inválida {pick!r}")
            kind = st.get("tipo", "combate")
            if kind not in STAGE_KINDS:
                raise ValueError(f"{key}/{st['id']}: tipo de etapa inválido {kind!r}")
            if set(targets) & set(avoid):
                raise ValueError(f"{key}/{st['id']}: o mesmo papel não pode ser alvo e evitado")
            if kind == "pontuacao" and not any(roles[r].points for r in targets if r in roles):
                raise ValueError(f"{key}/{st['id']}: etapa de pontuação sem alvos com pontos")
            # pontuação e corrida não são "derrotar qualquer inimigo": sem reconhecer os papéis, não age
            needs = bool(st.get("requer_modelos", kind != "combate" or bool(avoid)))
            stages.append(Stage(st["id"], str(st.get("nome", st["id"])), str(st.get("objetivo", "")), targets,
                                tuple(st.get("ignorar", [])), pick, tuple(st.get("entra_com", [])),
                                max(3, int(st.get("max_disparos_sem_progresso", 15))),
                                bool(st.get("fora_do_escopo")), kind, avoid, needs, str(st.get("condicao", "")),
                                tuple(st.get("requer", []))))
        support = raw.get("suporte", "pesquisa")
        if support not in SUPPORT_LABELS:
            raise ValueError(f"{key}: suporte inválido {support!r}")
        if support == "implementado" and any((not s.targets and s.kind != "corrida") or s.out_of_scope
                                             for s in stages):
            raise ValueError(f"{key}: estratégia implementada precisa de alvos em todas as etapas")
        models = raw.get("modelos") or ""
        if models and not valid_name(models):
            raise ValueError(f"{key}: prefixo de modelos inválido {models!r}")
        return cls(key, str(raw.get("nome", key)), tuple(raw.get("nomes", [])), tuple(raw.get("dificuldades", [])),
                   raw.get("solo", "desconhecido"), support, raw.get("confianca", "baixa"), str(raw.get("resumo", "")),
                   roles, statuses, stages, tuple(raw.get("referencias_de_mira", [])), tuple(raw.get("limites", [])),
                   tuple(raw.get("fontes", [])), models, raw.get("base"))


def _resolve(item: dict, by_id: dict[str, dict], seen=()) -> dict:
    """Perfil com a herança aplicada: o que o filho define substitui; ``ajustes_etapas`` muda só campos
    de etapas existentes; ``limites_extra``/``fontes_extra`` somam; os modelos de imagem são os da base."""
    base_id = item.get("base")
    if not base_id:
        return item
    if base_id in seen or base_id not in by_id:
        raise ValueError(f"{item.get('id')}: base inválida {base_id!r}")
    base = _resolve(by_id[base_id], by_id, seen + (item.get("id"),))
    out = copy.deepcopy(base)
    for k, v in item.items():
        if k not in ("ajustes_etapas", "limites_extra", "fontes_extra", "etapas_ids"):
            out[k] = copy.deepcopy(v)
    if "etapas_ids" in item:
        # a dificuldade usa só algumas etapas da instância, na ordem dada (ex.: o Normal tem a corrida)
        by_stage = {st.get("id"): st for st in base.get("etapas", [])}
        unknown = [sid for sid in item["etapas_ids"] if sid not in by_stage]
        if unknown:
            raise ValueError(f"{item.get('id')}: etapas desconhecidas na base {unknown}")
        out["etapas"] = [copy.deepcopy(by_stage[sid]) for sid in item["etapas_ids"]]
    if "modelos" not in item:
        out["modelos"] = base.get("modelos") or base.get("id")
    stages = {st.get("id"): st for st in out.get("etapas", [])}
    for sid, changes in (item.get("ajustes_etapas") or {}).items():
        if sid not in stages:
            raise ValueError(f"{item.get('id')}: ajuste de etapa desconhecida {sid!r}")
        stages[sid].update(copy.deepcopy(changes))
    out["limites"] = list(out.get("limites", [])) + list(item.get("limites_extra", []))
    out["fontes"] = list(dict.fromkeys(list(out.get("fontes", [])) + list(item.get("fontes_extra", []))))
    return out


def load_profiles(path: Path) -> tuple[dict[str, InstanceProfile], list[str]]:
    """Perfis válidos (por id) e erros legíveis."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return {}, [f"{Path(path).name}: {exc}"]
    items = [i for i in raw.get("instancias", []) if isinstance(i, dict)]
    by_id = {i.get("id"): i for i in items}
    out, errors = {}, []
    for item in items:
        try:
            p = InstanceProfile.from_raw(_resolve(item, by_id))
            out[p.key] = p
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            errors.append(str(exc))
    return out, errors


def match_profile(name: str, profiles: dict[str, InstanceProfile]) -> InstanceProfile | None:
    """Perfil cujo nome aparece no nome dado à atividade (ex.: "Formigueiro normal")."""
    text = f"_{slug(name)}_"
    said = {d for d in DIFFICULTY_WORDS if f"_{d}_" in text}

    def fits(p):
        if not any(f"_{slug(a)}_" in text or text.strip("_").startswith(slug(a)) for a in (p.aliases or (p.name,))):
            return False
        # "Bugou Avançado" não é o perfil do Normal (a Avançada tem uma etapa a mais)
        own = {slug(d) for d in p.difficulties}
        return not (own and said and not said & own)
    hits = [p for p in profiles.values() if p.runnable and fits(p)]
    if said and len(hits) > 1:
        exact = [p for p in hits if {slug(d) for d in p.difficulties} == said]
        hits = exact or hits
    if not said:
        # sem dificuldade no nome: só o perfil geral da instância; um de dificuldade seria um chute
        hits = [p for p in hits if p.base is None]
    return hits[0] if len(hits) == 1 else None


# --------------------------------------------------------------------------- decisão
@dataclass
class Plan:
    target: object | None = None       # Character escolhido (ou None)
    role: str | None = None
    stage: Stage | None = None
    reason: str = ""
    high_arc: bool = False             # só tiro alto (estado "so_por_cima")
    pause: str | None = None           # pedir intervenção
    hidden_role: str | None = None     # o alvo seguido sumiu: espera por ele (invisibilidade)
    missing: bool = False              # nenhum alvo da etapa na tela (o combate conta os turnos assim e pausa)


class StrategyPlanner:
    """Acompanha a etapa e escolhe o alvo a cada leitura. Um por execução da rotina."""

    STAGE_CONFIRM = 3      # leituras seguidas vendo o papel que abre a próxima etapa
    HIDE_GRACE_READS = 12  # leituras esperando um chefe que sumiu antes de mirar outro alvo
    STATUS_CONFIRM = 2     # leituras seguidas de um estado "pausar" antes de pausar
    COUNT_WINDOW = 5       # leituras usadas para contar os inimigos de forma estável

    def __init__(self, profile: InstanceProfile, has_template=lambda name: False, on_event=None,
                 cluster_radius: float = 1.0, reach: float = 0.6, avoid_radius: float = 1.0):
        self.p = profile
        self.has = has_template
        self.on_event = on_event or (lambda kind, msg: None)
        self.cluster_radius = cluster_radius  # régua: inimigos a essa distância contam como "juntos"
        self.reach = reach                    # régua: o que a explosão pega em volta do ponto de mira
        self.avoid_radius = avoid_radius      # régua: distância mínima entre o ponto de mira e um papel a evitar
        self.reset_run()

    # ------------------------------------------------------------------ estado
    def reset_run(self):
        self.index = 0
        self._battles = 0
        self._enter_reads: dict[int, int] = {}
        self._status_reads: dict[str, int] = {}
        self._warned: set[str] = set()
        self._last: tuple[str, float, float] | None = None
        self._missing_reads = 0
        self._progress()

    @property
    def stage(self) -> Stage:
        return self.p.stages[min(self.index, len(self.p.stages) - 1)]

    def _emit(self, kind, msg):
        (log.warning if kind == "aviso" else log.info)(msg)
        self.on_event(kind, msg)

    def _warn_once(self, key, msg):
        if key not in self._warned:
            self._warned.add(key)
            self._emit("aviso", msg)

    def _progress(self):
        self._shots = 0
        self._fewest: int | None = None
        self._counts: list[int] = []

    def _advance(self, idx: int, why: str, back_ok: bool = False):
        if idx == self.index or idx >= len(self.p.stages) or (idx < self.index and not back_ok):
            return
        self.index = idx
        self._last, self._missing_reads = None, 0
        self._enter_reads.clear()
        self._progress()
        st = self.stage
        self._emit("etapa", f"{self.p.name}: etapa {idx + 1}/{len(self.p.stages)} — {st.name} ({why}). {st.objective}")

    def on_battle_start(self):
        """Nova batalha na mesma execução: no mínimo a etapa seguinte (cada etapa é uma batalha)."""
        self._battles += 1
        self._last, self._missing_reads = None, 0
        self._progress()
        if self._battles == 1:
            st = self.stage
            self._emit("etapa", f"{self.p.name}: etapa 1/{len(self.p.stages)} — {st.name}. {st.objective}")
        else:
            self._advance(min(len(self.p.stages) - 1, self._battles - 1), "nova batalha")

    def on_shot(self) -> str | None:
        """Depois de cada disparo: motivo para pedir intervenção se não há progresso."""
        self._shots += 1
        st = self.stage
        if self._shots >= st.max_shots:
            self._shots = 0  # ao retomar, conta de novo (a referência de inimigos continua)
            return (f"{self._shots_msg(st)}: confira o jogo (alvo errado, imune ou fora de alcance) e clique em "
                    "Retomar")
        return None

    def _shots_msg(self, st):
        return f"{st.max_shots} disparos na etapa {st.name} sem diminuir os inimigos"

    # ----------------------------------------------------------------- escolha
    def _known(self, role: str) -> bool:
        return role == GENERIC_ROLE or self.has(self.p.role_template(role))

    def _effects(self, enemies, statuses, unit_px) -> tuple[dict[int, str], str | None]:
        """Efeito de cada inimigo (por ``id``) a partir dos estados vistos perto dele.

        O estado vale para o inimigo mais próximo dele, de preferência com o papel da regra;
        se o chefe naquele quadro só foi achado pelo marcador genérico (o escudo e o pavio mudam
        a aparência dele), vale para o inimigo genérico mais próximo. Um estado "pausar" conta
        mesmo sem inimigo por perto: na dúvida, pausa. Cada estado conta uma vez por leitura.
        """
        out: dict[int, str] = {}
        pause = None
        seen = set()
        radius = 3 * max(unit_px, 1.0)
        for s in statuses:
            rule = self.p.statuses.get(s.kind)
            if rule is None:
                continue
            group = [e for e in enemies if e.kind in rule.roles] or \
                [e for e in enemies if e.kind == GENERIC_ROLE]
            e = min(group, key=lambda c: math.hypot(c.x - s.x, c.y - s.y)) if group else None
            near = e is not None and math.hypot(e.x - s.x, e.y - s.y) <= radius
            if rule.effect == "pausar":
                seen.add(rule.key)
            elif near and out.get(id(e)) != "imune":
                seen.add(rule.key)
                out[id(e)] = rule.effect
        for key in seen:
            if self.p.statuses[key].effect == "pausar":
                self._status_reads[key] = self._status_reads.get(key, 0) + 1
                if self._status_reads[key] >= self.STATUS_CONFIRM:
                    pause = self.p.statuses[key].message
        for k in list(self._status_reads):
            if k not in seen:
                self._status_reads[k] = 0
        return out, pause

    def _choose(self, group, all_enemies, pick, me, unit_px):
        unit = max(unit_px, 1.0)
        if self._last is not None and self._last[0] == group[0].kind:
            # continua no mesmo inimigo enquanto ele estiver perto de onde foi visto (não alterna entre dois)
            _, lx, ly = self._last
            near = min(group, key=lambda e: math.hypot(e.x - lx, e.y - ly))
            if math.hypot(near.x - lx, near.y - ly) <= 2 * unit:
                return near

        def dist(e):
            return abs(e.x - me.x) if me is not None else e.x
        if pick == "agrupado":
            r = self.cluster_radius * unit
            return max(group, key=lambda e: (sum(1 for o in all_enemies if o is not e and abs(o.x - e.x) <= r),
                                             -dist(e)))
        return min(group, key=dist)  # mais_proximo e ameaca: o mais perto do seu personagem

    def _missing_models(self, st: Stage) -> list[str]:
        return self.p.blocking_roles(st, self._known)

    def _score_plan(self, st: Stage, foes, avoid, me, unit: float) -> Plan:
        """Etapa de pontuação: o alvo que mais soma, contando o que a explosão pega em volta dele.

        Alvos que tiram pontos nunca são mirados, e um alvo bom colado num que tira pontos (ou num
        papel a evitar) só é escolhido se o total esperado continuar positivo.
        """
        valued = [e for e in foes if e.kind in st.targets and self.p.roles.get(e.kind) is not None
                  and self.p.roles[e.kind].points is not None]

        def near(a, b, radius):
            return math.hypot(a.x - b.x, a.y - b.y) <= radius * unit

        def dist(e):
            return abs(e.x - me.x) if me is not None else e.x
        best, best_total, blocked = None, 0.0, False
        for e in valued:
            if self.p.roles[e.kind].points <= 0:
                continue
            if any(near(e, a, self.avoid_radius) for a in avoid):
                blocked = True
                continue
            total = sum(self.p.roles[o.kind].points for o in valued if near(e, o, self.reach))
            if total <= 0:
                blocked = True
                continue
            if best is None or total > best_total or (total == best_total and dist(e) < dist(best)):
                best, best_total = e, total
        if best is None:
            why = ("os alvos que somam pontos estão colados nos que tiram (ou num alvo a evitar): aguardando"
                   if blocked else f"nenhum alvo que some pontos visível na etapa {st.name}")
            return Plan(stage=st, reason=why, missing=not blocked)
        name = self.p.roles[best.kind].name
        return Plan(best, best.kind, st, f"etapa {st.name}: {name} ({best_total:+g} pontos esperados)")

    def update(self, enemies: list, statuses: list, me, unit_px: float) -> Plan:
        """Uma leitura: avança a etapa quando há evidência e escolhe o alvo."""
        visible = {e.kind for e in enemies}
        cur = self.stage
        own = (set(cur.targets) | set(cur.enters_with)) - {GENERIC_ROLE}
        own_bosses = {r for r in cur.targets if r in self.p.roles and self.p.roles[r].boss}
        for idx, st in enumerate(self.p.stages):
            if idx == self.index or not st.enters_with:
                continue
            # a etapa é a que a tela mostra: as fontes não garantem a ordem (ex.: no Galinheiro Difícil o
            # chefe vem antes da construção). Voltar a uma etapa anterior só sem nada da atual na tela, e
            # nunca deixar uma etapa com o chefe dela ainda visível (ele continuaria atacando sem ser alvo)
            switch_ok = (idx > self.index or not (visible & own)) and not ((visible & own_bosses) - set(st.targets))
            if switch_ok and visible & set(st.enters_with):
                self._enter_reads[idx] = self._enter_reads.get(idx, 0) + 1
                if self._enter_reads[idx] >= self.STAGE_CONFIRM:
                    who = next(self.p.roles[r].name for r in st.enters_with if r in visible)
                    self._advance(idx, f"{who} apareceu", back_ok=True)
                    break
            else:
                self._enter_reads[idx] = 0
        st = self.stage
        confirming = any(n > 0 for n in self._enter_reads.values())
        if st.out_of_scope:
            return Plan(stage=st, pause=f"a etapa {st.name} não é combate que o bot faça sozinho ({st.objective})")
        unit = max(unit_px, 1.0)
        avoid = [e for e in enemies if e.kind in st.avoid]
        foes = [e for e in enemies if e.kind not in st.avoid]
        # progresso = menos inimigos de forma estável: o maior número das últimas leituras (um quadro
        # vazio de explosão ou câmera não conta) caiu em relação ao anterior; ondas novas sobem a referência
        self._counts.append(len(foes))
        del self._counts[:-self.COUNT_WINDOW]
        stable = max(self._counts)
        if self._fewest is not None and stable < self._fewest:
            self._shots = 0
        self._fewest = stable
        effects, pause = self._effects(foes, statuses, unit_px)
        if pause:
            return Plan(stage=st, pause=pause)
        if confirming and (st.needs_models or st.kind == "corrida"):
            # outra etapa pode estar começando: não pausa nem atira numa etapa que talvez já tenha acabado
            return Plan(stage=st, reason="conferindo se a etapa mudou")
        if st.needs_models:
            missing = self._missing_models(st)
            if missing:
                names = ", ".join(self.p.roles[r].name for r in missing)
                return Plan(stage=st, pause=f"{self.p.name}, etapa {st.name}: o bot precisa reconhecer {names} "
                            "antes de agir (capture em Calibração > Alvos); sem isso ele não atira")
        if st.kind == "corrida" and not st.targets:
            return Plan(stage=st, pause=f"etapa {st.name}: {st.objective} Não é um combate comum e o JonFlow não "
                        "tem como agir nela sozinho; jogue esta etapa e clique em Retomar")
        if st.kind == "pontuacao":
            return self._score_plan(st, foes, avoid, me, unit)

        targets = [r for r in st.targets if r not in st.ignore]
        if not any(self._known(r) for r in targets if r != GENERIC_ROLE) and any(r != GENERIC_ROLE for r in targets):
            names = ", ".join(self.p.roles[r].name for r in targets if r != GENERIC_ROLE)
            self._warn_once(f"generico_{st.key}", f"{self.p.name}, etapa {st.name}: sem o modelo de {names} "
                            "(Calibração > Alvos), o bot mira qualquer inimigo visível")
            targets = [GENERIC_ROLE]
            pool = [e for e in foes if e.kind not in st.ignore]
        else:
            pool = foes
        immune, close_to_avoid = [], []
        for role in targets:
            group = [e for e in pool if e.kind == role and effects.get(id(e)) != "imune"]
            immune += [e for e in pool if e.kind == role and effects.get(id(e)) == "imune"]
            safe = [e for e in group if all(math.hypot(e.x - a.x, e.y - a.y) > self.avoid_radius * unit
                                            for a in avoid)]
            close_to_avoid += [e for e in group if e not in safe]
            group = [e for e in safe if effects.get(id(e)) == "vulneravel"] or safe
            if not group:
                if self._last is not None and self._last[0] == role and role in self.p.roles \
                        and self.p.roles[role].boss and not any(e.kind == role for e in pool):
                    # o chefe seguido sumiu: invisível ou animação; não troca de alvo na hora
                    self._missing_reads += 1
                    if self._missing_reads < self.HIDE_GRACE_READS:
                        return Plan(stage=st, role=role, hidden_role=role,
                                    reason=f"{self.p.roles[role].name} não está visível: aguardando")
                continue
            choice = self._choose(group, pool, st.pick, me, unit_px)
            self._last, self._missing_reads = (role, choice.x, choice.y), 0
            eff = effects.get(id(choice))
            label = self.p.roles[role].name if role in self.p.roles else "inimigo"
            return Plan(choice, role, st, f"etapa {st.name}: {label}", high_arc=eff == "so_por_cima")
        if close_to_avoid:
            names = sorted({self.p.roles[e.kind].name for e in avoid if e.kind in self.p.roles})
            return Plan(stage=st, reason=f"alvo perto de {', '.join(names)}, que não pode ser atingido: aguardando")
        if immune:
            names = sorted({self.p.roles[e.kind].name for e in immune if e.kind in self.p.roles})
            return Plan(stage=st, reason=f"{', '.join(names) or 'alvo'} imune agora: aguardando")
        return Plan(stage=st, reason=f"nenhum alvo da etapa {st.name} visível", missing=True)


def apply_plan(obs, plan: Plan):
    """Copia a decisão da estratégia para a observação; devolve o alvo (ou None)."""
    obs.stage = plan.stage.name if plan.stage else None
    obs.pause_reason = plan.pause
    obs.high_arc = plan.high_arc
    if plan.reason:
        obs.notes.append(plan.reason)
    if plan.target is None and plan.hidden_role is None and not plan.pause:
        obs.wait_reason = plan.reason or "nenhum alvo da etapa"
        obs.target_missing = plan.missing
    return plan.target
