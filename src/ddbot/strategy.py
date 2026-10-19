"""Estratégias por instância: etapa atual, alvo prioritário e estados especiais dos chefes.

O motor de mira e combate é o mesmo para todas as instâncias; o que muda é *quem* atacar
e *quando*. Cada perfil (``data/knowledge/instances.json``) descreve as etapas, os papéis
dos alvos (rainha, Barão, Midas...), os estados especiais (escudo, pavio) e a regra de
escolha de cada etapa. Os perfis vêm de guias de jogadores com fonte registrada; nada é
tratado como confirmado no DDClássico.

Reconhecimento: cada papel e estado é um modelo de imagem capturado pelo usuário no
próprio cliente (``alvo_<instancia>_<papel>``, ``status_<instancia>_<estado>``). Nada de
coordenadas fixas. Sem o modelo de um papel, a etapa usa o marcador genérico de inimigo e
avisa uma vez.

Travas (na dúvida, não atira):
- alvo marcado como imune não é atacado; se só ele está visível, espera;
- chefe que sumiu (invisível) não é trocado na hora: espera algumas leituras;
- estado com efeito "pausar" ou etapa fora do escopo pede intervenção;
- disparos demais na mesma etapa sem diminuir os inimigos pede intervenção.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

from .activities import slug, valid_name

log = logging.getLogger(__name__)

GENERIC_ROLE = "inimigo"  # inimigo achado pelo marcador genérico, sem papel reconhecido
PICKS = ("mais_proximo", "agrupado", "ameaca")
EFFECTS = ("imune", "so_por_cima", "pausar")
SUPPORT_LABELS = {"implementado": "estratégia própria", "pesquisa": "só pesquisa (o bot não joga sozinho)"}
SOLO_LABELS = {"possivel": "possível sozinho", "dificil": "difícil sozinho", "muito_dificil": "muito difícil sozinho",
               "desconhecido": "sozinho: não informado"}
HIGH_ARC_MIN_ANGLE = 60
DIFFICULTY_WORDS = ("facil", "normal", "dificil", "avancado", "epico")


@dataclass(frozen=True)
class Role:
    key: str
    name: str
    boss: bool = False


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

    @property
    def runnable(self) -> bool:
        return self.support == "implementado" and bool(self.stages)

    def role_template(self, role: str) -> str:
        return f"alvo_{self.key}_{role}"

    def status_template(self, status: str) -> str:
        return f"status_{self.key}_{status}"

    def templates(self) -> dict[str, str]:
        """Modelos que a Calibração pede para esta instância (nome -> descrição)."""
        out = {self.role_template(r.key): f"Alvo: {r.name} ({self.name})" for r in self.roles.values()}
        out.update({self.status_template(s.key): f"Estado: {s.name} ({self.name})" for s in self.statuses.values()})
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
            roles[r["id"]] = Role(r["id"], str(r.get("nome", r["id"])), bool(r.get("chefe")))
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
            refs = set(targets) | set(st.get("ignorar", [])) | set(st.get("entra_com", []))
            if refs - known:
                raise ValueError(f"{key}/{st['id']}: papéis desconhecidos {sorted(refs - known)}")
            pick = st.get("escolha", "mais_proximo")
            if pick not in PICKS:
                raise ValueError(f"{key}/{st['id']}: escolha inválida {pick!r}")
            stages.append(Stage(st["id"], str(st.get("nome", st["id"])), str(st.get("objetivo", "")), targets,
                                tuple(st.get("ignorar", [])), pick, tuple(st.get("entra_com", [])),
                                max(3, int(st.get("max_disparos_sem_progresso", 15))),
                                bool(st.get("fora_do_escopo"))))
        support = raw.get("suporte", "pesquisa")
        if support not in SUPPORT_LABELS:
            raise ValueError(f"{key}: suporte inválido {support!r}")
        if support == "implementado" and any(not s.targets or s.out_of_scope for s in stages):
            raise ValueError(f"{key}: estratégia implementada precisa de alvos em todas as etapas")
        return cls(key, str(raw.get("nome", key)), tuple(raw.get("nomes", [])), tuple(raw.get("dificuldades", [])),
                   raw.get("solo", "desconhecido"), support, raw.get("confianca", "baixa"), str(raw.get("resumo", "")),
                   roles, statuses, stages, tuple(raw.get("referencias_de_mira", [])), tuple(raw.get("limites", [])),
                   tuple(raw.get("fontes", [])))


def load_profiles(path: Path) -> tuple[dict[str, InstanceProfile], list[str]]:
    """Perfis válidos (por id) e erros legíveis."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return {}, [f"{Path(path).name}: {exc}"]
    out, errors = {}, []
    for item in raw.get("instancias", []):
        try:
            p = InstanceProfile.from_raw(item)
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
    hits = [p for p in profiles.values() if fits(p)]
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


class StrategyPlanner:
    """Acompanha a etapa e escolhe o alvo a cada leitura. Um por execução da rotina."""

    STAGE_CONFIRM = 3      # leituras seguidas vendo o papel que abre a próxima etapa
    HIDE_GRACE_READS = 12  # leituras esperando um chefe que sumiu antes de mirar outro alvo
    STATUS_CONFIRM = 2     # leituras seguidas de um estado "pausar" antes de pausar

    def __init__(self, profile: InstanceProfile, has_template=lambda name: False, on_event=None,
                 cluster_radius: float = 1.0):
        self.p = profile
        self.has = has_template
        self.on_event = on_event or (lambda kind, msg: None)
        self.cluster_radius = cluster_radius  # régua: inimigos a essa distância contam como "juntos"
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

    def _advance(self, idx: int, why: str):
        if idx <= self.index or idx >= len(self.p.stages):
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
        """Efeito de cada inimigo (por ``id``) a partir dos estados vistos perto dele."""
        out: dict[int, str] = {}
        pause = None
        seen = set()
        for s in statuses:
            rule = self.p.statuses.get(s.kind)
            if rule is None:
                continue
            group = [e for e in enemies if e.kind in rule.roles]
            if not group:
                continue  # estado sem o chefe na tela: não vale
            e = min(group, key=lambda c: math.hypot(c.x - s.x, c.y - s.y))
            if math.hypot(e.x - s.x, e.y - s.y) > 3 * max(unit_px, 1.0):
                continue
            seen.add(rule.key)
            if rule.effect == "pausar":
                n = self._status_reads.get(rule.key, 0) + 1
                self._status_reads[rule.key] = n
                if n >= self.STATUS_CONFIRM:
                    pause = rule.message
            elif out.get(id(e)) != "imune":
                out[id(e)] = rule.effect
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

    def update(self, enemies: list, statuses: list, me, unit_px: float) -> Plan:
        """Uma leitura: avança a etapa quando há evidência e escolhe o alvo."""
        visible = {e.kind for e in enemies}
        for idx in range(self.index + 1, len(self.p.stages)):
            st = self.p.stages[idx]
            if st.enters_with and visible & set(st.enters_with):
                self._enter_reads[idx] = self._enter_reads.get(idx, 0) + 1
                if self._enter_reads[idx] >= self.STAGE_CONFIRM:
                    who = next(self.p.roles[r].name for r in st.enters_with if r in visible)
                    self._advance(idx, f"{who} apareceu")
                    break
            else:
                self._enter_reads[idx] = 0
        st = self.stage
        if st.out_of_scope:
            return Plan(stage=st, pause=f"a etapa {st.name} não é combate que o bot faça sozinho ({st.objective})")
        if self._fewest is None or len(enemies) < self._fewest:
            if self._fewest is not None:
                self._shots = 0  # um inimigo a menos: houve progresso
            self._fewest = len(enemies)
        effects, pause = self._effects(enemies, statuses, unit_px)
        if pause:
            return Plan(stage=st, pause=pause)

        targets = [r for r in st.targets if r not in st.ignore]
        if not any(self._known(r) for r in targets if r != GENERIC_ROLE) and any(r != GENERIC_ROLE for r in targets):
            names = ", ".join(self.p.roles[r].name for r in targets if r != GENERIC_ROLE)
            self._warn_once(f"generico_{st.key}", f"{self.p.name}, etapa {st.name}: sem o modelo de {names} "
                            "(Calibração > Alvos), o bot mira qualquer inimigo visível")
            targets = [GENERIC_ROLE]
            pool = [e for e in enemies if e.kind not in st.ignore]
        else:
            pool = enemies
        immune = []
        for role in targets:
            group = [e for e in pool if e.kind == role and effects.get(id(e)) != "imune"]
            immune += [e for e in pool if e.kind == role and effects.get(id(e)) == "imune"]
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
        if immune:
            names = sorted({self.p.roles[e.kind].name for e in immune if e.kind in self.p.roles})
            return Plan(stage=st, reason=f"{', '.join(names) or 'alvo'} imune agora: aguardando")
        return Plan(stage=st, reason=f"nenhum alvo da etapa {st.name} visível")


def apply_plan(obs, plan: Plan):
    """Copia a decisão da estratégia para a observação; devolve o alvo (ou None)."""
    obs.stage = plan.stage.name if plan.stage else None
    obs.pause_reason = plan.pause
    obs.high_arc = plan.high_arc
    if plan.reason:
        obs.notes.append(plan.reason)
    if plan.target is None and plan.hidden_role is None and not plan.pause:
        obs.wait_reason = plan.reason or "nenhum alvo da etapa"
    return plan.target
