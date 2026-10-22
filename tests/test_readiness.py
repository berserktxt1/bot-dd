"""Antes de jogar sozinho: o que falta calibrar, e a recusa clara em vez de travar em tela desconhecida."""
import numpy as np

from ddbot.activities import activity_from_option
from ddbot.config import Config
from ddbot.readiness import check, summary

FULL = {f"estado_{s}" for s in ("lobby", "cais_expedicao", "menu_partidas", "menu_instancias", "sala", "batalha",
                                 "vitoria", "derrota")} | {"botao_partidas", "botao_cais", "botao_criar_sala",
                                                           "botao_escolher_instancia", "botao_iniciar", "turno",
                                                           "marcador_eu", "marcador_inimigo", "vento_esquerda",
                                                           "vento_direita", "partida_x", "instancia_x", "botao_confirmar"}


def cfg(regions=True):
    c = Config(data={})
    if regions:
        for k in ("angle", "wind", "turn_indicator"):
            c.set(f"regions.{k}", [0.1, 0.1, 0.1, 0.1])
    return c


def test_nothing_calibrated_lists_essentials():
    d = activity_from_option("partida_x", "Treino", "partida")
    missing = check(d, lambda k: False, cfg(False), False, False)
    req = [m.label for m in missing if m.required]
    assert "tela Lobby" in req and "tela Batalha" in req and "opção Treino no menu" in req
    assert "números do ângulo" in req and "indicador de turno" in req
    # carregando, etapa e recompensa são recomendados, não obrigatórios
    assert all(not m.required for m in missing if m.label in ("tela Carregando", "tela Etapa concluída"))
    assert "e mais" in summary(missing)


def test_fully_calibrated_is_ready():
    d = activity_from_option("partida_x", "Treino", "partida")
    missing = check(d, lambda k: k in FULL, cfg(), True, True)
    assert summary(missing) == "" and all(not m.required for m in missing)


def test_color_markers_count_as_calibrated():
    d = activity_from_option("partida_x", "Treino", "partida")
    c = cfg()
    for who in ("self", "enemy"):
        c.set(f"markers.{who}.mode", "color")
        c.set(f"markers.{who}.hsv_low", [0, 0, 0])
        c.set(f"markers.{who}.hsv_high", [10, 255, 255])
    has = lambda k: k in FULL - {"marcador_eu", "marcador_inimigo"}  # noqa: E731
    assert summary(check(d, has, c, True, True)) == ""


def test_service_refuses_real_start_without_calibration(home):
    from ddbot.capture import ArraySource
    from ddbot.service import BotService
    svc = BotService(home, start_hotkey=False)
    try:
        svc.config.set("automation.server_rules_confirmed", True)
        svc.set_source(ArraySource(np.zeros((600, 1000, 3), np.uint8)))
        ok, why = svc.start(activity_from_option("instancia_x", "X"), 1, simulated=False)
        assert not ok and why.startswith("falta calibrar para jogar sozinho") and "tela Lobby" in why
        assert svc.runner is None  # nada foi enviado ao jogo
        # a demonstração não depende de calibração
        assert svc.start(activity_from_option("instancia_x", "X"), 1, simulated=True)[0]
        svc.stop()
    finally:
        svc.close()


def test_instance_lists_the_expedition_dock_path_in_order():
    """Instâncias pelo Cais de Expedição: a lista segue o caminho no jogo (lobby, Cais, Criar sala, sala, escolher)."""
    d = activity_from_option("instancia_x", "X")
    missing = check(d, lambda name: False, cfg(), True, True)
    labels = [m.label for m in missing if m.required]
    path = ["tela Lobby", "Botão Central / Cais de Expedição", "tela Cais de Expedição", "Botão Jogar / Criar sala",
            "tela Sala/preparação", "Botão da sala que abre a escolha da instância", "Botão Início",
            "tela Escolha da instância", "opção X no menu", "Botão OK depois de escolher a instância e a dificuldade"]
    assert [lab for lab in labels if lab in path] == path
    how = {m.label: m.how for m in missing}
    assert "Cais de Expedição" in how["tela Cais de Expedição"] and "dentro da sala" in how["tela Escolha da instância"]
    assert "na sala, abra a escolha da instância" in how["opção X no menu"]
    assert not [m for m in check(d, lambda name: name in FULL, cfg(), True, True) if m.required]  # nada obrigatório
