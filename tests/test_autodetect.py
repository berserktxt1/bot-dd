"""Sugestão automática das regiões do combate (imagens sintéticas; nenhuma captura do DDClássico)."""
import cv2
import numpy as np

from ddbot.vision.autodetect import angle_from_change, draw_suggestions, find_playfield, suggest_regions


def hud(angle="45", wind="2.5", letterbox=40, seed=3):
    """Tela parecida com a de um DDTank: cenário, terreno, painel de baixo com a barra e o ângulo, vento no alto."""
    rng = np.random.default_rng(seed)
    W, H = 1000, 600
    img = np.full((H, W, 3), (140, 110, 70), np.uint8)
    for _ in range(60):
        x, y, r = int(rng.integers(0, W)), int(rng.integers(60, 420)), int(rng.integers(10, 40))
        cv2.circle(img, (x, y), r, tuple(int(c) for c in rng.integers(40, 200, 3)), -1)
    cv2.fillPoly(img, [np.array([[0, 420], [200, 380], [400, 430], [600, 390], [800, 440], [1000, 400],
                                 [1000, 600], [0, 600]])], (40, 120, 60))
    cv2.rectangle(img, (0, 520), (1000, 600), (30, 30, 30), -1)
    cv2.rectangle(img, (220, 560), (780, 580), (200, 200, 200), 2)
    cv2.rectangle(img, (222, 562), (500, 578), (0, 140, 255), -1)
    cv2.putText(img, angle, (30, 575), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    cv2.rectangle(img, (440, 8), (560, 48), (20, 20, 20), -1)
    cv2.putText(img, wind, (478, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    frame = np.zeros((H, W + 2 * letterbox, 3), np.uint8)
    frame[:, letterbox:letterbox + W] = img
    return frame


def text_box(text, org, scale, thick=2):
    """Caixa verdadeira de um texto desenhado com cv2.putText (x0, y0, x1, y1)."""
    (tw, th), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    return org[0], org[1] - th, org[0] + tw, org[1] + base


def to_px(roi, shape):
    h, w = shape[:2]
    x, y, rw, rh = roi
    return x * w, y * h, (x + rw) * w, (y + rh) * h


def contains(roi, shape, box):
    """A região sugerida (em frações) cobre a caixa verdadeira (em pixels), sem ser enorme."""
    x0, y0, x1, y1 = to_px(roi, shape)
    bx0, by0, bx1, by1 = box
    big = (x1 - x0) * (y1 - y0) <= 6 * (bx1 - bx0) * (by1 - by0)
    return x0 <= bx0 + 3 and y0 <= by0 + 3 and x1 >= bx1 - 3 and y1 >= by1 - 3 and big


def test_suggests_power_bar_angle_wind_and_playfield():
    frame = hud()
    found = {s.key: s for s in suggest_regions(frame)}
    assert set(found) == {"playfield", "power_bar", "angle", "wind"}
    off = 40  # faixa preta à esquerda
    assert contains(found["power_bar"].roi, frame.shape, (220 + off, 560, 780 + off, 580))
    assert contains(found["angle"].roi, frame.shape, text_box("45", (30 + off, 575), 1.0))
    assert contains(found["wind"].roi, frame.shape, text_box("2.5", (478 + off, 40), 0.9))
    x0, y0, x1, y1 = to_px(found["playfield"].roi, frame.shape)
    assert abs(x0 - off) <= 2 and abs(x1 - (1000 + off)) <= 2  # a faixa preta fica fora da régua
    for s in found.values():
        assert 0 < s.confidence <= 1 and s.why
        assert all(isinstance(v, float) for v in s.roi)  # vai para o config.json
    assert draw_suggestions(frame, list(found.values())).shape == frame.shape


def test_no_letterbox_no_playfield_suggestion():
    assert find_playfield(hud(letterbox=0)) is None


def test_blank_image_suggests_nothing():
    assert suggest_regions(np.zeros((600, 1000, 3), np.uint8)) == []


def test_angle_region_from_key_press_difference():
    before, after = hud(angle="45"), hud(angle="46")
    s = angle_from_change(before, after)
    assert s is not None and s.key == "angle" and contains(s.roi, before.shape, text_box("46", (70, 575), 1.0))
    assert angle_from_change(before, before) is None  # nada mudou: não inventa
    moved = np.roll(before, 25, axis=1)
    assert angle_from_change(before, moved) is None  # a câmera andou: mudou a tela toda
