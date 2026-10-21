import cv2
import numpy as np

from ddbot.capture import ArraySource, ImageSource, load_image, save_image
from ddbot.config import Config
from ddbot.vision.digits import DigitReader
from ddbot.vision.menu import detect_option_tiles, find_known_options
from ddbot.vision.perception import Perception, power_fill, to_ruler
from ddbot.vision.regions import crop, frac_to_px, px_to_frac
from ddbot.vision.templates import TemplateLibrary, find_all, match_template


def text_img(t, w=90):
    img = np.zeros((30, w, 3), np.uint8)
    cv2.putText(img, t, (4, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return img


def test_regions_roundtrip():
    shape = (600, 1000, 3)
    rect = frac_to_px([0.1, 0.2, 0.3, 0.1], shape)
    assert rect == (100, 120, 300, 60)
    assert px_to_frac(rect, shape) == [0.1, 0.2, 0.3, 0.1]
    sub, r = crop(np.zeros(shape, np.uint8), [0.1, 0.2, 0.3, 0.1])
    assert sub.shape[:2] == (60, 300)


def test_template_multiscale():
    rng = np.random.default_rng(0)
    img = rng.integers(0, 255, (300, 400, 3), dtype=np.uint8)
    tpl = img[100:140, 200:260].copy()
    small = cv2.resize(img, None, fx=0.8, fy=0.8)
    score, x, y, w, h = match_template(small, tpl)
    assert score > 0.8 and abs(x - 160) <= 2 and abs(y - 80) <= 2
    hits = find_all(img, tpl, 0.9)
    assert len(hits) == 1


def test_template_library(tmp_path):
    lib = TemplateLibrary(tmp_path / "t")
    rng = np.random.default_rng(1)
    img = rng.integers(0, 255, (200, 200, 3), dtype=np.uint8)
    lib.add("botao_iniciar", img[20:60, 30:90])
    assert lib.keys() == ["botao_iniciar"]
    m = lib.best("botao_iniciar", img)
    assert m.score > 0.95 and m.center == (60, 40)
    found = find_known_options(img, lib, 0.9, prefix="botao_")
    assert found and found[0][0] == "botao_iniciar"


def test_digits_learn_and_read(tmp_path):
    r = DigitReader(tmp_path / "g.json")
    assert not r.trained
    assert r.learn(text_img("1234"), "1234")
    assert r.learn(text_img("5678"), "5678")
    assert r.learn(text_img("90"), "90")
    v, conf = r.read(text_img("4709"))
    assert v == 4709 and conf > 0.5
    r2 = DigitReader(tmp_path / "g.json")  # persistido
    assert r2.read(text_img("865"))[0] == 865
    assert not r.learn(text_img("12"), "123")  # quantidade de glifos não confere


def test_power_fill():
    bar = np.zeros((10, 100, 3), np.uint8)
    bar[:, :40] = (0, 0, 255)
    assert abs(power_fill(bar) - 40) < 2


def test_menu_tiles_detected():
    img = np.full((600, 1000, 3), 40, np.uint8)
    for r in range(2):
        for c in range(3):
            x, y = 120 + c * 250, 150 + r * 200
            cv2.rectangle(img, (x, y), (x + 180, y + 140), (90 + 40 * c, 140, 200), -1)
    tiles = detect_option_tiles(img)
    assert len(tiles) == 6
    assert tiles[0][0] < tiles[1][0] < tiles[2][0] and tiles[3][1] > tiles[0][1]


def test_image_io_unicode_path(tmp_path):
    img = text_img("7")
    p = save_image(tmp_path / "ação" / "x.png", img)
    assert np.array_equal(load_image(p), img)
    src = ImageSource(p)
    assert src.grab().shape == img.shape
    assert ArraySource(None).grab() is None


def _scene(tmp_path, me=(200, 400), enemy=(700, 350), wind_text="3"):
    """Cena sintética: marcadores, número do ângulo, vento e indicador de turno."""
    rng = np.random.default_rng(5)
    frame = np.full((600, 1000, 3), 60, np.uint8)
    me_tpl = rng.integers(0, 255, (24, 24, 3), dtype=np.uint8)
    en_tpl = rng.integers(0, 255, (24, 24, 3), dtype=np.uint8)
    turn_tpl = rng.integers(0, 255, (20, 40, 3), dtype=np.uint8)
    frame[me[1] - 12:me[1] + 12, me[0] - 12:me[0] + 12] = me_tpl
    frame[enemy[1] - 12:enemy[1] + 12, enemy[0] - 12:enemy[0] + 12] = en_tpl
    frame[20:40, 900:940] = turn_tpl
    frame[540:570, 20:110] = text_img("1234")
    frame[10:40, 450:540] = text_img(wind_text)
    cfg = Config(data={"regions": {"angle": [0.02, 0.9, 0.09, 0.05], "wind": [0.45, 0.0167, 0.09, 0.05],
                                   "turn_indicator": [0.88, 0.02, 0.1, 0.06]}})
    lib = TemplateLibrary(tmp_path / "tpl")
    lib.add("marcador_eu", me_tpl)
    lib.add("marcador_inimigo", en_tpl)
    lib.add("turno", turn_tpl)
    p = Perception(cfg, lib, tmp_path / "tpl")
    for reader in (p.angle_reader, p.wind_reader):
        reader.learn(text_img("1234"), "1234")
        reader.learn(text_img("5678"), "5678")
    return frame, p


def test_perception_scene(tmp_path):
    frame, p = _scene(tmp_path)
    snap = p.analyze(frame)
    assert snap.my_turn is True
    assert snap.angle is None  # 1234 > 90: leitura descartada
    assert abs(snap.me.x - 200) < 3 and abs(snap.enemies[0].x - 700) < 3
    assert snap.unit_px == 100
    d, dy, wind_rel, direction = to_ruler(snap, p.target(snap), 1.5)
    assert abs(d - 5.0) < 0.05 and abs(dy - 0.5) < 0.05 and direction == 1 and wind_rel == 1.5
    # vento sem setas capturadas: o valor é lido, mas sem direção ele não é usado (um sinal
    # chutado erraria o dobro do vento); fica registrado como magnitude e aviso
    assert snap.wind is None and snap.wind_magnitude == 3
    assert any("direção incerta" in w for w in snap.warnings)


def test_target_left_flips_wind(tmp_path):
    frame, p = _scene(tmp_path, me=(800, 400), enemy=(300, 350))
    snap = p.analyze(frame)
    d, dy, wind_rel, direction = to_ruler(snap, p.target(snap), 1.5)
    assert direction == -1 and wind_rel == -1.5


def test_wind_out_of_range_discarded(tmp_path):
    frame, p = _scene(tmp_path, wind_text="12")
    snap = p.analyze(frame)
    assert snap.wind is None and snap.wind_magnitude is None
    assert any("fora da faixa" in w for w in snap.warnings)


def test_digit_reader_rejects_noise(tmp_path):
    r = DigitReader(tmp_path / "g.json")
    r.learn(text_img("1234"), "1234")
    r.learn(text_img("5678"), "5678")
    noise = np.random.default_rng(3).integers(0, 255, (30, 90, 3), dtype=np.uint8)
    value, conf = r.read(noise)
    assert value is None


def test_digit_file_corrupted_does_not_crash(tmp_path):
    path = tmp_path / "g.json"
    path.write_text("{quebrado", encoding="utf-8")
    r = DigitReader(path)
    assert r.glyphs == {} and not path.exists()


def test_power_fill_ignores_marks_on_the_right():
    bar = np.zeros((10, 100, 3), np.uint8)
    bar[:, :30] = (0, 0, 255)
    bar[:, 80:83] = (0, 255, 0)  # marca colorida da força anterior
    assert abs(power_fill(bar) - 30) < 2


def test_find_all_other_scale_via_perception(tmp_path):
    frame, p = _scene(tmp_path)
    big = cv2.resize(frame, None, fx=1.25, fy=1.25)
    snap = p.analyze(big)
    assert snap.me is not None and abs(snap.me.x - 250) < 5


def test_template_names_cannot_escape(tmp_path):
    lib = TemplateLibrary(tmp_path / "t")
    import pytest
    with pytest.raises(ValueError):
        lib.add("../fora", np.zeros((5, 5, 3), np.uint8))
    assert not (tmp_path / "fora").exists()


def test_menu_rows_with_small_offsets():
    img = np.full((600, 1000, 3), 40, np.uint8)
    tops = [150, 165, 140]  # mesma linha com desalinhamento de alguns pixels
    for c, y in enumerate(tops):
        x = 120 + c * 250
        cv2.rectangle(img, (x, y), (x + 180, y + 140), (90 + 40 * c, 140, 200), -1)
    tiles = detect_option_tiles(img)
    assert [t[0] for t in tiles] == sorted(t[0] for t in tiles)


def test_learned_scale_and_late_template_still_found(tmp_path):
    """Escala memorizada acelera as buscas, mas um modelo de outro tamanho ainda é achado."""
    import cv2
    from ddbot.vision.templates import FULL_EVERY, TemplateLibrary
    rng = np.random.default_rng(5)
    lib = TemplateLibrary(tmp_path)
    a = rng.integers(0, 255, (40, 120, 3), dtype=np.uint8)
    b = rng.integers(0, 255, (40, 120, 3), dtype=np.uint8)
    lib.add("estado_a", a)
    lib.add("estado_b", b)
    frame = np.full((600, 1000, 3), 60, np.uint8)
    frame[100:140, 100:220] = a                                     # escala 1,0
    frame[300:350, 400:550] = cv2.resize(b, (150, 50))              # escala 1,25
    assert lib.best("estado_a", frame).score > 0.95
    found = [lib.best("estado_b", frame).score for _ in range(FULL_EVERY + 1)]
    assert max(found) > 0.9  # achado na busca completa periódica
    m = lib.best("estado_b", frame)
    assert m.score > 0.9 and abs(m.rect[0] - 400) <= 2 and abs(m.rect[2] - 150) <= 4


def test_marker_scale_uses_winning_sample(tmp_path):
    """Dois tamanhos de amostra do marcador: o tamanho vem da amostra que venceu."""
    import cv2
    from ddbot.config import Config
    from ddbot.vision.perception import Perception
    from ddbot.vision.templates import TemplateLibrary
    rng = np.random.default_rng(9)
    big = rng.integers(0, 255, (44, 44, 3), dtype=np.uint8)
    small = cv2.resize(rng.integers(0, 255, (30, 30, 3), dtype=np.uint8), (30, 30))
    lib = TemplateLibrary(tmp_path)
    lib.add("marcador_inimigo", big)
    lib.add("marcador_inimigo", small)
    frame = np.full((600, 1000, 3), 60, np.uint8)
    frame[300:330, 600:630] = small
    per = Perception(Config(data={}), lib, tmp_path)
    found = per._locate(frame, "inimigo", "marcador_inimigo", {"mode": "template"})
    assert found and abs(found[0].x - 615) < 3 and abs(found[0].y - 315) < 3


def test_wind_arrow_outside_digit_region_gives_direction(tmp_path):
    """Região do vento só com os números; a seta ao lado ainda dá o sentido, sem inverter duas vezes."""
    import cv2
    from ddbot.config import Config
    from ddbot.vision.perception import Perception, Snapshot
    from ddbot.vision.templates import TemplateLibrary

    def digits(t, w=70):
        img = np.zeros((30, w, 3), np.uint8)
        cv2.putText(img, t, (4, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        return img
    rng = np.random.default_rng(2)
    arrow_l = rng.integers(0, 255, (24, 24, 3), dtype=np.uint8)
    arrow_r = rng.integers(0, 255, (24, 24, 3), dtype=np.uint8)
    lib = TemplateLibrary(tmp_path)
    lib.add("vento_esquerda", arrow_l)
    lib.add("vento_direita", arrow_r)
    cfg = Config(data={"regions": {"wind": [0.5, 0.05, 0.07, 0.05]}})  # 70x30 em 1000x600
    per = Perception(cfg, lib, tmp_path)
    for t in ("12", "34", "5.6", "7.8", "90"):
        assert per.wind_reader.learn(digits(t), t)
    frame = np.zeros((600, 1000, 3), np.uint8)
    frame[30:60, 500:570] = digits("2.5")
    frame[33:57, 470:494] = arrow_l          # seta à esquerda, fora da região dos números
    snap = Snapshot(width=1000, height=600)
    per.read_wind(frame, snap)
    assert snap.wind == -2.5
    frame[33:57, 470:494] = arrow_r
    snap = Snapshot(width=1000, height=600)
    per.read_wind(frame, snap)
    assert snap.wind == 2.5


def test_victory_banner_over_battle_wins(tmp_path):
    from ddbot.config import Config
    from ddbot.vision.perception import Perception, Snapshot
    from ddbot.vision.templates import TemplateLibrary
    rng = np.random.default_rng(4)
    hud = rng.integers(0, 255, (40, 120, 3), dtype=np.uint8)
    win = rng.integers(0, 255, (40, 120, 3), dtype=np.uint8)
    lib = TemplateLibrary(tmp_path)
    lib.add("estado_batalha", hud)
    lib.add("estado_vitoria", win)
    frame = np.full((600, 1000, 3), 60, np.uint8)
    frame[500:540, 100:220] = hud                     # painel da batalha, intacto
    noisy = np.clip(win.astype(int) + rng.integers(-40, 40, win.shape), 0, 255).astype(np.uint8)
    frame[200:240, 440:560] = noisy                   # faixa de vitória, um pouco menos nítida
    snap = Snapshot(width=1000, height=600)
    Perception(Config(data={}), lib, tmp_path).classify_state(frame, snap)
    assert snap.state == "vitoria"


def test_template_with_a_wrong_learned_scale_is_searched_again(tmp_path):
    """Regressão: um modelo que memorizou uma escala errada (uma coincidência >= 0,80) nunca mais era procurado nas
    outras escalas depois que qualquer tela tinha sido reconhecida: aquela tela deixava de ser reconhecida até
    reabrir o programa."""
    from ddbot.vision.templates import FULL_EVERY, TemplateLibrary
    rng = np.random.default_rng(7)
    lib = TemplateLibrary(tmp_path)
    tpl = rng.integers(0, 255, (40, 120, 3), dtype=np.uint8)
    lib.add("estado_sala", tpl)
    frame = np.full((600, 1000, 3), 60, np.uint8)
    frame[200:240, 300:420] = tpl                       # na tela, na escala 1,0
    lib._scales[("estado_sala", 0, frame.shape[:2])] = 0.75  # escala errada memorizada
    lib._shape_scale[frame.shape[:2]] = 0.75                 # e outra tela já reconhecida nesse tamanho
    scores = [lib.best("estado_sala", frame).score for _ in range(FULL_EVERY + 1)]
    assert max(scores) > 0.95
    assert lib.best("estado_sala", frame).score > 0.95  # depois de achada, a escala certa fica memorizada


def test_unrecognized_screen_explains_the_closest_calibrated_screens(tmp_path):
    from ddbot.vision.perception import Perception, Snapshot
    rng = np.random.default_rng(8)
    lib = TemplateLibrary(tmp_path)
    lib.add("estado_lobby", rng.integers(0, 255, (40, 120, 3), dtype=np.uint8))
    lib.add("estado_sala", rng.integers(0, 255, (40, 120, 3), dtype=np.uint8))
    per = Perception(Config(data={}), lib, tmp_path)
    snap = Snapshot(width=1000, height=600)
    per.classify_state(np.full((600, 1000, 3), 60, np.uint8), snap)
    assert snap.state == "desconhecido"
    text = per.explain_state(snap)
    assert "Lobby" in text and "Sala/preparação" in text and "mínimo 0,80" in text
    assert set(snap.summary()["telas_parecidas"]) == {"Lobby", "Sala/preparação"}


def test_dialogs_over_the_room_win_over_the_room(tmp_path):
    """A janela de escolher a instância e o aviso de instância difícil aparecem por cima da sala."""
    from ddbot.vision.perception import Perception, Snapshot
    rng = np.random.default_rng(9)
    room, warn = (rng.integers(0, 255, (40, 120, 3), dtype=np.uint8) for _ in range(2))
    lib = TemplateLibrary(tmp_path)
    lib.add("estado_sala", room)
    lib.add("estado_aviso_sozinho", warn)
    frame = np.full((600, 1000, 3), 60, np.uint8)
    frame[500:540, 100:220] = room
    frame[200:240, 440:560] = np.clip(warn.astype(int) + rng.integers(-40, 40, warn.shape), 0, 255).astype(np.uint8)
    snap = Snapshot(width=1000, height=600)
    Perception(Config(data={}), lib, tmp_path).classify_state(frame, snap)
    assert snap.state == "aviso_sozinho"
