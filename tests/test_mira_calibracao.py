"""Calibração por resultados (cenários separados, ajuste robusto, banco antigo) e estabilidade da mira.

Disparos e impactos são sintéticos: provam a matemática e o registro, não a precisão no DDClássico.
"""
import sqlite3

import numpy as np

from ddbot.aiming import Aimer, Candidate, Recommendation, ShotContext
from ddbot.automation.safety import KillSwitch
from ddbot.calibration import Calibrator, ShotRecord, ShotStore
from ddbot.combat import CombatEngine
from ddbot.config import Config
from ddbot.tracking import TargetTracker


def shots(cal, params, n, bias, scenario, outliers=(), seed=0, source="observado"):
    rng = np.random.default_rng(seed)
    for i in range(n):
        d = float(rng.uniform(4, 14))
        rec = ShotRecord(angle=65, force=50.0, wind=0.0, distance=d, method="a65", source=source, scenario=scenario)
        pred = cal.predict_x(rec)
        rec.impact_x = pred + bias + float(rng.normal(0, 0.05)) + (outliers[i] if i < len(outliers) else 0.0)
        cal.record(rec)


def test_robust_correction_ignores_a_few_wrong_marks(tmp_path, params):
    store = ShotStore(tmp_path / "s.sqlite3")
    cal = Calibrator(store, params, scenario="timed|cliente.exe")
    # 12 disparos com erro real de +0,8 e dois marcados muito errado (+6): a correção fica perto de +0,8
    shots(cal, params, 14, 0.8, "timed|cliente.exe", outliers=(6.0, 6.0))
    off, sigma, n = cal.predict_offset("a65", 65, 50.0, 0.0, 0.0, 9.0)
    assert n == 14 and abs(off - 0.8) < 0.2, off
    store.close()


def test_scenarios_do_not_mix(tmp_path, params):
    store = ShotStore(tmp_path / "s.sqlite3")
    current = {"v": "timed|cliente.exe"}
    cal = Calibrator(store, params, scenario=lambda: current["v"])
    shots(cal, params, 8, 0.8, "timed|cliente.exe", seed=1)
    shots(cal, params, 8, -1.5, "visual|cliente.exe", seed=2)
    off, _, n = cal.predict_offset("a65", 65, 50.0, 0.0, 0.0, 9.0)
    assert n == 8 and abs(off - 0.8) < 0.2
    current["v"] = "visual|cliente.exe"  # o usuário trocou o modo de controlar a força
    off, _, n = cal.predict_offset("a65", 65, 50.0, 0.0, 0.0, 9.0)
    assert n == 8 and abs(off + 1.5) < 0.2
    current["v"] = "timed|outro_cliente.exe"
    assert cal.predict_offset("a65", 65, 50.0, 0.0, 0.0, 9.0)[2] == 0  # outro cliente: nada aprendido
    st = cal.stats()
    assert st["disparos"] == 0 and st["outros_cenarios"] == 16
    store.close()


def test_new_shots_get_the_current_scenario_and_context(tmp_path, params):
    store = ShotStore(tmp_path / "s.sqlite3")
    cal = Calibrator(store, params, scenario="timed|cliente.exe")
    sid = cal.record(ShotRecord(angle=65, force=50, wind=0, distance=8, method="a65", instance="galinheiro_dificil",
                                difficulty="dificil", stage="Pintinhos", target="frango"))
    back = store.get(sid)
    assert (back.scenario, back.instance, back.difficulty, back.stage, back.target) == \
        ("timed|cliente.exe", "galinheiro_dificil", "dificil", "Pintinhos", "frango")
    assert back.predicted_x is not None  # previsto fica guardado ao lado do observado
    cal.set_result(sid, back.predicted_x + 0.1, True)
    assert cal.stats()["por_instancia"] == {"galinheiro_dificil": {"avaliados": 1, "acertos": 1}}
    store.close()


def test_old_database_is_upgraded_and_old_shots_kept_out_of_the_correction(tmp_path, params):
    path = tmp_path / "antigo.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE shots (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL, angle REAL, force REAL,
                    wind REAL, distance REAL, dy REAL, impact_x REAL, hit INTEGER, method TEXT, weapon TEXT,
                    predicted_x REAL, source TEXT, mode TEXT, note TEXT)""")
    for i in range(6):
        conn.execute("INSERT INTO shots (timestamp, angle, force, wind, distance, dy, impact_x, hit, method, weapon,"
                     " predicted_x, source, mode, note) VALUES (0, 65, 50, 0, ?, 0, ?, 1, 'a65', 'padrao', NULL,"
                     " 'observado', 'automatico', '')", (6 + i, 9 + i))
    conn.commit()
    conn.close()
    store = ShotStore(path)
    assert len(store.all()) == 6 and all(r.scenario == "" for r in store.all())
    cal = Calibrator(store, params, scenario="timed|cliente.exe")
    assert cal.predict_offset("a65", 65, 50.0, 0.0, 0.0, 9.0)[2] == 0  # versão antiga, sem cenário
    assert cal.stats()["outros_cenarios"] == 6
    store.close()


def test_combat_records_instance_stage_and_target(tmp_path, kb, params):
    from ddbot.combat import BattleObservation, ShotOutcome
    store = ShotStore(tmp_path / "s.sqlite3")
    cal = Calibrator(store, params)
    eng = CombatEngine(None, None, Aimer(kb, params, cal), cal, TargetTracker(), KillSwitch(), Config(data={}))
    eng.context = {"instancia": "olimpiadas_bugou_normal", "dificuldade": "normal"}
    rec = Aimer(kb, params).recommend(ShotContext(distance=7.0))
    obs = BattleObservation(True, True, distance=7.0, stage="Balões", target_id="balao_vermelho_3")
    sid = eng.record(rec, obs, ShotOutcome(), mode="automatico")
    back = store.get(sid)
    assert (back.instance, back.difficulty, back.stage, back.target) == \
        ("olimpiadas_bugou_normal", "normal", "Balões", "balao_vermelho")
    store.close()


def cand(method, angle, p):
    return Candidate(method, angle, 50.0, 7.0, 7.0, 0.3, p, ["teste"])


def test_recommendation_stays_on_the_same_angle_within_a_turn(kb, params):
    eng = CombatEngine(None, None, None, None, TargetTracker(), KillSwitch(), Config(data={}))
    ctx = ShotContext(distance=7.0)
    first = Recommendation(cand("fisica", 64, 0.80), [cand("fisica", 64, 0.80), cand("a65", 66, 0.78)], ctx)
    assert eng.keep_steady(first, 1).best.angle == 64
    # a leitura oscilou um pouco: o outro ângulo ficou 2% melhor, mas o turno continua no mesmo
    wobble = Recommendation(cand("a65", 66, 0.81), [cand("a65", 66, 0.81), cand("fisica", 64, 0.79)], ctx)
    kept = eng.keep_steady(wobble, 1)
    assert kept.best.angle == 64 and "64°" in kept.reason
    # bem melhor: troca
    better = Recommendation(cand("a65", 66, 0.95), [cand("a65", 66, 0.95), cand("fisica", 64, 0.70)], ctx)
    assert eng.keep_steady(better, 1).best.angle == 66
    # turno novo: vale o melhor da leitura nova
    assert eng.keep_steady(Recommendation(cand("fisica", 64, 0.81), [cand("fisica", 64, 0.81),
                                                                     cand("a65", 66, 0.80)], ctx), 2).best.angle == 64


def test_timed_release_adds_the_bar_start_delay():
    from ddbot.automation.input import InputController, RecordingBackend
    from ddbot.game_io import KeyboardShooter
    rec = RecordingBackend()
    inp = InputController(KillSwitch(), rec)
    held = {}
    inp.hold = lambda key, seconds, **kw: held.update(key=key, s=seconds) or True
    cfg = Config(data={"automation": {"power_full_time_s": 3.33, "power_start_delay_s": 0.06,
                                      "power_mode": "timed"}})
    KeyboardShooter(inp, None, cfg).charge_and_fire(50.0)
    assert abs(held["s"] - (0.06 + 3.33 * 0.5)) < 1e-6
    # o padrão para quem instala agora vem da medida no DDClássico (a conferir no cliente)
    assert Config(data={}).get("automation.power_full_time_s") == 3.33
