"""Qual janela é o jogo, qual é o launcher, e para onde os comandos podem ir.

O DDClássico é aberto por um launcher. Dependendo do launcher, o jogo aparece:
- numa janela própria de outro processo (título e classe diferentes do launcher); ou
- numa área interna (janela filha) do próprio launcher.

Nada aqui presume nomes. O usuário identifica uma vez, no assistente da interface, qual
janela é o jogo e qual é o launcher; o perfil guarda o executável e a classe de cada um
(sem coordenadas). Depois o bot reencontra o jogo sozinho, inclusive quando ele é reaberto.

Comandos:
- cliques só valem se o ponto estiver sobre a área do jogo (a janela escolhida ou uma
  janela interna dela), nunca sobre um botão do launcher;
- teclas só são enviadas se o foco do teclado estiver dentro da área do jogo.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .winapi import WindowInfo

GAME, LAUNCHER_ONLY, NOTHING, NO_PROFILE = "jogo", "launcher_sem_jogo", "nada", "sem_perfil"


@dataclass
class WindowRule:
    exe: str = ""               # nome do executável (comparação sem maiúsculas)
    cls: str = ""               # classe da janela ("" = qualquer)
    title_contains: str = ""    # trecho do título ("" = qualquer); títulos mudam, use só se preciso
    child: bool = False         # True = janela interna (área dentro de outra janela)

    def matches(self, w: WindowInfo) -> bool:
        if not self.exe or w.exe.lower() != self.exe.lower():
            return False
        if self.cls and w.cls != self.cls:
            return False
        if self.title_contains and self.title_contains.lower() not in w.title.lower():
            return False
        return bool(w.parent) == self.child

    @classmethod
    def of(cls, w: WindowInfo) -> "WindowRule":
        return cls(exe=w.exe, cls=w.cls, child=bool(w.parent))

    @classmethod
    def from_dict(cls, d) -> "WindowRule | None":
        if not isinstance(d, dict) or not d.get("exe"):
            return None
        return cls(exe=str(d["exe"]), cls=str(d.get("cls", "")), title_contains=str(d.get("title_contains", "")),
                   child=bool(d.get("child", False)))


@dataclass
class GameWindowProfile:
    game: WindowRule | None = None
    launcher: WindowRule | None = None

    @property
    def configured(self) -> bool:
        return self.game is not None

    def to_dict(self) -> dict:
        return {"game": asdict(self.game) if self.game else None,
                "launcher": asdict(self.launcher) if self.launcher else None}

    @classmethod
    def from_config(cls, config) -> "GameWindowProfile":
        raw = config.get("window.profile", {}) or {}
        return cls(WindowRule.from_dict(raw.get("game")), WindowRule.from_dict(raw.get("launcher")))


def validate_choice(game: WindowInfo, launcher: WindowInfo | None) -> str | None:
    """Erro legível se a escolha do assistente não fizer sentido; None se estiver ok."""
    if game is None:
        return "escolha a janela do jogo"
    if game.area < 200 * 150:
        return "a janela escolhida como jogo é pequena demais; escolha a área onde a batalha aparece"
    if launcher is not None:
        if launcher.hwnd == game.hwnd:
            return "a mesma janela não pode ser o jogo e o launcher"
        if not game.parent and WindowRule.of(game) == WindowRule.of(launcher):
            return ("o jogo e o launcher parecem a mesma janela; se o jogo aparece dentro do launcher, "
                    "escolha a área interna (janela interna) onde a batalha é desenhada")
    return None


@dataclass
class Located:
    state: str                      # jogo | launcher_sem_jogo | nada | sem_perfil
    game: WindowInfo | None = None
    launcher: WindowInfo | None = None
    candidates: int = 0

    @property
    def message(self) -> str:
        return {
            GAME: "Jogo encontrado",
            LAUNCHER_ONLY: "Launcher aberto; o jogo ainda não iniciou",
            NOTHING: "Launcher e jogo não encontrados",
            NO_PROFILE: "Janela do jogo ainda não identificada",
        }[self.state]


def locate(profile: GameWindowProfile, windows: list[WindowInfo]) -> Located:
    """Procura o jogo e o launcher numa lista de janelas (principais e internas)."""
    if not profile.configured:
        return Located(NO_PROFILE)
    games = [w for w in windows if profile.game.matches(w) and w.visible]
    launchers = [w for w in windows if profile.launcher and profile.launcher.matches(w)] if profile.launcher else []
    launcher = max(launchers, key=lambda w: w.area) if launchers else None
    # o jogo nunca pode ser o próprio launcher
    if launcher is not None:
        games = [w for w in games if w.hwnd != launcher.hwnd]
    if games:
        return Located(GAME, max(games, key=lambda w: w.area), launcher, len(games))
    if launcher is not None:
        return Located(LAUNCHER_ONLY, None, launcher)
    return Located(NOTHING)


def rank_candidates(windows: list[WindowInfo], keywords) -> list[WindowInfo]:
    """Ordem de sugestão no assistente: título/programa com as palavras-chave primeiro, depois as maiores.

    É só uma sugestão: quem confirma qual é o jogo é o usuário.
    """
    kws = [k.lower() for k in (keywords or [])]

    def score(w: WindowInfo):
        text = f"{w.title} {w.exe}".lower()
        return (any(k in text for k in kws), w.area)
    return sorted(windows, key=score, reverse=True)


def keyboard_ok(target: int, target_is_child: bool, foreground: int, focus: int, root_of, contains
                ) -> tuple[bool, str]:
    """Se as teclas enviadas agora chegariam ao jogo (e não ao launcher ou a outra janela).

    - a janela principal que contém o jogo precisa estar na frente;
    - jogo numa área interna do launcher: o foco do teclado precisa estar nessa área (um
      botão ou campo do launcher com foco receberia as teclas);
    - jogo em janela própria: o foco precisa estar nela ou numa janela interna dela.
    """
    if not foreground or root_of(foreground) != root_of(target):
        return False, "a janela do jogo não está na frente"
    if target_is_child:
        if not contains(target, focus):
            return False, "o foco do teclado está no launcher, não na área do jogo; clique dentro do jogo"
        return True, ""
    if focus and root_of(focus) != root_of(target):
        return False, "o foco do teclado está em outra janela"
    return True, ""
