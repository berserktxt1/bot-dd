"""Integração: captura -> visão -> decisão -> execução, com uma tela de jogo sintética
que reage às teclas enviadas (o ângulo exibido muda com as setas, a barra de força
enche enquanto o espaço está pressionado). Nenhum cliente real envolvido."""
import threading
import time

import cv2
import numpy as np

from ddbot.activities import activity_from_option
from ddbot.aiming import Aimer
from ddbot.automation.input import InputController, RecordingBackend
from ddbot.automation.safety import KillSwitch
from ddbot.calibration import Calibrator, ShotStore
from ddbot.capture import FrameSource
from ddbot.combat import CombatEngine, Mode
from ddbot.config import Config
from ddbot.game_io import GameActor, KeyboardShooter, VisionBattleView, VisionScreenReader
from ddbot.tracking import TargetTracker
from ddbot.vision.perception import Perception
from ddbot.vision.templates import TemplateLibrary


def text_img(t, w=60):
    img = np.zeros((30, w, 3), np.uint8)
    cv2.putText(img, t, (4, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return img


class FakeGame(FrameSource, RecordingBackend):
    """Tela + teclado falsos do jogo."""

    origin = (500, 300)

    def __init__(self):
        RecordingBackend.__init__(self)
        rng = np.random.default_rng(7)
        self.me_tpl = rng.integers(0, 255, (24, 24, 3), dtype=np.uint8)
        self.en_tpl = rng.integers(0, 255, (24, 24, 3), dtype=np.uint8)
        self.turn_tpl = rng.integers(0, 255, (20, 40, 3), dtype=np.uint8)
        self.btn_tpl = rng.integers(0, 255, (30, 80, 3), dtype=np.uint8)
        self.state_tpl = rng.integers(0, 255, (30, 120, 3), dtype=np.uint8)
        self.angle = 30
        self.space_down_at = None
        self.released_power = None
        self.full_time = 0.5
        self.lock = threading.Lock()

    def power(self):
        if self.space_down_at is None:
            return 0.0
        return min(100.0, (time.monotonic() - self.space_down_at) / self.full_time * 100)

    def key(self, key, up):
        super().key(key, up)
        with self.lock:
            if key == "up" and up:
                self.angle = min(90, self.angle + 1)
            elif key == "down" and up:
                self.angle = max(0, self.angle - 1)
            elif key == "space":
                if not up:
                    self.space_down_at = time.monotonic()
                else:
                    self.released_power = self.power()
                    self.space_down_at = None

    def grab(self):
        f = np.full((600, 1000, 3), 60, np.uint8)
        f[388:412, 188:212] = self.me_tpl          # eu em (200, 400)
        f[388:412, 788:812] = self.en_tpl          # inimigo em (800, 400): distância 6
        f[20:40, 900:940] = self.turn_tpl
        f[100:130, 450:570] = self.state_tpl
        f[500:530, 450:530] = self.btn_tpl         # botão centrado em (490, 515)
        with self.lock:
            f[540:570, 20:80] = text_img(str(self.angle))
            p = self.power()
        f[580:590, 300:300 + int(p * 4)] = (0, 0, 255)
        return f

    def is_foreground(self):
        return True


def build(tmp_path, power_mode="timed"):
    game = FakeGame()
    cfg = Config(data={
        "regions": {"angle": [0.02, 0.9, 0.06, 0.05], "turn_indicator": [0.88, 0.02, 0.1, 0.06],
                    "power_bar": [0.3, 0.9667, 0.4, 0.0167]},
        "automation": {"server_rules_confirmed": True, "min_seconds_between_shots": 0, "power_mode": power_mode,
                       "power_full_time_s": game.full_time, "post_shot_wait_s": 0.0, "key_delay_ms": 1},
        "thresholds": {"auto_min_hit_probability": 0.0, "vision_min_confidence": 0.0}})
    lib = TemplateLibrary(tmp_path / "tpl")
    lib.add("marcador_eu", game.me_tpl)
    lib.add("marcador_inimigo", game.en_tpl)
    lib.add("turno", game.turn_tpl)
    lib.add("botao_iniciar", game.btn_tpl)
    lib.add("estado_sala", game.state_tpl)
    per = Perception(cfg, lib, tmp_path / "tpl")
    per.angle_reader.learn(text_img("1234", 90), "1234")
    per.angle_reader.learn(text_img("5678", 90), "5678")
    per.angle_reader.learn(text_img("90"), "90")
    kill = KillSwitch()
    inp = InputController(kill, game, foreground_check=game.is_foreground, key_delay_s=0.001)
    view = VisionBattleView(game, per, cfg)
    store = ShotStore(tmp_path / "s.sqlite3")
    return game, cfg, lib, per, kill, inp, view, store


def test_vision_to_keyboard_shot(tmp_path, kb, params):
    game, cfg, lib, per, kill, inp, view, store = build(tmp_path)
    cal = Calibrator(store, params)
    eng = CombatEngine(view, KeyboardShooter(inp, view, cfg), Aimer(kb, params, cal), cal, TargetTracker(), kill, cfg)
    assert eng.set_mode(Mode.AUTO)[0]
    obs = view.observe()
    assert obs.my_turn and abs(obs.distance - 6.0) < 0.05 and obs.current_angle == 30
    eng.step()  # primeira leitura do turno; a segunda confirma e dispara
    rec = eng.step()
    b = rec.best
    assert b is not None
    # o ângulo exibido chegou ao recomendado e a força solta bate com o tempo de carga
    assert game.angle == b.angle
    assert game.released_power is not None and abs(game.released_power - b.force) < 6
    shots = store.all()
    assert len(shots) == 1 and shots[0].angle == b.angle
    # não dispara de novo no mesmo turno
    n_events = len(game.events)
    eng.step()
    assert len(game.events) == n_events
    store.close()


def test_visual_power_mode(tmp_path, kb, params):
    game, cfg, lib, per, kill, inp, view, store = build(tmp_path, power_mode="visual")
    # barra de 2 s (a real leva ~4 s): com 0,5 s a amostragem sob carga perde o ponto e a trava
    # de segurança solta pelo tempo, o que é o comportamento correto mas não o que se testa aqui
    game.full_time = 2.0
    cfg.set("automation.power_full_time_s", 2.0)
    sh = KeyboardShooter(inp, view, cfg)
    sh.charge_and_fire(40.0)
    assert abs(game.released_power - 40) < 6
    store.close()


def test_screen_reader_and_actor_click_with_window_offset(tmp_path):
    game, cfg, lib, per, kill, inp, view, store = build(tmp_path)
    reader = VisionScreenReader(game, per)
    s = reader.read()
    assert s.state == "sala" and s.confidence > 0.9
    actor = GameActor(inp, game, lib, cfg)
    assert actor.click("botao_iniciar", s.frame)
    assert ("click", 500 + 490, 300 + 515) in game.events
    assert not actor.click("botao_iniciar", s.frame)  # clique duplicado imediato bloqueado
    assert not actor.click("botao_sair", s.frame)     # modelo inexistente
    store.close()


def test_kill_switch_during_charge_releases_key(tmp_path):
    game, cfg, lib, per, kill, inp, view, store = build(tmp_path)
    cfg.set("automation.power_full_time_s", 5.0)
    sh = KeyboardShooter(inp, view, cfg)
    threading.Timer(0.1, kill.trigger).start()
    t = time.monotonic()
    try:
        sh.charge_and_fire(100)
    except Exception:
        pass
    assert time.monotonic() - t < 1.0
    assert game.events[-1] == ("key", "space", True)
    store.close()


def test_activity_definition_matches_capture_flow(tmp_path):
    d = activity_from_option("instancia_x", "X")
    assert d.flow["sala"][0].target == "botao_iniciar"


def test_visual_power_unreadable_bar_releases_on_time(tmp_path):
    """Barra configurada mas ilegível (cor errada: lê 0): solta no tempo, não 10% depois."""
    game, cfg, lib, per, kill, inp, view, store = build(tmp_path, power_mode="visual")
    game.full_time = 2.0
    cfg.set("automation.power_full_time_s", 2.0)
    cfg.set("regions.power_bar", [0.0, 0.0, 0.05, 0.05])  # região sem barra nenhuma
    KeyboardShooter(inp, view, cfg).charge_and_fire(40.0)
    assert abs(game.released_power - 40) < 4
    store.close()


def test_capture_error_during_charge_does_not_abort_shot(tmp_path):
    game, cfg, lib, per, kill, inp, view, store = build(tmp_path, power_mode="visual")
    game.full_time = 2.0
    cfg.set("automation.power_full_time_s", 2.0)
    real, calls = game.grab, {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] > 1:  # a primeira (antes de segurar) funciona; depois a captura falha
            raise RuntimeError("falha passageira na captura")
        return real()
    game.grab = flaky
    KeyboardShooter(inp, view, cfg).charge_and_fire(40.0)
    assert game.released_power is not None and abs(game.released_power - 40) < 4
    store.close()


def test_unconfirmed_angle_reads_are_not_trusted(tmp_path):
    game, cfg, lib, per, kill, inp, view, store = build(tmp_path)
    sh = KeyboardShooter(inp, view, cfg)
    seq = iter([44, 45, 44, 45, 44, 45])
    sh._read_angle = lambda: next(seq)
    assert sh._stable_angle() is None
    store.close()


def test_retarget_when_followed_enemy_is_gone(tmp_path):
    """O inimigo seguido morreu: depois de algumas leituras o bot mira o outro que está na tela."""
    from ddbot.vision.perception import Character, Snapshot
    game, cfg, lib, per, kill, inp, view, store = build(tmp_path)
    a, b = Character(500, 400, 1.0, "inimigo", "modelo"), Character(900, 400, 1.0, "inimigo", "modelo")
    snap = Snapshot(width=1000, height=600, enemies=[a, b], unit_px=100)
    view._target_px = (500, 400)
    assert view._pick_target(snap) is a
    snap.enemies = [b]  # A morreu
    picks = [view._pick_target(snap) for _ in range(view.RETARGET_READS)]
    assert all(p is None for p in picks[:-1]) and picks[-1] is b
    assert view._target_seq == 1  # alvo novo, histórico novo no rastreador
    store.close()


def test_click_cancelled_when_game_window_vanished(tmp_path, monkeypatch):
    """Janela do jogo fechada entre a leitura e o clique: nada de clicar na área de trabalho."""
    from ddbot import winapi
    from ddbot.capture import WindowCapture
    game, cfg, lib, per, kill, inp, view, store = build(tmp_path)
    frame = game.grab()
    gone = WindowCapture(4242)
    monkeypatch.setattr(winapi, "window_info", lambda h: None)
    actor = GameActor(inp, gone, lib, cfg)
    assert actor.click("botao_iniciar", frame) is False
    assert not any(e[0] == "click" for e in game.events)
    store.close()
