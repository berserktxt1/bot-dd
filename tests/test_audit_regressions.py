"""Regressões dos defeitos encontrados na auditoria de 2026-10-16 (um teste por defeito)."""
import json
import time
from dataclasses import replace

import numpy as np
import pytest

from ddbot.aiming import Aimer, ShotContext, Weapon, hit_half_width, round_angle
from ddbot.automation.input import InputController, RecordingBackend
from ddbot.automation.safety import Aborted, KillSwitch
from ddbot.calibration import Calibrator, ShotRecord, ShotStore
from ddbot.config import Config
from ddbot.physics import landing_x
from ddbot.tracking import TargetTracker
from test_integration import build


# ------------------------------------------------------------------ disparo
def test_angle_not_confirmed_aborts(tmp_path):
    """Ângulo na tela não converge: não dispara (antes confiava na contagem)."""
    game, cfg, lib, per, kill, inp, view, store = build(tmp_path)
    from ddbot.game_io import KeyboardShooter
    game.key = lambda key, up: RecordingBackend.key(game, key, up)  # setas não mudam o ângulo exibido
    sh = KeyboardShooter(inp, view, cfg)
    with pytest.raises(Aborted):
        sh.set_angle(40, 30)
    store.close()


def test_turn_ended_during_adjust_cancels_shot(tmp_path):
    game, cfg, lib, per, kill, inp, view, store = build(tmp_path)
    from ddbot.combat import BattleObservation
    from ddbot.game_io import KeyboardShooter
    sh = KeyboardShooter(inp, view, cfg)
    game.turn_tpl[:] = 0  # o indicador de turno some
    with pytest.raises(Aborted):
        sh.shoot(32, 40, 1, BattleObservation(True, True, current_angle=30))
    assert not any(e[1] == "space" for e in game.events if e[0] == "key")
    store.close()


def test_facing_reconfirmed_after_battle_reset(tmp_path):
    game, cfg, lib, per, kill, inp, view, store = build(tmp_path)
    from ddbot.game_io import KeyboardShooter
    sh = KeyboardShooter(inp, view, cfg)
    sh.face(-1)
    sh.face(-1)
    sh.reset()
    sh.face(-1)
    lefts = [e for e in game.events if e == ("key", "left", False)]
    assert len(lefts) == 2


def test_visual_power_never_holds_past_timed_estimate(tmp_path):
    """Barra não lida durante a carga: solta no tempo estimado, não segura até 100%."""
    game, cfg, lib, per, kill, inp, view, store = build(tmp_path, power_mode="visual")
    from ddbot.game_io import KeyboardShooter
    game.full_time = 2.0  # barra realista (a do jogo leva ~4 s); com 0,5 s, 15 ms do Windows = 3 pontos
    cfg.set("automation.power_full_time_s", 2.0)
    sh = KeyboardShooter(inp, view, cfg)
    first = {"done": False}

    def read_power(frame, snap):
        snap.power = 0.0 if not first["done"] else None
        first["done"] = True
    per.read_power = read_power
    sh.charge_and_fire(40.0)
    # trava: tempo estimado (40) + 10% + 50 ms = ~46,5; nunca perto de 100
    assert game.released_power is not None and 38 < game.released_power < 50
    store.close()


class Desktop:
    """Área de trabalho simulada: qual janela está em cada ponto da tela.

    Antes o teste consultava o Windows de verdade (WindowFromPoint) com uma janela de jogo
    falsa: passava na CI (o ponto caía fora da tela pequena do runner) e falhava num PC com
    1080p (havia outra janela real ali). Agora o cenário é explícito.
    """

    GAME, OTHER = 1, 2

    def __init__(self, info):
        self.info = info
        self.covered: tuple | None = None   # (x0, y0, x1, y1) coberto por OUTRA janela
        self.screen = (0, 0, 1920, 1080)

    def window_at(self, x, y):
        sx0, sy0, sx1, sy1 = self.screen
        if not (sx0 <= x < sx1 and sy0 <= y < sy1):
            return 0  # fora de qualquer monitor
        if self.covered and self.covered[0] <= x < self.covered[2] and self.covered[1] <= y < self.covered[3]:
            return self.OTHER
        i = self.info
        if i.left <= x < i.left + i.width and i.top <= y < i.top + i.height:
            return self.GAME
        return self.OTHER

    @staticmethod
    def contains(target, hwnd):
        return hwnd == target


def _actor_on_desktop(tmp_path):
    from ddbot.game_io import GameActor
    game, cfg, lib, per, kill, inp, view, store = build(tmp_path)

    class Info:
        left, top, width, height = 500, 300, 1000, 600
    game.info = Info()
    game.hwnd = Desktop.GAME
    desk = Desktop(Info)
    actor = GameActor(inp, game, lib, cfg, window_at=desk.window_at, contains=desk.contains)
    return game, Info, desk, actor, store


def test_actor_refuses_click_when_window_resized(tmp_path):
    """Geometria errada recusa; janela no tamanho certo, ativa e desobstruída permite."""
    game, Info, desk, actor, store = _actor_on_desktop(tmp_path)
    frame = game.grab()                      # quadro de 1000x600
    Info.width, Info.height = 800, 600       # a janela mudou de tamanho depois da leitura
    assert actor.click("botao_iniciar", frame) is False
    assert not any(e[0] == "click" for e in game.events)
    Info.width, Info.height = 1000, 600      # tamanho igual ao do quadro
    assert actor.click("botao_iniciar", frame) is True
    assert ("click", 500 + 490, 300 + 515) in game.events
    assert actor.click("botao_iniciar", frame) is None  # adiado, não "não encontrado"
    store.close()


def test_actor_refuses_click_under_other_window(tmp_path):
    game, Info, desk, actor, store = _actor_on_desktop(tmp_path)
    frame = game.grab()
    desk.covered = (900, 780, 1100, 900)     # outra janela sobre o botão (990, 815)
    assert actor.click("botao_iniciar", frame) is False
    desk.covered = None
    assert actor.click("botao_iniciar", frame) is True
    store.close()


def test_actor_refuses_click_off_screen(tmp_path):
    """Jogo parcialmente fora do monitor: o ponto não tem janela e o clique não cairia no jogo."""
    game, Info, desk, actor, store = _actor_on_desktop(tmp_path)
    frame = game.grab()
    desk.screen = (0, 0, 900, 700)           # monitor menor: o botão (990, 815) fica fora
    assert actor.click("botao_iniciar", frame) is False
    assert not any(e[0] == "click" for e in game.events)
    store.close()


def test_cancel_interrupts_between_keys():
    k = KillSwitch()
    be = RecordingBackend()
    state = {"why": None}
    inp = InputController(k, be, cancel_check=lambda: state["why"], key_delay_s=0.001)
    inp.tap("up", 3)
    state["why"] = "pausa"
    from ddbot.automation.safety import Cancelled
    with pytest.raises(Cancelled):
        inp.tap("up", 3)
    assert be.events[-1] == ("key", "up", True)


# ------------------------------------------------------------------ mira
def test_flat_terrain_does_not_block_high_shots_with_headwind(kb, params):
    aimer = Aimer(kb, params)
    flat = np.array([[0, 0.0], [40, 0.0]])
    for d, w in ((3, -2), (5, -3), (4, -2)):
        rec = aimer.recommend(ShotContext(distance=d, wind=w, terrain=flat))
        assert not any(c.blocked for c in rec.candidates), (d, w)


def test_round_angle_half_up():
    assert round_angle(30.5) == 31 and round_angle(31.5) == 32 and round_angle(29.49) == 29


def test_table_extrapolates_half_unit(kb):
    a50 = kb.table_methods["a50"]
    assert a50.force_for(20.4) > a50.force_for(20) + 0.5


def test_weapon_correction_not_applied_twice(tmp_path, kb, params):
    """Arma com força ×1,1 e disparos perfeitos: a correção aprendida deve ser ~0."""
    w = Weapon(name="forte", force_scale=1.1)
    cal = Calibrator(ShotStore(tmp_path / "w.sqlite3"), params,
                     weapon_lookup=lambda n: w if n == "forte" else Weapon())
    pw = replace(params, speed_k=params.speed_k * 1.1)
    for d in (4, 6, 8, 10, 12, 14, 5, 7, 9, 11):
        f = 30 + 2.5 * d
        cal.record(ShotRecord(angle=65, force=f, wind=0, distance=d, method="a65", weapon="forte",
                              impact_x=float(landing_x(65, f, 0, 0, pw))))
    off, sigma, n = cal.predict_offset("a65", 65, 50, 0, 0, 8, weapon="forte")
    assert n == 10 and abs(off) < 0.05


def test_general_correction_only_shifts_bias(tmp_path, params):
    cal = Calibrator(ShotStore(tmp_path / "b.sqlite3"), params)
    for d in (4, 8, 12, 16):
        f = 30 + 3 * d
        cal.record(ShotRecord(angle=65, force=f, wind=0, distance=d, method="a65",
                              impact_x=float(landing_x(65, f, 0, 0, params)) + 0.5))
    # outro método, sem dados próprios: usa só o viés geral (sem inclinação do a65)
    off_near, _, _ = cal.predict_offset("a20", 20, 40, 0, 0, 2)
    off_far, _, _ = cal.predict_offset("a20", 20, 80, 0, 0, 18)
    assert off_near == pytest.approx(off_far)


def test_predictive_sigma_matches_noise(tmp_path, params):
    rng = np.random.default_rng(5)
    cal = Calibrator(ShotStore(tmp_path / "s.sqlite3"), params)
    for _ in range(10):
        d = rng.uniform(4, 16)
        f = 30 + 3 * d
        cal.store.add(ShotRecord(angle=65, force=f, wind=0, distance=d, method="a65",
                                 impact_x=float(landing_x(65, f, 0, 0, params)) + rng.normal(0, 0.3)))
    cal.rebuild()
    _, sigma, n = cal.predict_offset("a65", 65, 56, 0, 0, 10)
    assert n == 10 and sigma > 0.2  # antes: ~0,2 dividido por √(n/5), subestimado


def test_refit_keeps_parameters_physical(tmp_path, kb, params):
    cal = Calibrator(ShotStore(tmp_path / "r.sqlite3"), params)
    rng = np.random.default_rng(2)
    for _ in range(20):
        a, f = rng.uniform(30, 80), rng.uniform(30, 90)
        cal.store.add(ShotRecord(angle=a, force=f, wind=rng.uniform(-2, 2), distance=5,
                                 impact_x=float(rng.uniform(0, 3))))  # dados ruins de propósito
    rows = [(a, d, f) for a, d, f, _ in kb.documented_cells()]
    new, info = cal.refit_params(table_rows=rows, max_iter=150)
    for v, (lo, hi) in zip(new.to_vector(), Calibrator.BOUNDS):
        assert lo <= v <= hi
    assert new.wind_k >= 0


def test_hit_criterion_single_definition():
    assert hit_half_width(0.35, 0.25) == pytest.approx(0.425)


# ------------------------------------------------------------------ rastreamento
def test_hidden_radius_uses_max_move():
    tr = TargetTracker(max_move_per_turn=1.5, max_uncertainty=2.5)
    tr.observe("x", 5, 0, 1)
    tr.observe("x", 5, 0, 2)  # parado enquanto visível
    tr.mark_hidden("x", 3)
    assert tr.estimate("x", 3).radius == pytest.approx(1.7)


def test_turn_counter_reset_is_not_current_position():
    tr = TargetTracker()
    tr.observe("x", 5, 0, 10)
    tr.observe("x", 5, 0, 11)
    tr.mark_hidden("x", 2)
    assert tr.estimate("x", 2) is None


# ------------------------------------------------------------- configuração
@pytest.mark.parametrize("content", ["﻿{}", "", "{quebrado", "[1, 2]", '"texto"'])
def test_bad_config_file_falls_back(tmp_path, content):
    path = tmp_path / "config.json"
    path.write_text(content, encoding="utf-8")
    c = Config(path)
    assert c.get("thresholds.template") == 0.8
    if content.strip("﻿") not in ("{}",):
        assert c.problems and list(tmp_path.glob("config.corrompido-*.json"))


def test_wrong_types_replaced_by_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"capture": 5, "thresholds": {"template": "abc"},
                                "safety": {"emergency_hotkey": None}}), encoding="utf-8")
    c = Config(path)
    assert c.get("capture.fps") == 4 and c.get("thresholds.template") == 0.8
    assert c.get("safety.emergency_hotkey", "<f12>") == "<f12>"  # vazio não derruba a interface
    assert len(c.problems) == 2


def test_validate_values_ranges():
    assert Config.validate_values({"thresholds.template": 2.0})
    assert not Config.validate_values({"thresholds.template": 0.8})


def test_config_save_is_atomic(tmp_path):
    c = Config(tmp_path / "config.json")
    c.set("instances.max_minutes", 30)
    c.save()
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["instances"]["max_minutes"] == 30
    assert not list(tmp_path.glob(".config.json.*.tmp"))


# --------------------------------------------------------------- persistência
def test_knowledge_updated_only_if_untouched(tmp_path, monkeypatch):
    from ddbot import paths as P
    res = tmp_path / "res"
    (res / "data" / "knowledge").mkdir(parents=True)
    (res / "data" / "instances").mkdir(parents=True)
    src = res / "data" / "knowledge" / "angle_tables.json"
    src.write_text('{"v": 1}', encoding="utf-8")
    monkeypatch.setattr(P, "resource_root", lambda: res)
    home = tmp_path / "home"
    P.Paths(home)
    user = home / "knowledge" / "angle_tables.json"
    src.write_text('{"v": 2}', encoding="utf-8")  # versão nova do programa
    P.Paths(home)
    assert json.loads(user.read_text()) == {"v": 2}
    user.write_text('{"v": "meu"}', encoding="utf-8")  # editado pelo usuário
    src.write_text('{"v": 3}', encoding="utf-8")
    P.Paths(home)
    assert json.loads(user.read_text()) == {"v": "meu"}


def test_corrupted_model_params_restored(home):
    from ddbot.service import BotService
    svc = BotService(home, start_hotkey=False)
    svc.close()
    (home / "knowledge" / "model_params.json").write_text("{", encoding="utf-8")
    svc = BotService(home, start_hotkey=False)
    try:
        assert svc.params.speed_k > 0
        assert any("modelo físico" in n for n in svc.startup_notes)
    finally:
        svc.close()


def test_activity_name_collision_gets_suffix(home):
    from ddbot.service import BotService
    svc = BotService(home, start_hotkey=False)
    try:
        img = np.random.default_rng(0).integers(0, 255, (20, 20, 3), dtype=np.uint8)
        a = svc.create_activity_from_image(img, "Labirinto!", "instancia", "pve")
        b = svc.create_activity_from_image(img, "Labirinto?", "instancia", "pve")
        assert a.key != b.key
        assert len(svc.templates.get(a.flow["menu_instancias"][0].target)) == 1
        assert len(svc.templates.get(b.flow["menu_instancias"][0].target)) == 1
    finally:
        svc.close()


def test_captures_are_limited(home, monkeypatch):
    from ddbot import service as S
    from ddbot.service import BotService
    monkeypatch.setattr(S, "MAX_CAPTURES", 5)
    svc = BotService(home, start_hotkey=False)
    try:
        img = np.zeros((4, 4, 3), np.uint8)
        for _ in range(9):
            svc.save_capture(img)
            time.sleep(0.002)
        assert len(list(svc.paths.captures.glob("*.png"))) == 5
    finally:
        svc.close()


def test_home_path_masked_in_logs(home):
    import logging
    from pathlib import Path
    from ddbot.service import BotService
    svc = BotService(home, start_hotkey=False)
    try:
        logging.getLogger("teste").warning("arquivo em %s", Path.home() / "segredo")
        for h in logging.getLogger().handlers:
            h.flush()
        text = (svc.paths.logs / "ddbot.log").read_text(encoding="utf-8")
        assert str(Path.home()) + "/segredo" not in text and "%USERPROFILE%" in text
    finally:
        svc.close()


def test_real_start_blocked_without_hotkey(home):
    from ddbot.activities import activity_from_option
    from ddbot.capture import ArraySource
    from ddbot.service import BotService
    svc = BotService(home, start_hotkey=False)
    try:
        svc.hotkey, svc.hotkey_ok = object(), False
        svc.set_source(ArraySource(np.zeros((10, 10, 3), np.uint8)))
        ok, why = svc.start(activity_from_option("instancia_x", "X"), 1, simulated=False)
        assert not ok and "emergência" in why
    finally:
        svc.hotkey = None
        svc.close()


def test_controls_test_refused_while_running(home):
    from ddbot.activities import activity_from_option
    from ddbot.capture import ArraySource
    from ddbot.service import BotService
    svc = BotService(home, start_hotkey=False)
    try:
        assert svc.start(activity_from_option("instancia_teste", "T"), 0, simulated=True)[0]
        svc.set_source(ArraySource(np.zeros((10, 10, 3), np.uint8)))
        with pytest.raises(RuntimeError):
            svc.test_controls()
    finally:
        svc.close()


def test_window_capture_releases_all_threads():
    import threading

    from ddbot.capture import WindowCapture
    cap = WindowCapture(0)

    class Fake:
        closed = 0

        def close(self):
            Fake.closed += 1
    import ddbot.capture as C
    orig = C.WindowCapture._sct

    def fake_sct(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            sct = Fake()
            self._local.sct = sct
            with self._lock:
                self._all[id(sct)] = sct
        return sct
    C.WindowCapture._sct = fake_sct
    try:
        def work(release):
            cap._sct()
            if release:
                cap.release_thread()
        ts = [threading.Thread(target=work, args=(i % 2 == 0,)) for i in range(6)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert cap.open_instances == 3
        cap.close()
        assert cap.open_instances == 0 and Fake.closed == 6
    finally:
        C.WindowCapture._sct = orig


def test_legacy_localappdata_folder_kept(tmp_path, monkeypatch):
    """Quem usava o DDClássico Bot com dados em %LOCALAPPDATA% continua com os mesmos dados no JonFlow."""
    from ddbot import paths as P
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert P._fallback_dir() == tmp_path / "JonFlow"
    (tmp_path / "DDClassicoBot").mkdir()
    (tmp_path / "DDClassicoBot" / "config.json").write_text("{}", encoding="utf-8")
    assert P._fallback_dir() == tmp_path / "DDClassicoBot"
    (tmp_path / "JonFlow").mkdir()
    assert P._fallback_dir() == tmp_path / "JonFlow"


# ------------------------------------------------------------ 0.4.0: launcher e captura
def test_stale_parent_pid_reused_by_other_launcher_is_dropped():
    """O pid do pai que terminou foi reaproveitado por um launcher aberto depois do jogo."""
    from ddbot.winapi import prune_stale_parents
    created = {10: 100, 11: 900, 20: 500, 30: 50}   # 11 (segundo launcher) nasceu depois do jogo (20)
    parents = {10: 4, 11: 4, 20: 11, 30: 4}
    out = prune_stale_parents(parents, created.get)
    assert out[20] == 0 and out[10] == 4
    # sem a hora de criação (sem acesso), a ligação fica: não há prova de que é falsa
    assert prune_stale_parents({20: 11, 11: 4}, lambda pid: None)[20] == 11


def test_several_launchers_without_parentage_do_not_guess():
    from ddbot.detection import GAME, detect
    from ddbot.game_window import GameWindowProfile, WindowRule
    from ddbot.winapi import WindowInfo

    def w(hwnd, pid, exe, title, ww=1000, hh=640):
        return WindowInfo(hwnd, title, 0, 0, ww, hh, pid=pid, exe=exe, cls="Wnd")
    l1, l2 = w(100, 10, "L.exe", "DDTank Launcher", 1200, 700), w(110, 11, "L.exe", "DDTank Launcher", 900, 600)
    game = w(200, 20, "cliente.exe", "Janela")
    prof = GameWindowProfile(WindowRule("cliente.exe", "Wnd"), WindowRule("L.exe", "Wnd"))
    # o jogo foi aberto por um processo intermediário que já terminou: sem parentesco
    d = detect([l1, l2, game], {10: 4, 11: 4, 20: 0}, 999, ["DDTank"], prof)
    assert d.state == GAME and d.game.hwnd == 200
    assert d.launcher is None  # dois launchers: não escolhe o "maior"
    # com parentesco, é o launcher certo, mesmo sendo o menor
    d = detect([l1, l2, game], {10: 4, 11: 4, 20: 11}, 999, ["DDTank"], prof)
    assert d.launcher is not None and d.launcher.pid == 11
    # um launcher só, sem parentesco: é ele
    d = detect([l1, game], {10: 4, 20: 0}, 999, ["DDTank"], prof)
    assert d.launcher is not None and d.launcher.pid == 10


def _frame(color, w=400, h=300):
    import numpy as np
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = color
    img[::17, :] = (255, 255, 255)  # textura: nada de imagem "vazia"
    return img


def test_window_image_that_shows_the_covering_window_is_refused():
    from ddbot.capture import check_window_image, grid_points
    game, cover = _frame((40, 170, 40)), _frame((40, 40, 170))
    pts = [p for p in grid_points() if p[0] > 0.5]           # metade direita coberta
    screen = game.copy()
    screen[:, 200:] = cover[:, 200:]
    ok, _ = check_window_image(game, screen, pts)              # imagem real do jogo: confirmada
    assert ok is True
    ok, why = check_window_image(screen, screen, pts)          # "imagem da janela" = a tela: recusada
    assert ok is False and "na frente" in why
    ok, _ = check_window_image(cover, game, [])                # descoberto, mas não confere
    assert ok is False
    ok, _ = check_window_image(game, cover, grid_points())     # todo coberto: não dá para confirmar
    assert ok is None


def test_window_capture_never_returns_foreign_pixels(monkeypatch):
    """Simula o Windows: PrintWindow devolvendo a janela da frente; jogo coberto em parte."""
    import numpy as np
    from ddbot import capture, winapi
    from ddbot.winapi import WindowInfo
    info = WindowInfo(5, "Cliente", 100, 100, 400, 300)
    game, cover = _frame((40, 170, 40)), _frame((40, 40, 170))
    screen = game.copy()
    screen[:, 330:] = cover[:, 330:]                            # janela estreita na faixa da direita
    cover_x0 = 100 + 330

    monkeypatch.setattr(winapi, "window_info", lambda h: info)
    monkeypatch.setattr(winapi, "is_minimized", lambda h: False)
    monkeypatch.setattr(winapi, "root_of", lambda h: h)
    monkeypatch.setattr(winapi, "window_at", lambda x, y: 9 if x >= cover_x0 else 5)
    cap = capture.WindowCapture(5)
    monkeypatch.setattr(cap, "_screen", lambda i: screen.copy())
    # a cobertura fica entre os 5 pontos antigos (centro/quadrantes): a grade a encontra
    assert capture.covered(5, info, winapi.window_at, winapi.root_of)
    monkeypatch.setattr(cap, "_grab_window", lambda i: screen.copy())   # PrintWindow "mentindo"
    assert cap.grab() is None and "na frente" in cap.unavailable
    monkeypatch.setattr(cap, "_grab_window", lambda i: game.copy())     # PrintWindow correto
    frame = cap.grab()
    assert frame is not None and cap.method == "janela" and np.array_equal(frame, game)
    monkeypatch.setattr(cap, "_grab_window", lambda i: None)            # sem PrintWindow e coberto
    assert cap.grab() is None and "na frente do jogo" in cap.unavailable


def test_capture_part_of_game_off_screen_is_not_a_mismatch(monkeypatch):
    """No runner do Windows (1024x768) o jogo de teste passava da borda: a cópia da tela é preta ali.

    Esses pontos não podem reprovar a imagem certa da janela, e sem ela a cópia da tela não é usada.
    """
    import numpy as np
    from ddbot import capture, winapi
    from ddbot.winapi import WindowInfo
    info = WindowInfo(5, "Cliente", 100, 100, 400, 300)
    game = _frame((40, 170, 40))
    screen = game.copy()
    screen[:, 250:] = 0                                         # fora do monitor: preto na cópia da tela
    monkeypatch.setattr(winapi, "window_info", lambda h: info)
    monkeypatch.setattr(winapi, "is_minimized", lambda h: False)
    monkeypatch.setattr(winapi, "root_of", lambda h: h)
    monkeypatch.setattr(winapi, "window_at", lambda x, y: 0 if x >= 350 else 5)
    cap = capture.WindowCapture(5)
    monkeypatch.setattr(cap, "_screen", lambda i: screen.copy())
    monkeypatch.setattr(cap, "_grab_window", lambda i: game.copy())
    frame = cap.grab()
    assert frame is not None and cap.method == "janela" and np.array_equal(frame, game)
    monkeypatch.setattr(cap, "_grab_window", lambda i: None)
    assert cap.grab() is None and "fora da tela" in cap.unavailable


def _scaled_game(scale):
    """Janela de teste verde (#22AA44) com texto, desenhada na escala ``scale`` (1.0 = 100%)."""
    import cv2
    import numpy as np
    w, h = int(round(400 * scale)), int(round(248 * scale))
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = (68, 170, 34)
    cv2.putText(img, "GAME", (w // 2 - int(60 * scale), h // 2), cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), 2)
    return img


def test_window_drawn_at_100_percent_on_125_percent_screen(monkeypatch):
    """PC do usuário em 125%: a janela sem suporte a DPI desenha em 100% e o Windows a amplia na tela.

    A imagem pedida no tamanho da tela vinha com o jogo num canto e o resto preto (média BGR 43, 108, 22)
    e passava na conferência por pontos (30 de 48 coincidiam). Agora a imagem no tamanho em que a janela
    desenha é ampliada para a tela; a imagem no canto é recusada (e, com o jogo coberto, nada é usado).
    """
    import numpy as np
    from ddbot import capture, winapi
    from ddbot.capture import check_window_image, grid_points
    from ddbot.winapi import WindowInfo
    small, screen = _scaled_game(1.0), _scaled_game(1.25)        # 400×248 desenhado, 500×310 na tela
    h, w = screen.shape[:2]
    corner = np.zeros_like(screen)
    corner[:small.shape[0], :small.shape[1]] = small             # o que o PrintWindow devolvia antes
    ok, why = check_window_image(corner, screen, [], grid_points())
    assert ok is False and "área inteira" in why

    info = WindowInfo(5, "Cliente", 100, 100, w, h)
    monkeypatch.setattr(winapi, "IS_WINDOWS", True)
    monkeypatch.setattr(winapi, "window_info", lambda hw: info)
    monkeypatch.setattr(winapi, "is_minimized", lambda hw: False)
    monkeypatch.setattr(winapi, "root_of", lambda hw: hw)
    monkeypatch.setattr(winapi, "window_at", lambda x, y: 5)
    bgra = lambda img: np.dstack([img, np.full(img.shape[:2], 255, np.uint8)])  # noqa: E731
    cap = capture.WindowCapture(5)
    monkeypatch.setattr(cap, "_screen", lambda i: screen.copy())
    monkeypatch.setattr(winapi, "print_window", lambda hw, ww, hh: bgra(small))    # tamanho em que a janela desenha
    frame = cap.grab()
    assert frame is not None and cap.method == "janela" and frame.shape == screen.shape
    assert float(np.abs(frame.astype(int) - screen.astype(int)).mean()) < 4      # igual à tela, inclusive nos cantos
    assert tuple(frame[-3, -3]) == (68, 170, 34)

    cap = capture.WindowCapture(5)
    monkeypatch.setattr(cap, "_screen", lambda i: screen.copy())
    monkeypatch.setattr(winapi, "print_window", lambda hw, ww, hh: bgra(corner))   # imagem no canto (antes)
    frame = cap.grab()
    assert cap.method == "tela" and np.array_equal(frame, screen)  # descoberto: usa a cópia da tela, nunca o canto
    cap = capture.WindowCapture(5)
    monkeypatch.setattr(cap, "_screen", lambda i: screen.copy())
    monkeypatch.setattr(winapi, "window_at", lambda x, y: 9 if x > 100 + w * 0.8 else 5)  # coberto à direita
    assert cap.grab() is None and cap.unavailable                    # coberto: recusa com o motivo


def test_fit_to_area_only_scales_like_windows():
    import numpy as np
    from ddbot.capture import fit_to_area, unpainted_edges
    img = np.full((248, 400, 3), 90, np.uint8)
    assert fit_to_area(img, 400, 248) is img
    assert fit_to_area(img, 500, 310).shape == (310, 500, 3)       # 125%
    assert fit_to_area(img, 600, 372).shape == (372, 600, 3)       # 150%
    assert fit_to_area(img, 500, 248) is None                      # proporção diferente: não é a escala do Windows
    screen = np.full((310, 500, 3), 90, np.uint8)
    black_right = screen.copy()
    black_right[:, 450:] = 0
    assert not unpainted_edges(black_right, screen)                # só um lado preto: a conferência por pontos decide
    black_right[280:, :] = 0
    assert unpainted_edges(black_right, screen)
    assert not unpainted_edges(black_right, black_right)           # a tela também é preta ali (fora do monitor)
