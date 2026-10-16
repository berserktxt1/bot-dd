"""Estados da faixa de estado da interface (lógica pura, sem Tkinter)."""
import pytest

from ddbot.activities import RunStatus
from ddbot.gui.states import UiSnapshot, advice, describe


def snap(**kw):
    base = dict(has_window=True, demo=False, activity_name="Labirinto")
    base.update(kw)
    return UiSnapshot(**base)


@pytest.mark.parametrize("s,kind,needle", [
    (snap(has_window=False, activity_name=None), "warning", "Jogo não encontrado"),
    (snap(activity_name=None), "idle", "Escolha o que jogar"),
    (snap(), "ready", "Pronto"),
    (snap(demo=True, has_window=False), "ready", "Pronto"),
    (snap(activity_auto=False), "warning", "outros jogadores"),
    (snap(alive=True, status=RunStatus.RUNNING, screen="lobby"), "running", "Executando"),
    (snap(alive=True, status=RunStatus.RUNNING, screen="batalha", my_turn=True), "combat", "seu turno"),
    (snap(alive=True, status=RunStatus.RUNNING, screen="batalha", my_turn=False), "combat", "adversário"),
    (snap(alive=True, status=RunStatus.RUNNING, unknown_screen=True), "warning", "não reconhecida"),
    (snap(alive=True, status=RunStatus.PAUSED, reason="pausado pelo usuário"), "paused", "Pausado"),
    (snap(status=RunStatus.FINISHED, reason="quantidade configurada concluída (3/3)"), "done", "Concluído"),
    (snap(status=RunStatus.FAILED, reason="o cliente mostra desconexão"), "error", "Interrompido"),
    (snap(emergency=True, alive=True, status=RunStatus.RUNNING), "emergency", "emergência"),
])
def test_banner_states(s, kind, needle):
    b = describe(s)
    assert b.kind == kind and needle in (b.title + b.detail)


def test_every_state_has_text_not_only_color():
    for kind in ("idle", "ready", "running", "combat", "paused", "done", "warning", "error", "emergency"):
        from ddbot.gui import theme
        bg, fg, icon = theme.STATE_STYLES[kind]
        assert icon  # ícone além da cor


def test_errors_come_with_guidance():
    assert "Calibração" in advice("botão 'botao_iniciar' não encontrado na tela 'sala'")
    assert "Configurações" in advice("automação não autorizada: confirme as regras do servidor")
    assert "frente" in advice("a janela do jogo perdeu o foco") or advice("foco")
    b = describe(snap(alive=True, status=RunStatus.PAUSED, reason="tela desconhecida por tempo demais"))
    assert "Calibração" in b.detail


def test_progress_text():
    b = describe(snap(alive=True, status=RunStatus.RUNNING, screen="sala", completed=2, runs=5))
    assert "2 de 5" in b.detail
    b = describe(snap(alive=True, status=RunStatus.RUNNING, screen="sala", completed=4, runs=0))
    assert "contínua" in b.detail


def test_contrast_of_palette():
    """Texto sobre fundo com contraste mínimo de 4,5:1 (WCAG AA)."""
    from ddbot.gui import theme as T

    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    def ratio(a, b):
        la, lb = sorted((lum(a), lum(b)), reverse=True)
        return (la + 0.05) / (lb + 0.05)
    pairs = [(T.INK, T.BG), (T.MUTED, T.BG), (T.MUTED, T.SURFACE), (T.BRASS, T.SURFACE), ("#FFFFFF", T.PRIMARY)]
    pairs += [(fg, bg) for bg, fg, _ in T.STATE_STYLES.values()]
    for fg, bg in pairs:
        assert ratio(fg, bg) >= 4.5, (fg, bg, round(ratio(fg, bg), 2))


@pytest.mark.parametrize("raw,expected", [
    ("tela: batalha", "Tela: Batalha"),
    ("clicou em botao_iniciar", "Clicou em Botão Iniciar na sala de preparação"),
    ("clicou em instancia_labirinto_azul", "Clicou em labirinto azul"),
    ("disparo #1: 68°/76.3 (fisica) -> acerto", "Disparo #1: 68°/76.3 (fisica): acerto"),
])
def test_history_messages_humanized(raw, expected):
    from ddbot.gui.states import humanize
    assert humanize(raw) == expected


def test_options_deduplicated():
    from types import SimpleNamespace as N

    from ddbot.gui.states import pick_options
    cands = [N(method="fisica")] * 6 + [N(method="a65"), N(method="high")]
    out = pick_options(cands)
    assert [c.method for c in out] == ["fisica", "fisica", "a65", "high"]


def test_paused_title_not_repeated():
    b = describe(snap(alive=True, status=RunStatus.PAUSED, reason="pausado pelo usuário"))
    assert b.title == "Pausado pelo usuário"
