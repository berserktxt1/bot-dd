"""Simulação de batalhas para testar mira, calibração e invisibilidade sem o cliente.

O "mundo" usa constantes físicas verdadeiras diferentes das do modelo (o bot não as
conhece) e acrescenta ruído de leitura e de execução. Assim dá para medir se a
calibração com disparos observados realmente reduz o erro.

Nada aqui envia teclas ou lê o jogo: ``SimulatedShooter`` só calcula o impacto.
"""
from __future__ import annotations

import random
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from .aiming import Aimer
from .automation.safety import KillSwitch
from .calibration import Calibrator, ShotStore
from .combat import BattleObservation, BattleView, CombatEngine, Mode, Shooter, ShotOutcome
from .config import Config
from .knowledge import KnowledgeBase
from .physics import PhysicsParams, landing_x
from .tracking import TargetTracker


@dataclass
class SimSettings:
    seed: int = 1
    max_turns: int = 12
    target_hp: int = 3               # acertos necessários para vencer
    wind_max: float = 3.0
    distance_range: tuple[float, float] = (3.0, 15.0)
    dy_range: tuple[float, float] = (-1.0, 1.0)
    move_per_turn: float = 0.6       # deslocamento máximo do inimigo por turno
    hide_probability: float = 0.0    # chance de o inimigo ficar invisível em um turno
    hide_turns: int = 2
    read_sigma_distance: float = 0.08
    read_sigma_wind: float = 0.05
    exec_sigma_force: float = 0.5
    target_width: float = 0.35
    turn_timeout_reads: int = 6      # leituras até o turno acabar sem disparo (cronômetro do jogo)
    enemy_turn_reads: int = 2        # leituras do turno do inimigo (o bot confirma o turno em 2)
    left_probability: float = 0.0    # chance de o inimigo estar à esquerda numa batalha
    # diferença entre o "jogo" e o modelo do bot (o bot não conhece estes fatores)
    true_speed_scale: float = 1.03
    true_wind_scale: float = 1.25
    true_drag_scale: float = 0.95


@dataclass
class SimState:
    me_x: float = 1.0
    target_x: float = 10.0
    dy: float = 0.0
    wind_screen: float = 0.0
    hidden_left: int = 0
    turn: int = 0
    my_turn: bool = True
    hits: int = 0
    reads_this_turn: int = 0
    enemy_reads_left: int = 0
    direction: int = 1
    skipped_turns: int = 0
    over: str | None = None
    log: list[dict] = field(default_factory=list)


class SimulatedWorld:
    def __init__(self, base: PhysicsParams, settings: SimSettings | None = None):
        self.s = settings or SimSettings()
        self.rng = random.Random(self.s.seed)
        self.true_params = replace(base, speed_k=base.speed_k * self.s.true_speed_scale,
                                   wind_k=base.wind_k * self.s.true_wind_scale,
                                   drag=base.drag * self.s.true_drag_scale)
        self.state = SimState()
        self.new_battle()

    def new_battle(self, stage: int = 0):
        s, r = self.s, self.rng
        st = SimState(me_x=r.uniform(8.0, 10.0))
        st.direction = -1 if r.random() < s.left_probability else 1
        st.target_x = st.me_x + st.direction * r.uniform(*s.distance_range)
        st.dy = r.uniform(*s.dy_range)
        st.wind_screen = round(r.uniform(-s.wind_max, s.wind_max), 1)
        self.state = st

    def _next_turn(self):
        s, r, st = self.s, self.rng, self.state
        st.turn += 1
        st.reads_this_turn = 0
        st.wind_screen = round(r.uniform(-s.wind_max, s.wind_max), 1)
        d = abs(st.target_x - st.me_x) + r.uniform(-s.move_per_turn, s.move_per_turn)
        d = min(s.distance_range[1], max(s.distance_range[0], d))
        st.target_x = st.me_x + st.direction * d
        if st.hidden_left > 0:
            st.hidden_left -= 1
        elif r.random() < s.hide_probability:
            st.hidden_left = s.hide_turns
        if st.turn >= s.max_turns and st.over is None:
            st.over = "derrota"

    def observe(self) -> BattleObservation:
        st, s, r = self.state, self.s, self.rng
        if st.over:
            return BattleObservation(False, False, battle_over=st.over)
        if not st.my_turn:  # turno do inimigo: algumas leituras
            if st.enemy_reads_left <= 0:
                st.enemy_reads_left = s.enemy_turn_reads
            st.enemy_reads_left -= 1
            if st.enemy_reads_left <= 0:
                st.my_turn = True
                self._next_turn()
            return BattleObservation(True, False)
        st.reads_this_turn += 1
        if st.reads_this_turn > s.turn_timeout_reads:  # tempo do turno esgotou
            st.my_turn = False
            st.skipped_turns += 1
            return BattleObservation(True, False)
        visible = st.hidden_left == 0
        wind_read = st.wind_screen + r.gauss(0, s.read_sigma_wind)
        # coordenadas de tela em régua: y cresce para baixo, o atirador fica em y=0
        obs = BattleObservation(True, True, me_x=st.me_x, me_y=0.0, wind_screen=wind_read, wind_confidence=0.95,
                                confidence=0.95, target_visible=visible)
        if visible:
            measured = st.target_x + r.gauss(0, s.read_sigma_distance)
            obs.direction = 1 if measured >= st.me_x else -1
            obs.distance = abs(measured - st.me_x)
            obs.wind = wind_read * obs.direction
            obs.dy = st.dy
            obs.target_x, obs.target_y = measured, -st.dy
        return obs

    def fire(self, angle: float, force: float, direction: int = 1) -> ShotOutcome:
        from .aiming import hit_half_width
        st, s = self.state, self.s
        f = min(100.0, max(0.0, force + self.rng.gauss(0, s.exec_sigma_force)))
        # o projétil vai para o lado em que o bot atirou; o vento conta relativo a esse lado
        x = float(landing_x(angle, f, st.wind_screen * direction, st.dy, self.true_params))
        true_distance = (st.target_x - st.me_x) * direction  # negativo = atirou para o lado errado
        hit = bool(np.isfinite(x) and abs(x - true_distance) <= hit_half_width(s.target_width, 0.25))
        if hit:
            st.hits += 1
        st.log.append({"turno": st.turn, "angulo": angle, "forca": force, "impacto": x,
                       "alvo": true_distance, "acerto": hit, "oculto": st.hidden_left > 0})
        st.my_turn = False
        if st.hits >= s.target_hp:
            st.over = "vitoria"
        # o impacto é medido em relação ao atirador; distância "vista" é usada como referência
        return ShotOutcome(impact_x=x if np.isfinite(x) else None, hit=hit)


class SimulatedView(BattleView):
    def __init__(self, world: SimulatedWorld):
        self.world = world

    def observe(self):
        return self.world.observe()


class SimulatedShooter(Shooter):
    def __init__(self, world: SimulatedWorld):
        self.world = world

    def shoot(self, angle, force, direction, obs):
        return self.world.fire(angle, force, direction)


@dataclass
class SimReport:
    battles: int
    shots: int
    hits: int
    wins: int
    hit_rate_first_half: float | None
    hit_rate_second_half: float | None
    mean_abs_error_first_half: float | None
    mean_abs_error_second_half: float | None
    shots_hidden: int
    skipped_turns: int = 0

    @property
    def hit_rate(self) -> float | None:
        return self.hits / self.shots if self.shots else None

    def as_dict(self):
        d = self.__dict__.copy()
        d["hit_rate"] = self.hit_rate
        return d


def _half_stats(rows):
    if not rows:
        return None, None
    hits = sum(1 for r in rows if r["acerto"]) / len(rows)
    errs = [abs(r["impacto"] - r["alvo"]) for r in rows if np.isfinite(r["impacto"])]
    return hits, (float(np.mean(errs)) if errs else None)


def run_simulation(kb: KnowledgeBase, params: PhysicsParams, battles: int = 20,
                   settings: SimSettings | None = None, calibrate: bool = True,
                   store_path: Path | None = None, max_steps_per_battle: int = 200) -> SimReport:
    """Executa ``battles`` batalhas em modo automático simulado e devolve estatísticas."""
    settings = settings or SimSettings()
    world = SimulatedWorld(params, settings)
    tmpdir = None
    if store_path is None:
        tmpdir = tempfile.TemporaryDirectory()
        store_path = Path(tmpdir.name) / "sim.sqlite3"
    store = ShotStore(store_path)
    store.clear(source="simulado")
    calibrator = Calibrator(store, params, sources=("simulado",))
    aimer = Aimer(kb, params, calibrator if calibrate else None)
    # configuração isolada: a autorização vale só para o executor simulado
    cfg = Config(data={"automation": {"server_rules_confirmed": True, "min_seconds_between_shots": 0,
                                  "post_shot_wait_s": 0},
                       "aim": {"target_width": settings.target_width},
                       "thresholds": {"auto_min_hit_probability": 0.0}})
    engine = CombatEngine(SimulatedView(world), SimulatedShooter(world), aimer, calibrator,
                          TargetTracker(max_move_per_turn=settings.move_per_turn * 1.2),
                          KillSwitch(), cfg, source="simulado")
    engine.set_mode(Mode.AUTO)
    all_rows, wins, skipped = [], 0, 0
    try:
        for _ in range(battles):
            world.new_battle()
            # como o ActivityRunner (on_battle_start): batalha nova, turno novo. Antes o laço só lia o fim
            # da batalha uma vez, mas o motor exige leituras seguidas para aceitá-lo: o turno da batalha
            # anterior (já com disparo) continuava valendo e o 1º turno de cada batalha era perdido
            engine.reset_battle()
            for _ in range(max_steps_per_battle):
                engine.step()
                if world.state.over:
                    break
            wins += world.state.over == "vitoria"
            skipped += world.state.skipped_turns
            all_rows += world.state.log
    finally:
        store.close()
        if tmpdir is not None:
            tmpdir.cleanup()
    half = len(all_rows) // 2
    h1, e1 = _half_stats(all_rows[:half])
    h2, e2 = _half_stats(all_rows[half:])
    return SimReport(battles, len(all_rows), sum(1 for r in all_rows if r["acerto"]), wins,
                     h1, h2, e1, e2, sum(1 for r in all_rows if r["oculto"]), skipped)


# ------------------------------------------------------------ cliente simulado (telas)
class SimulatedClient:
    """Cliente falso com telas e botões para testar ``ActivityRunner`` de ponta a ponta.

    Instâncias, como no DDClássico: lobby -[botao_cais]-> cais_expedicao -[botao_criar_sala]-> sala (sem
    instância) -[botao_escolher_instancia]-> menu_instancias -[opção, dificuldade]-> sala (com instância)
    -[botao_iniciar]-> carregando -> batalha -> vitoria/derrota -[botao_sair]-> lobby (ou a sala, com
    ``back_to_room``: ela volta com a instância anterior escolhida). Partidas: lobby -[botao_partidas]->
    menu_partidas -[opção]-> sala -[botao_iniciar]-> ... Iniciar numa sala sem instância não faz nada.
    A opção só existe no menu do seu tipo (``partida_*`` no de partidas, as demais na escolha da instância).
    ``faults`` injeta problemas: {"popup_at": n, "unknown_for": leituras,
    "disconnect_at": n, "missing_button": nome, "stage_battles": k, "solo_warning": True}. Com
    ``solo_warning``, Iniciar abre o aviso de instância difícil (um jogador): botao_confirmar_aviso segue,
    botao_fechar volta à sala.
    """

    def __init__(self, world: SimulatedWorld, option="instancia_teste", faults: dict | None = None,
                 loading_reads: int = 2, difficulty: str | None = None, back_to_room: bool = False):
        self.world = world
        self.option = option
        self.difficulty = difficulty   # botão de dificuldade que precisa ser clicado depois da opção
        self.selected: list[str] = []  # opção e dificuldade escolhidas no menu (para conferir nos testes)
        self.room_choice: list[str] | None = None  # o que a sala tem escolhido (None: sala sem instância)
        self.back_to_room = back_to_room
        self.faults = dict(faults or {})
        self.loading_reads = loading_reads
        self.screen = "lobby"
        self.reads = 0
        self.clicks: list[tuple[str, str]] = []
        self.keys: list[str] = []
        self._loading_left = 0
        self._unknown_left = 0
        self._popup = False
        self.stage = 0
        self.battles_started = 0
        self.ignored: set[str] = set()

    # ScreenReader
    def read(self):
        from .activities import ScreenState
        self.reads += 1
        f = self.faults
        if f.get("read_error_at") and self.reads in f["read_error_at"]:
            raise RuntimeError("falha passageira na captura")
        if f.get("window_gone_at") and self.reads >= f["window_gone_at"]:
            return ScreenState("janela_indisponivel", 1.0, None, "a janela do jogo está minimizada")
        if f.get("no_focus_at") and self.reads >= f["no_focus_at"]:
            return ScreenState("janela_sem_foco", 1.0)
        if f.get("flash_at") and self.reads == f["flash_at"][0]:
            return ScreenState(f["flash_at"][1], 0.95)  # um quadro falso isolado
        if f.get("disconnect_at") and self.reads >= f["disconnect_at"]:
            return ScreenState("desconectado", 0.95)
        if f.get("popup_at") and self.reads == f["popup_at"]:
            self._popup = True
        if f.get("unknown_at") and self.reads == f["unknown_at"]:
            self._unknown_left = int(f.get("unknown_for", 3))
        if self._unknown_left > 0:
            self._unknown_left -= 1
            return ScreenState("lobby", 0.3)  # leitura fraca = desconhecido
        if self._popup:
            return ScreenState("desconhecido", 0.2)
        if self.screen == "carregando":
            self._loading_left -= 1
            if self._loading_left <= 0:
                self._start_battle()
        if self.screen == "batalha" and self.world.state.over:
            result = self.world.state.over
            stages = int(self.faults.get("stage_battles", getattr(self.world, "stage_count", 1)))
            if result == "vitoria" and self.stage + 1 < stages:
                self.stage += 1
                self.screen = "etapa_concluida"
            elif f.get("skip_result"):
                self.screen = "lobby"  # o jogo volta direto, sem tela de resultado reconhecível
            else:
                self.screen = result
        return ScreenState(self.screen, 0.95)

    def _start_battle(self):
        self.world.new_battle(self.stage)
        self.battles_started += 1
        self.screen = "batalha"

    # Actor
    def click(self, template, frame=None) -> bool:
        if template == self.faults.get("missing_button"):
            return False
        if template == self.faults.get("focus_lost_on"):
            from .automation.safety import FocusLost
            raise FocusLost("a janela do jogo não está na frente")
        if template == self.faults.get("ignore_first_click") and template not in self.ignored:
            self.ignored.add(template)  # o jogo "perdeu" o clique (atraso)
            self.clicks.append((self.screen, template + ":ignorado"))
            return True
        if self._popup:
            if template == "botao_fechar":
                self._popup = False
                self.clicks.append((self.screen, template))
                return True
            return False
        menu = "menu_partidas" if self.option.startswith("partida_") else "menu_instancias"
        hidden = set(self.faults.get("menu_hides", ()))  # opções/dificuldades que este "cliente" não tem
        if self.screen == menu and template in hidden:
            return False
        if self.screen == menu and template == self.option and self.difficulty:
            self.selected = [template]  # escolhe a instância; a sala só abre depois da dificuldade
            self.clicks.append((self.screen, template))
            return True
        if self.screen == menu and self.difficulty and template == self.difficulty:
            if self.selected != [self.option]:
                return False
            self.selected.append(template)
            self.clicks.append((self.screen, template))
            self.room_choice = list(self.selected)
            self.screen = "sala"
            return True
        if self.screen == menu and template.startswith("dificuldade_"):
            return False  # outra dificuldade não é a que esta atividade pede
        if self.screen == "sala" and template == "botao_iniciar" and self.room_choice is None:
            return False  # sala sem instância escolhida: o jogo não inicia
        if self.screen == "sala" and template == "botao_iniciar" and self.faults.get("solo_warning"):
            self.clicks.append((self.screen, template))
            self.screen = "aviso_sozinho"
            return True
        if self.screen == "aviso_sozinho" and template in ("botao_confirmar_aviso", "botao_fechar"):
            self.clicks.append((self.screen, template))
            if template == "botao_fechar":
                self.screen = "sala"
                return True
            self._loading_left, self.stage, self.screen = self.loading_reads, 0, "carregando"
            return True
        end = "sala" if self.back_to_room else "lobby"
        nxt = {("lobby", "botao_cais"): "cais_expedicao",
               ("cais_expedicao", "botao_criar_sala"): "sala",
               ("sala", "botao_escolher_instancia"): "menu_instancias",
               ("lobby", "botao_partidas"): "menu_partidas",
               (menu, self.option): "sala",
               ("sala", "botao_iniciar"): "carregando",
               ("etapa_concluida", "botao_continuar"): "carregando",
               ("vitoria", "botao_sair"): end, ("derrota", "botao_sair"): end,
               ("recompensa", "botao_sair"): end}.get((self.screen, template))
        if nxt is None:
            return False
        self.clicks.append((self.screen, template))
        if (self.screen, nxt) in (("cais_expedicao", "sala"), ("lobby", "menu_partidas")):
            self.room_choice = None  # sala nova
        if self.screen in ("menu_instancias", "menu_partidas") and nxt == "sala":
            self.room_choice = [template]
        if nxt == "carregando":
            self._loading_left = self.loading_reads
            if self.screen == "sala":
                self.stage = 0
        self.screen = nxt
        return True

    def press(self, key):
        self.keys.append(key)
        if self._popup and key == "esc":
            self._popup = False


# ------------------------------------------------------- instâncias simuladas (estratégias)
@dataclass
class SimEnemy:
    role: str
    x: float
    hp: int = 1
    y: float = 0.0
    advance: float = 0.0          # quanto anda na direção do seu personagem por turno
    hidden: int = 0               # turnos ainda invisível
    status: str | None = None     # estado ativo agora (chave do perfil)
    status_key: str | None = None  # estado que alterna (ex.: escudo do Barão)
    status_every: int = 0         # alterna o estado a cada N turnos (0 = nunca)
    becomes: str | None = None    # ao morrer vira outro papel (segunda vida, ex.: Midas vermelho)
    avoid: bool = False           # não pode ser atingido (ex.: o juiz); não conta para vencer


# Cenários FICTÍCIOS para a demonstração e os testes: usam os papéis e estados de cada perfil
# para exercitar a estratégia (etapas, prioridade, imunidade, tiro por cima, perseguição). Vida,
# posições e quantidades não são dados do jogo.
DEMO_SCENARIOS = {
    "formigueiro": [
        {"inimigos": [("formiga", 3, {})], "vence": None},
        {"inimigos": [("rainha", 1, {"hp": 3}), ("formiga", 2, {})], "vence": ["rainha"]},
    ],
    "galinheiro": [
        {"inimigos": [("frango", 3, {"advance": 0.5})], "vence": None},
        {"inimigos": [("galo", 1, {"hp": 2, "advance": 0.4}), ("galinha", 2, {"advance": 0.4})], "vence": None},
        {"inimigos": [("construcao", 1, {"hp": 3})], "vence": None},
        {"inimigos": [("chefe", 1, {"hp": 3, "advance": 0.2}), ("gaiola", 1, {"hp": 2})], "vence": None},
    ],
    # as dificuldades seguem as etapas de cada perfil (fontes de 2013 e o emulador; ver instances.json)
    "galinheiro_facil": [
        {"inimigos": [("frango", 3, {"advance": 0.5})], "vence": None},
        {"inimigos": [("chefe", 1, {"hp": 3, "advance": 0.2}), ("gaiola", 1, {"hp": 2})], "vence": None},
    ],
    "galinheiro_normal": [
        {"inimigos": [("frango", 4, {"advance": 0.5})], "vence": None},
        {"inimigos": [("construcao", 1, {"hp": 3})], "vence": None},
        {"inimigos": [("chefe", 1, {"hp": 3, "advance": 0.2}), ("gaiola", 1, {"hp": 2})], "vence": None},
    ],
    "galinheiro_dificil": [
        {"inimigos": [("frango", 4, {"advance": 0.6})], "vence": None},
        {"inimigos": [("galo", 1, {"hp": 2, "advance": 0.4}), ("galinha", 2, {"advance": 0.4})], "vence": None},
        {"inimigos": [("chefe", 1, {"hp": 4, "advance": 0.2}), ("gaiola", 1, {"hp": 2})], "vence": None},
        {"inimigos": [("construcao", 1, {"hp": 3})], "vence": None},
    ],
    # balões: "pontos" é a meta da etapa (no jogo, 99); os verdes tiram pontos. Corrida: os rivais andam até o
    # pódio (do seu lado) e chegar lá é derrota. Boxiador com duas vidas e o juiz, que não pode ser atingido.
    "olimpiadas_bugou_normal": [
        {"inimigos": [("balao_vermelho", 4, {}), ("balao_verde", 3, {}), ("balao_dobro", 1, {})], "vence": None,
         "pontos": 9},
        {"inimigos": [("bugou_rival", 3, {"advance": 0.35})], "vence": None},
        {"inimigos": [("boxiador", 1, {"hp": 2, "becomes": "boxiador"}), ("juiz", 1, {"avoid": True})],
         "vence": ["boxiador"]},
    ],
    "bugou_normal": [
        {"inimigos": [("bugou", 3, {})], "vence": None},
        {"inimigos": [("barao", 1, {"hp": 3, "status": "barao_escudo", "status_every": 2}), ("bugou", 1, {})],
         "vence": ["barao"]},
        {"inimigos": [("midas", 1, {"hp": 2, "status": "midas_escudo", "status_every": 3,
                                    "becomes": "midas_vermelho"})], "vence": ["midas", "midas_vermelho"]},
        {"inimigos": [("matias", 1, {"hp": 3}), ("bomba", 1, {})], "vence": ["matias"]},
    ],
}


class InstanceWorld(SimulatedWorld):
    """Batalha simulada com vários inimigos, etapas e estados, decidida pela mesma estratégia
    (``StrategyPlanner``) usada no jogo real. ``fuse_at``: (etapa, turno) em que o Matias acende
    o pavio (estado "pausar"), para testar a pausa."""

    def __init__(self, base: PhysicsParams, profile, planner, settings: SimSettings | None = None,
                 fuse_at: tuple[int, int] | None = None):
        self.profile = profile
        self.planner = planner
        self.scenario = scenario_for(profile)
        self.stage_count = len(self.scenario)
        self.fuse_at = fuse_at
        self.enemies: list[SimEnemy] = []
        self.stage = 0
        self.plans: list = []
        self.shots_log: list[dict] = []  # disparos de todas as batalhas (o estado é zerado a cada uma)
        self.score = 0.0                 # pontos da etapa de pontuação
        self.bad_hits = 0                # alvos que tiram pontos atingidos (a estratégia deve evitar)
        self.avoid_hits = 0              # papéis que não podiam ser atingidos (ex.: o juiz acordado)
        super().__init__(base, settings or SimSettings(max_turns=40, distance_range=(4.0, 12.0)))

    def new_battle(self, stage: int = 0):
        super().new_battle()
        r, st = self.rng, self.state
        st.me_x = r.uniform(0.8, 1.5)
        self.stage = min(stage, self.stage_count - 1)
        self.enemies = []
        self.score = 0.0
        self._spawn()

    def _spawn(self):
        r, st = self.rng, self.state
        for role, n, kw in self.scenario[self.stage]["inimigos"]:
            kw = dict(kw)
            if "status" in kw:
                kw["status_key"] = kw.pop("status")
            for _ in range(n):
                e = SimEnemy(role, st.me_x + r.uniform(*self.s.distance_range), y=-r.uniform(-0.6, 0.6), **kw)
                e.status = e.status_key
                if e.avoid:
                    # longe do chefe o bastante para dar para mirar nele (no jogo real, o juiz anda pela arena)
                    others = [o.x for o in self.enemies if not o.avoid] or [st.me_x + 6]
                    e.x = max(others) + 2.5
                self.enemies.append(e)

    def _points(self, role) -> float:
        rule = self.profile.roles.get(role)
        return float(rule.points or 0) if rule is not None else 0.0

    def extinguish(self):
        """O usuário usou o gelo: o pavio apagou."""
        for e in self.enemies:
            if e.status == "matias_pavio":
                e.status = None

    def _next_turn(self):
        super()._next_turn()
        st, r = self.state, self.rng
        for e in self.enemies:
            if e.advance:
                e.x = max(st.me_x + 0.5, e.x - e.advance)
            if e.status_every and e.status != "matias_pavio":
                e.status = e.status_key if (st.turn // e.status_every) % 2 == 0 else None
            if e.hidden:
                e.hidden -= 1
            elif self.profile.roles.get(e.role) and self.profile.roles[e.role].boss \
                    and r.random() < self.s.hide_probability:
                e.hidden = self.s.hide_turns
        if self.fuse_at and (self.stage, st.turn) == self.fuse_at:
            for e in self.enemies:
                if e.role == "matias":
                    e.status = "matias_pavio"
        if any(e.advance and e.x - st.me_x < 0.8 for e in self.enemies) and st.over is None:
            st.over = "derrota"  # os frangos alcançaram o seu personagem
        st.target_x = st.me_x + 5  # não usado (a estratégia escolhe entre os inimigos)

    def observe(self) -> BattleObservation:
        from .strategy import apply_plan
        from .vision.perception import Character
        st, s, r = self.state, self.s, self.rng
        if st.over or not st.my_turn:
            return super().observe()
        st.reads_this_turn += 1
        if st.reads_this_turn > s.turn_timeout_reads:
            st.my_turn = False
            st.skipped_turns += 1
            return BattleObservation(True, False)
        me = Character(st.me_x, 0.0, 0.95, "eu", "simulado")
        seen = [(e, Character(e.x + r.gauss(0, s.read_sigma_distance), e.y, 0.95, e.role, "simulado"))
                for e in self.enemies if not e.hidden]
        statuses = [Character(c.x, c.y, 0.95, e.status, "simulado") for e, c in seen if e.status]
        plan = self.planner.update([c for _, c in seen], statuses, me, 1.0)
        self.plans.append(plan)
        wind_read = st.wind_screen + r.gauss(0, s.read_sigma_wind)
        obs = BattleObservation(True, True, me_x=st.me_x, me_y=0.0, wind_screen=wind_read, wind_confidence=0.95,
                                confidence=0.95)
        target = apply_plan(obs, plan)
        obs.target_id = f"{plan.role or 'alvo'}"
        if target is None:
            obs.target_visible = False
            return obs
        obs.direction = 1 if target.x >= st.me_x else -1
        obs.distance = abs(target.x - st.me_x)
        obs.wind = wind_read * obs.direction
        obs.dy = -target.y
        obs.target_x, obs.target_y = target.x, target.y
        return obs

    def fire(self, angle: float, force: float, direction: int = 1) -> ShotOutcome:
        from .aiming import hit_half_width
        st, s = self.state, self.s
        f = min(100.0, max(0.0, force + self.rng.gauss(0, s.exec_sigma_force)))
        wind = st.wind_screen * direction
        hw = hit_half_width(s.target_width, 0.25)
        lands = {}
        for e in self.enemies:  # o projétil cai na altura de cada inimigo
            xe = float(landing_x(angle, f, wind, -e.y, self.true_params))
            if np.isfinite(xe) and abs(e.x - (st.me_x + direction * xe)) <= hw:
                lands[id(e)] = abs(e.x - (st.me_x + direction * xe))
        x = float(landing_x(angle, f, wind, 0.0, self.true_params))
        land = st.me_x + direction * x if np.isfinite(x) else float("nan")
        near = [e for e in self.enemies if id(e) in lands]
        hit = bool(near)
        damaged = blocked = False
        if near:
            e = min(near, key=lambda e: lands[id(e)])
            rule = self.profile.statuses.get(e.status) if e.status else None
            blocked = rule is not None and (rule.effect == "imune" or (rule.effect == "so_por_cima" and angle < 60))
            if e.avoid:
                blocked, hit = True, False
                self.avoid_hits += 1
                if self.avoid_hits >= 3 and st.over is None:
                    st.over = "derrota"  # o juiz acordado pela 3ª vez: o personagem morre
            elif not blocked:
                damaged = True
                e.hp -= 1
                points = self._points(e.role)
                self.score += points
                self.bad_hits += points < 0
                if e.hp <= 0:
                    self.enemies.remove(e)
                    if e.becomes:
                        self.enemies.append(SimEnemy(e.becomes, e.x, 2, e.y, status_key=e.status_key,
                                                     status_every=e.status_every))
        st.hits += damaged
        st.log.append({"turno": st.turn, "angulo": angle, "forca": force, "impacto": x,
                       "alvo": abs(land - st.me_x) if np.isfinite(land) else 0.0, "acerto": hit,
                       "oculto": False, "dano": damaged, "bloqueado": blocked})
        self.shots_log.append(st.log[-1])
        st.my_turn = False
        stage = self.scenario[self.stage]
        wins = stage["vence"]
        alive = [e for e in self.enemies if not e.avoid and (wins is None or e.role in wins)]
        goal = stage.get("pontos")
        if goal is not None:
            if self.score >= goal and st.over is None:
                st.over = "vitoria"
            elif not any(self._points(e.role) > 0 for e in self.enemies):
                self._spawn()  # acabaram os balões bons antes da meta: aparecem outros
        elif not alive and st.over is None:
            st.over = "vitoria"
        return ShotOutcome(impact_x=x if np.isfinite(x) else None, hit=damaged)


def demo_option(definition, default="instancia_teste") -> str:
    """Opção (modelo do menu) que a definição clica: o cliente simulado a mostra no menu certo."""
    return next((a.target for acts in definition.flow.values() for a in acts
                 if a.kind == "clicar" and a.target and a.target.startswith(("instancia_", "partida_"))), default)


def demo_difficulty(definition) -> str | None:
    """Botão de dificuldade que a definição clica (atividades pré-cadastradas), se houver."""
    return next((a.target for acts in definition.flow.values() for a in acts
                 if a.kind == "clicar" and a.target and a.target.startswith("dificuldade_")), None)


def scenario_for(profile):
    """Cenário de demonstração do perfil: o dele ou o da instância de que ele herdou."""
    for key in (profile.key, profile.base, profile.models):
        if key and key in DEMO_SCENARIOS:
            return DEMO_SCENARIOS[key]
    return None


def simulated_activity(kb: KnowledgeBase, params: PhysicsParams, definition, runs=2, faults=None,
                       settings: SimSettings | None = None, calibrate=True, store_path: Path | None = None,
                       limits=None, config_overrides: dict | None = None, profile=None, fuse_at=None,
                       on_event=None):
    """Monta ``ActivityRunner`` + combate sobre o cliente simulado (sem tempo real).

    Com ``profile`` (``strategy.InstanceProfile``), a batalha tem vários inimigos e etapas e
    quem decide o alvo é a mesma estratégia usada no jogo real.
    """
    from .activities import ActivityRunner, RunLimits

    planner = None
    if profile is not None:
        from .strategy import StrategyPlanner
        planner = StrategyPlanner(profile, has_template=lambda name: True,
                                  on_event=lambda kind, msg: on_event(kind, msg) if on_event else None)
        world = InstanceWorld(params, profile, planner, settings, fuse_at=fuse_at)
        settings = world.s
    else:
        settings = settings or SimSettings()
        world = SimulatedWorld(params, settings)
    client = SimulatedClient(world, option=demo_option(definition), faults=faults,
                             difficulty=demo_difficulty(definition))
    tmpdir = None
    if store_path is None:
        tmpdir = tempfile.TemporaryDirectory()
        store_path = Path(tmpdir.name) / "sim.sqlite3"
    store = ShotStore(store_path)
    calibrator = Calibrator(store, params, sources=("simulado",))
    data = {"automation": {"server_rules_confirmed": True, "min_seconds_between_shots": 0,
                                  "post_shot_wait_s": 0},
            "aim": {"target_width": settings.target_width},
            "thresholds": {"auto_min_hit_probability": 0.0}}
    for k, v in (config_overrides or {}).items():
        data.setdefault(k, {}).update(v)
    cfg = Config(data=data)
    kill = KillSwitch()
    engine = CombatEngine(SimulatedView(world), SimulatedShooter(world), Aimer(kb, params,
                          calibrator if calibrate else None), calibrator,
                          TargetTracker(max_move_per_turn=settings.move_per_turn * 1.2), kill, cfg,
                          source="simulado")
    engine.set_mode(Mode.AUTO)
    engine.planner = planner
    clock = FakeClock()

    def battle_start():
        engine.reset_battle()
        if planner is not None:
            planner.on_battle_start()
    runner = ActivityRunner(definition, client, client, engine.step, kill, cfg,
                            limits or RunLimits(runs=runs), clock=clock, on_battle_start=battle_start,
                            on_activity_start=planner.reset_run if planner is not None else None)
    # sem esperas reais: o relógio falso avança a cada pausa
    runner._sleep = lambda s: clock.advance(max(s, 0.05))  # type: ignore[method-assign]
    runner.POLL_S = 0.4

    def cleanup():
        store.close()
        if tmpdir is not None:
            tmpdir.cleanup()
    return runner, client, engine, clock, cleanup


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


def drive(runner, max_steps=20000):
    """Executa o runner passo a passo até terminar, pausar ou atingir ``max_steps``."""
    from .activities import RunCounters, RunStatus

    ok, why = runner.check_allowed()
    if not ok:
        runner.status, runner.reason = RunStatus.FAILED, why
        return runner.status
    runner.status = RunStatus.RUNNING
    runner.counters = RunCounters(started_at=runner.clock(), clock=runner.clock)
    for _ in range(max_steps):
        if not runner.run_once() or runner.status == RunStatus.PAUSED:
            break
    return runner.status
