"""Regressões do combate automático (revisão do Formigueiro Fácil na 0.5.1).

Cada teste reproduz um estado em que o bot ficava parado sem pausar nem dizer o motivo, ou em que uma
recuperação podia cancelar a operação. Nada aqui foi conferido no cliente real: são leituras simuladas.
"""
from types import SimpleNamespace

import pytest

from ddbot.activities import ActivityRunner, RunLimits, RunStatus, ScreenState, activity_from_option
from ddbot.aiming import Aimer
from ddbot.automation.safety import Aborted, FocusLost, InputBlocked, KillSwitch, NeedsAttention
from ddbot.calibration import Calibrator, ShotStore
from ddbot.combat import BattleObservation, BattleView, CombatEngine, Mode, Shooter, ShotOutcome
from ddbot.config import Config
from ddbot.game_io import VisionBattleView
from ddbot.readiness import check
from ddbot.strategy import StrategyPlanner, apply_plan, load_profiles
from ddbot.tracking import TargetTracker
from ddbot.vision.perception import Character, Snapshot

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


class ScriptView(BattleView):
    def __init__(self, seq):
        self.seq = list(seq)

    def observe(self):
        return self.seq.pop(0) if len(self.seq) > 1 else self.seq[0]


class CountShooter(Shooter):
    def __init__(self, error=None):
        self.shots = []
        self.error = error

    def shoot(self, angle, force, direction, obs):
        self.shots.append((angle, force, direction))
        if self.error is not None:
            raise self.error
        return ShotOutcome()


def _engine(tmp_path, kb, params, seq, shooter=None, **auto):
    cal = Calibrator(ShotStore(tmp_path / "c.sqlite3"), params)
    cfg = Config(data={"automation": {"server_rules_confirmed": True, "min_seconds_between_shots": 0,
                                      "post_shot_wait_s": 0, **auto}})
    eng = CombatEngine(ScriptView(seq), shooter or CountShooter(), Aimer(kb, params, cal), cal, TargetTracker(),
                       KillSwitch(), cfg)
    events = []
    eng.on_event = events.append
    clock = [0.0]
    eng.clock = lambda: clock[0]
    assert eng.set_mode(Mode.AUTO)[0]
    return eng, events, clock


def mine(**kw):
    base = dict(in_battle=True, my_turn=True, distance=8.0, wind=0.5, me_x=1, target_x=9, target_y=0, confidence=0.95)
    base.update(kw)
    return BattleObservation(**base)


ENEMY = BattleObservation(True, False)


# ------------------------------------------------------------------- turno
def test_turn_never_recognized_warns_with_score_and_pauses(tmp_path, kb, params):
    """O indicador é lido, mas nunca casa: antes o bot ficava até o limite da batalha (15 min) sem dizer nada."""
    eng, events, clock = _engine(tmp_path, kb, params, [BattleObservation(True, False, turn_score=0.55)])
    eng.step()
    clock[0] = eng.NO_TURN_WARN_S + 1
    eng.step()
    warn = [e.message for e in events if "sem reconhecer o seu turno" in e.message]
    assert warn and "0,55" in warn[0] and "mínimo 0,80" in warn[0]
    clock[0] = eng.NO_TURN_PAUSE_S + 1
    with pytest.raises(NeedsAttention, match="sem reconhecer o seu turno"):
        eng.step()


def test_turn_timer_restarts_after_each_of_my_turns(tmp_path, kb, params):
    eng, events, clock = _engine(tmp_path, kb, params, [ENEMY, mine(), mine(), ENEMY, ENEMY, ENEMY])
    eng.step()
    clock[0] = 50.0
    eng.step()
    eng.step()  # seu turno confirmado (e o disparo): o tempo sem turno recomeça
    clock[0] = 51.0
    eng.step()
    eng.step()  # o turno passou
    clock[0] = 51.0 + eng.NO_TURN_WARN_S - 1
    eng.step()
    assert not any("sem reconhecer" in e.message for e in events)
    assert any("disparo confirmado" in e.message for e in events)


# ------------------------------------------------------------- alvo ausente
def test_no_target_of_the_stage_pauses_after_three_turns(tmp_path, kb, params):
    """Estratégia sem alvo visível: antes esperava turno após turno, sem pausar."""
    snap = SimpleNamespace(enemies=[], me=SimpleNamespace(x=1), unit_px=10.0)
    waiting = mine(distance=None, target_x=None, wait_reason="nenhum alvo da etapa Formigas visível",
                   target_missing=True, snapshot=snap)
    seq = [waiting, waiting, ENEMY, ENEMY] * 3
    sh = CountShooter()
    eng, events, _ = _engine(tmp_path, kb, params, seq, sh)
    with pytest.raises(NeedsAttention, match="nenhum inimigo foi encontrado"):
        for _ in range(len(seq)):
            eng.step()
    assert sh.shots == [] and sum("aguardando" in e.message for e in events) == 3


def test_legit_wait_does_not_pause(tmp_path, kb, params):
    """Espera da estratégia com alvo na tela (chefe imune, por exemplo) continua só avisando."""
    immune = mine(distance=None, target_x=None, wait_reason="Barão imune agora: aguardando")
    seq = [immune, immune, ENEMY, ENEMY] * 4
    eng, events, _ = _engine(tmp_path, kb, params, seq)
    for _ in range(len(seq)):
        eng.step()
    assert sum("imune" in e.message for e in events) == 4


def test_planner_marks_missing_target(tmp_path):
    profiles, errors = load_profiles(ROOT / "data" / "knowledge" / "instances.json")
    assert not errors
    planner = StrategyPlanner(profiles["formigueiro_facil"], has_template=lambda n: True)
    plan = planner.update([], [], Character(10, 10, 0.9, "eu", "modelo"), 50.0)
    obs = BattleObservation(True, True)
    assert apply_plan(obs, plan) is None
    assert obs.target_missing and "Formigas" in obs.wait_reason


# --------------------------------------------------------- leitura e disparo
def test_unread_wind_names_the_reading_and_pauses(tmp_path, kb, params):
    """Vento não lido: antes "confiança visual baixa (0.00 < 0.7)" em todo turno, sem pausar nem dizer qual."""
    weak = mine(confidence=0.0, weak_reads=["vento não reconhecido (treine os dígitos do vento)"])
    seq = [weak, weak, weak, weak, ENEMY, ENEMY, weak, weak, weak, weak]
    sh = CountShooter()
    eng, events, _ = _engine(tmp_path, kb, params, seq, sh, bad_read_seconds=0)
    with pytest.raises(NeedsAttention, match="treine os dígitos do vento"):
        for _ in range(len(seq)):
            eng.step()
    assert sh.shots == []
    assert any("disparo não executado" in e.message and "vento" in e.message for e in events)


def test_cancelled_shot_counts_and_pauses(tmp_path, kb, params):
    """Ângulo não confirmado (ou outra trava do disparo): um cancelamento por turno, depois pausa."""
    sh = CountShooter(error=Aborted("ângulo não confirmado na tela (queria 45, lido 40)"))
    seq = [mine(), mine(), mine(), ENEMY, ENEMY, mine(), mine()]
    eng, events, _ = _engine(tmp_path, kb, params, seq, sh)
    with pytest.raises(NeedsAttention, match="ângulo não confirmado"):
        for _ in range(len(seq)):
            eng.step()
    assert len(sh.shots) == 2  # nunca duas tentativas no mesmo turno


@pytest.mark.parametrize("error", [FocusLost("a janela do jogo não está na frente"),
                                   InputBlocked("o Windows bloqueou o envio de teclas")])
def test_focus_and_blocked_input_reach_the_routine(tmp_path, kb, params, error):
    """Janela sem foco e entrada bloqueada sobem para a rotina (que pausa) e não liberam outro disparo."""
    sh = CountShooter(error=error)
    eng, _, _ = _engine(tmp_path, kb, params, [mine()], sh)
    eng.step()
    with pytest.raises(type(error)):
        eng.step()
    eng.step()
    assert len(sh.shots) == 1


def test_unconfirmed_shot_warns_then_pauses(tmp_path, kb, params):
    """O turno continua seu depois do disparo (teclas não chegaram ao jogo): avisa e, na segunda vez, pausa."""
    seq = [mine(), mine(), mine(), ENEMY, ENEMY, mine(), mine(), mine()]
    sh = CountShooter()
    eng, events, clock = _engine(tmp_path, kb, params, seq, sh)
    eng.step()
    eng.step()  # dispara
    assert len(sh.shots) == 1
    clock[0] = eng.SHOT_CONFIRM_S + 1
    eng.step()
    assert any("não foi confirmado" in e.message for e in events)
    eng.step()
    eng.step()  # o turno passou (pelo relógio do jogo, por exemplo)
    eng.step()
    eng.step()  # novo turno: segundo disparo
    assert len(sh.shots) == 2
    clock[0] = 2 * (eng.SHOT_CONFIRM_S + 1)
    with pytest.raises(NeedsAttention, match="sem confirmação"):
        eng.step()


def test_shot_confirmed_when_turn_passes(tmp_path, kb, params):
    seq = [mine(), mine(), ENEMY, ENEMY]
    eng, events, _ = _engine(tmp_path, kb, params, seq)
    for _ in range(4):
        eng.step()
    assert any(e.message == "disparo confirmado: o turno passou" for e in events)
    assert not any("não foi confirmado" in e.message for e in events)


def test_vision_view_lists_weak_reads(tmp_path):
    """A observação da tela diz qual leitura ficou abaixo do mínimo (aqui, o vento sem direção)."""
    snap = Snapshot(width=1000, height=600, state="batalha", my_turn=True, turn_confidence=0.95,
                    wind=None, me=Character(100, 300, 0.9, "eu", "modelo"),
                    enemies=[Character(600, 300, 0.6, "inimigo", "modelo")], unit_px=100.0,
                    warnings=["vento 2 com direção incerta (capture as setas do vento)"])
    perception = SimpleNamespace(analyze=lambda frame: snap, manual_target=None,
                                 target=lambda s: s.enemies[0])
    source = SimpleNamespace(grab=lambda: object())
    view = VisionBattleView(source, perception, Config(data={}))
    obs = view.observe()
    assert obs.confidence == 0.0 and obs.turn_score == 0.95
    assert obs.weak_reads == ["alvo 0,60", "vento 2 com direção incerta (capture as setas do vento)"]


# ---------------------------------------------------------------- rotina
class Reader:
    def __init__(self, states, clock):
        self.states, self.clock = list(states), clock

    def read(self):
        st = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return ScreenState(st, 0.95 if st != "desconhecido" else 0.3, object())


class Actor:
    def __init__(self, found=("botao_fechar",)):
        self.clicks, self.found = [], set(found)

    def click(self, template, frame):
        self.clicks.append(template)
        return template in self.found

    def press(self, key):
        self.clicks.append(f"tecla:{key}")


def _runner(states, combat_step=lambda allow_fire=True: None, actor=None, **cfg):
    clock = [1000.0]
    d = activity_from_option("instancia_formigueiro", "Formigueiro")
    config = Config(data={"automation": {"server_rules_confirmed": True}, "instances": cfg})
    actor = actor or Actor()
    def tick():  # cada consulta anda 0,25 s: nenhuma espera da rotina fica parada no tempo
        clock[0] += 0.25
        return clock[0]
    r = ActivityRunner(d, Reader(states, clock), actor, combat_step, KillSwitch(), config,
                       RunLimits(runs=1), clock=tick)
    r.POLL_S = r.COMBAT_POLL_S = 0
    r.status = RunStatus.RUNNING
    return r, actor


def _drive(r, steps=400):
    for _ in range(steps):
        if not r.run_once() or r.status == RunStatus.PAUSED:
            break
    return r.status


def test_unknown_screen_in_battle_pauses_without_clicking_close():
    """Mudança inesperada de tela na batalha: pausa; o X reconhecido não é clicado (pode sair da batalha)."""
    r, actor = _runner(["batalha"] * 3 + ["desconhecido"])
    assert _drive(r) == RunStatus.PAUSED
    assert "botao_fechar" not in actor.clicks and "desconhecida" in r.reason


def test_solo_warning_without_confirm_button_pauses_without_cancelling():
    """Aviso de um jogador com permissão, mas sem o botão de confirmar: o X cancelaria a operação; pausa."""
    r, actor = _runner(["aviso_sozinho"], confirm_solo_warning=True)
    assert _drive(r) == RunStatus.PAUSED
    assert "botao_fechar" not in actor.clicks
    assert actor.clicks and set(actor.clicks) == {"botao_confirmar_aviso"}


def test_blocked_input_during_combat_pauses_the_routine():
    def step(allow_fire=True):
        raise InputBlocked("o Windows bloqueou o envio de teclas/cliques")
    r, _ = _runner(["batalha"], combat_step=step)
    assert _drive(r) == RunStatus.PAUSED and "bloqueou" in r.reason


# --------------------------------------------------------------- calibração
def test_generic_enemy_marker_optional_when_instance_targets_cover_every_stage():
    profiles, _ = load_profiles(ROOT / "data" / "knowledge" / "instances.json")
    prof = profiles["formigueiro_facil"]
    d = activity_from_option("instancia_formigueiro", "Formigueiro Fácil", strategy=prof.key)

    def req(templates):
        miss = check(d, lambda n: n in templates, Config(data={}), True, True, profile=prof)
        return {m.key for m in miss if m.required}

    assert "marcador_inimigo" in req(set())
    assert "marcador_inimigo" in req({"alvo_formigueiro_formiga"})  # a etapa da rainha ficaria sem alvo
    both = {"alvo_formigueiro_formiga", "alvo_formigueiro_rainha"}
    assert "marcador_inimigo" not in req(both)
    assert "marcador_eu" in req(both)  # o seu personagem continua obrigatório
