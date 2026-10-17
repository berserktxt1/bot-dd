import threading
import time

import pytest

from ddbot.aiming import Aimer
from ddbot.automation.input import InputController, RecordingBackend
from ddbot.automation.safety import Aborted, KillSwitch, TurnGate
from ddbot.calibration import Calibrator, ShotStore
from ddbot.combat import BattleObservation, BattleView, CombatEngine, Mode, Shooter, ShotOutcome
from ddbot.config import Config
from ddbot.tracking import TargetTracker


def test_killswitch_interrupts_sleep():
    k = KillSwitch()
    threading.Timer(0.05, k.trigger).start()
    t = time.monotonic()
    with pytest.raises(Aborted):
        k.sleep(5)
    assert time.monotonic() - t < 1
    k.reset()
    k.check()


def test_turn_gate_one_shot_per_turn():
    g = TurnGate(0, confirm=1)
    g.update(True)
    assert g.can_shoot()[0]
    g.mark_shot()
    assert not g.can_shoot()[0]
    g.update(True)
    assert not g.can_shoot()[0]  # mesmo turno
    g.update(False)
    assert not g.can_shoot()[0]
    g.update(True)
    assert g.can_shoot()[0]


def test_turn_gate_debounce():
    """Uma leitura isolada (None/False) não cria turno novo nem libera um segundo disparo."""
    g = TurnGate(0, confirm=2)
    g.update(True)
    assert not g.my_turn  # um quadro só não basta
    g.update(True)
    assert g.my_turn and g.can_shoot()[0]
    g.mark_shot()
    for reading in (None, True, False, True, None, True):
        g.update(reading)
        assert not g.can_shoot()[0]
    g.update(False)
    g.update(False)
    assert not g.my_turn
    g.update(True)
    g.update(True)
    assert g.can_shoot()[0] and g.turn_id == 2


def test_kill_callbacks_do_not_leak():
    import gc
    k = KillSwitch()
    for _ in range(50):
        InputController(k, RecordingBackend())
    gc.collect()
    k.trigger()
    assert len(k._callbacks) == 0


def test_input_releases_keys_on_kill_and_checks_focus():
    k = KillSwitch()
    be = RecordingBackend()
    focus = {"ok": True}
    inp = InputController(k, be, foreground_check=lambda: focus["ok"], key_delay_s=0.001)
    inp.key_down("space")
    k.trigger()
    assert ("key", "space", True) in be.events
    with pytest.raises(Aborted):
        inp.tap("up")
    k.reset()
    focus["ok"] = False
    with pytest.raises(Aborted):
        inp.tap("up")
    with pytest.raises(Aborted):
        inp.hold("space", 1.0)


def test_hold_stops_when_focus_lost():
    k = KillSwitch()
    be = RecordingBackend()
    state = {"n": 0}

    def fg():
        state["n"] += 1
        return state["n"] < 5
    inp = InputController(k, be, foreground_check=fg, key_delay_s=0.001)
    with pytest.raises(Aborted):
        inp.hold("space", 2.0)
    assert be.events[-1] == ("key", "space", True)  # tecla solta mesmo abortando


class ScriptView(BattleView):
    def __init__(self, seq):
        self.seq = list(seq)

    def observe(self):
        return self.seq.pop(0) if len(self.seq) > 1 else self.seq[0]


class CountShooter(Shooter):
    def __init__(self):
        self.shots = []

    def shoot(self, angle, force, direction, obs):
        self.shots.append((angle, force, direction))
        return ShotOutcome(impact_x=obs.distance, hit=True)


def _engine(tmp_path, kb, params, view, shooter, cfg=None):
    store = ShotStore(tmp_path / "e.sqlite3")
    cal = Calibrator(store, params)
    cfg = cfg or Config(data={"automation": {"server_rules_confirmed": True, "min_seconds_between_shots": 0}})
    return CombatEngine(view, shooter, Aimer(kb, params, cal), cal, TargetTracker(), KillSwitch(), cfg)


def my_turn(**kw):
    base = dict(in_battle=True, my_turn=True, distance=8.0, wind=0.5, me_x=1, target_x=9, target_y=0, confidence=0.95)
    base.update(kw)
    return BattleObservation(**base)


def test_assist_never_fires(tmp_path, kb, params):
    sh = CountShooter()
    eng = _engine(tmp_path, kb, params, ScriptView([my_turn()]), sh)
    eng.step()  # o turno é confirmado na segunda leitura
    rec = eng.step()
    assert rec.best is not None and sh.shots == []


def test_auto_requires_authorization(tmp_path, kb, params):
    eng = _engine(tmp_path, kb, params, ScriptView([my_turn()]), CountShooter(), Config(data={}))
    ok, why = eng.set_mode(Mode.AUTO)
    assert not ok and "regras" in why and eng.mode == Mode.ASSIST


def test_auto_fires_once_per_turn(tmp_path, kb, params):
    sh = CountShooter()
    enemy = BattleObservation(True, False)
    seq = [my_turn(), my_turn(), my_turn(), my_turn(), enemy, enemy,
           my_turn(distance=6.0, target_x=7), my_turn(distance=6.0, target_x=7)]
    eng = _engine(tmp_path, kb, params, ScriptView(seq), sh)
    assert eng.set_mode(Mode.AUTO)[0]
    for _ in range(10):
        eng.step()
    assert len(sh.shots) == 2
    assert len(eng.calibrator.store.all()) == 2


def test_low_confidence_does_not_fire(tmp_path, kb, params):
    sh = CountShooter()
    cfg = Config(data={"automation": {"server_rules_confirmed": True, "min_seconds_between_shots": 0,
                                      "bad_read_seconds": 0}})
    eng = _engine(tmp_path, kb, params, ScriptView([my_turn(confidence=0.3)]), sh, cfg)
    eng.set_mode(Mode.AUTO)
    events = []
    eng.on_event = events.append
    for _ in range(6):  # desiste do turno só depois de 3 leituras ruins seguidas
        eng.step()
    assert sh.shots == [] and any("confiança" in e.message for e in events)


def test_brief_bad_reads_at_turn_start_do_not_lose_the_turn(tmp_path, kb, params):
    """Câmera se movendo no começo do turno: algumas leituras ruins e depois boas -> ainda atira."""
    sh = CountShooter()
    seq = [my_turn(confidence=0.3)] * 5 + [my_turn()]
    eng = _engine(tmp_path, kb, params, ScriptView(seq), sh)
    eng.set_mode(Mode.AUTO)
    for _ in range(len(seq)):
        eng.step()
    assert len(sh.shots) == 1


def test_hidden_target_without_history_waits(tmp_path, kb, params):
    sh = CountShooter()
    eng = _engine(tmp_path, kb, params, ScriptView([my_turn(target_visible=False, distance=None, target_x=None)]), sh)
    eng.set_mode(Mode.AUTO)
    assert eng.step() is None and sh.shots == []


def test_hidden_target_uses_estimate_after_history(tmp_path, kb, params):
    sh = CountShooter()
    enemy = BattleObservation(True, False)
    seq = [my_turn(target_x=9), my_turn(target_x=9), enemy, enemy,
           my_turn(target_x=9.2, distance=8.2), my_turn(target_x=9.2, distance=8.2), enemy, enemy,
           my_turn(target_visible=False, distance=None, target_x=None, me_y=0.0, target_y=None, wind_screen=0.5)]
    eng = _engine(tmp_path, kb, params, ScriptView(seq), sh)
    eng.tracker.max_move_per_turn = 0.5  # raio após 1 turno oculto: 0,7 (pequeno o bastante para atirar)
    eng.set_mode(Mode.AUTO)
    for _ in range(11):
        eng.step()
    assert len(sh.shots) == 3  # o terceiro disparo usou a região estimada
    assert any("estimada" in n for n in eng.last_observation.notes)


def test_battle_over_resets(tmp_path, kb, params):
    eng = _engine(tmp_path, kb, params, ScriptView([BattleObservation(False, False, battle_over="vitoria")]),
                  CountShooter())
    eng.tracker.observe("alvo", 1, 0, 1)
    eng.step()
    assert eng.tracker.targets  # um quadro só ainda não encerra a batalha
    eng.step()
    assert eng.tracker.targets == {}


def test_hidden_target_on_the_left_keeps_direction_and_wind(tmp_path, kb, params):
    """Alvo invisível à esquerda: direção, vento relativo e altura vêm da região estimada."""
    sh = CountShooter()
    enemy = BattleObservation(True, False)
    left = dict(me_x=9.0, me_y=0.0, target_x=3.0, target_y=-0.5, distance=6.0, direction=-1, wind=-1.0,
                wind_screen=1.0, dy=0.5)
    hidden = dict(me_x=9.0, me_y=0.0, target_visible=False, distance=None, target_x=None, wind_screen=1.0)
    seq = [my_turn(**left), my_turn(**left), enemy, enemy, my_turn(**left), my_turn(**left), enemy, enemy,
           my_turn(**hidden)]
    eng = _engine(tmp_path, kb, params, ScriptView(seq), sh)
    eng.tracker.max_move_per_turn = 0.5
    eng.set_mode(Mode.AUTO)
    for _ in range(11):
        eng.step()
    assert len(sh.shots) == 3 and sh.shots[-1][2] == -1
    obs = eng.last_observation
    assert obs.wind == -1.0 and abs(obs.dy - 0.5) < 1e-9
    assert eng.last_recommendation.context.sigma_distance > 0.1  # incerteza da região somada


def test_first_turn_of_next_battle_fires(tmp_path, kb, params):
    """A batalha terminou no meu turno: o primeiro turno da seguinte não pode ser pulado."""
    sh = CountShooter()
    over = BattleObservation(False, False, battle_over="vitoria")
    seq = [my_turn(), my_turn(), over, over, my_turn(), my_turn()]
    eng = _engine(tmp_path, kb, params, ScriptView(seq), sh)
    eng.set_mode(Mode.AUTO)
    for _ in range(6):
        eng.step()
    assert len(sh.shots) == 2


def test_single_victory_like_frame_does_not_allow_second_shot(tmp_path, kb, params):
    """Uma explosão lida como 'vitória' num quadro só não zera o turno nem libera outro disparo."""
    sh = CountShooter()
    over = BattleObservation(False, False, battle_over="vitoria")
    eng = _engine(tmp_path, kb, params, ScriptView([my_turn(), my_turn(), over, my_turn(), my_turn()]), sh)
    eng.set_mode(Mode.AUTO)
    for _ in range(5):
        eng.step()
    assert len(sh.shots) == 1


def test_observe_only_step_never_fires(tmp_path, kb, params):
    sh = CountShooter()
    eng = _engine(tmp_path, kb, params, ScriptView([my_turn()]), sh)
    eng.set_mode(Mode.AUTO)
    for _ in range(4):
        eng.step(allow_fire=False)
    assert sh.shots == [] and eng.last_recommendation is not None


def test_shot_recorded_even_if_stopped_during_wait(tmp_path, kb, params):
    sh = CountShooter()
    cfg = Config(data={"automation": {"server_rules_confirmed": True, "min_seconds_between_shots": 0,
                                      "post_shot_wait_s": 5.0}})
    eng = _engine(tmp_path, kb, params, ScriptView([my_turn()]), sh, cfg)
    stop = {"why": None}
    eng.cancel_check = lambda: stop["why"]
    eng.set_mode(Mode.AUTO)
    eng.step()
    threading.Timer(0.2, lambda: stop.update(why="parada")).start()
    t = time.monotonic()
    eng.step()
    assert len(sh.shots) == 1 and len(eng.calibrator.store.all()) == 1
    assert time.monotonic() - t < 2.0  # a espera pós-disparo respeita a parada
