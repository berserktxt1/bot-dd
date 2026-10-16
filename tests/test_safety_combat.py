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
    g = TurnGate(0)
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
    rec = eng.step()
    assert rec.best is not None and sh.shots == []


def test_auto_requires_authorization(tmp_path, kb, params):
    eng = _engine(tmp_path, kb, params, ScriptView([my_turn()]), CountShooter(), Config(data={}))
    ok, why = eng.set_mode(Mode.AUTO)
    assert not ok and "regras" in why and eng.mode == Mode.ASSIST


def test_auto_fires_once_per_turn(tmp_path, kb, params):
    sh = CountShooter()
    seq = [my_turn(), my_turn(), my_turn(), BattleObservation(True, False), my_turn(distance=6.0, target_x=7)]
    eng = _engine(tmp_path, kb, params, ScriptView(seq), sh)
    assert eng.set_mode(Mode.AUTO)[0]
    for _ in range(5):
        eng.step()
    assert len(sh.shots) == 2
    assert len(eng.calibrator.store.all()) == 2


def test_low_confidence_does_not_fire(tmp_path, kb, params):
    sh = CountShooter()
    eng = _engine(tmp_path, kb, params, ScriptView([my_turn(confidence=0.3)]), sh)
    eng.set_mode(Mode.AUTO)
    events = []
    eng.on_event = events.append
    eng.step()
    eng.step()
    assert sh.shots == [] and any("confiança" in e.message for e in events)


def test_hidden_target_without_history_waits(tmp_path, kb, params):
    sh = CountShooter()
    eng = _engine(tmp_path, kb, params, ScriptView([my_turn(target_visible=False, distance=None, target_x=None)]), sh)
    eng.set_mode(Mode.AUTO)
    assert eng.step() is None and sh.shots == []


def test_hidden_target_uses_estimate_after_history(tmp_path, kb, params):
    sh = CountShooter()
    seq = [my_turn(target_x=9), BattleObservation(True, False), my_turn(target_x=9.2, distance=8.2),
           BattleObservation(True, False), my_turn(target_visible=False, distance=None, target_x=None)]
    eng = _engine(tmp_path, kb, params, ScriptView(seq), sh)
    eng.set_mode(Mode.AUTO)
    for _ in range(5):
        eng.step()
    assert len(sh.shots) == 3  # o terceiro disparo usou a região estimada
    assert any("estimada" in n for n in eng.last_observation.notes)


def test_battle_over_resets(tmp_path, kb, params):
    eng = _engine(tmp_path, kb, params, ScriptView([BattleObservation(False, False, battle_over="vitoria")]),
                  CountShooter())
    eng.tracker.observe("alvo", 1, 0, 1)
    eng.step()
    assert eng.tracker.targets == {}
