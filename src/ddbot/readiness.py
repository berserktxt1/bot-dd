"""O que falta calibrar para uma atividade rodar sozinha no jogo real.

Sem as telas, os botões e as leituras do combate capturados do cliente do usuário, o bot
não reconhece nada e a rotina pararia em "tela desconhecida". Esta verificação diz antes
de começar exatamente o que falta e onde capturar.

Obrigatório: as telas em que o fluxo age (lobby, menu, sala, batalha, vitória, derrota),
os botões que o fluxo precisa clicar, e no combate o ângulo, o vento, o indicador de turno,
as setas do vento e os marcadores dos personagens. Telas e botões opcionais (carregando,
etapa concluída, recompensa, confirmar) só entram como recomendação.

Com uma estratégia de instância, os alvos (rainha, Barão...) e os estados (escudo, pavio)
também entram como recomendação: sem eles a etapa mira qualquer inimigo visível e o bot avisa.
"""
from __future__ import annotations

from dataclasses import dataclass

from .activities import COMMON_TEMPLATES, ActivityDef
from .vision.perception import STATE_LABELS

OPTIONAL_STATES = ("carregando", "etapa_concluida", "recompensa")


@dataclass
class Missing:
    label: str          # o que falta, como aparece na Calibração
    where: str          # aba/página da Calibração
    required: bool = True


def check(d: ActivityDef, has_template, config, angle_trained: bool, wind_trained: bool,
          profile=None) -> list[Missing]:
    out: list[Missing] = []
    for state, actions in d.flow.items():
        acts = {a.kind for a in actions}
        required = state not in OPTIONAL_STATES and bool(acts & {"clicar", "combate", "concluir"})
        if not has_template(f"estado_{state}"):
            out.append(Missing(f"tela {STATE_LABELS.get(state, state)}", "Calibração > Modelos", required))
        for a in actions:
            if a.kind in ("clicar", "clicar_opcional") and a.target and not has_template(a.target):
                if a.target.startswith(("instancia_", "partida_")):
                    label = f"opção {d.name} no menu"
                    where = "Calibração > Menu"
                else:
                    label = COMMON_TEMPLATES.get(a.target, a.target).split(" (")[0]
                    where = "Calibração > Modelos"
                out.append(Missing(label, where, a.kind == "clicar" and required))
    if any(a.kind == "combate" for acts in d.flow.values() for a in acts):
        g = config.get
        for key, label in (("angle", "região do número do ângulo"), ("wind", "região do vento"),
                           ("turn_indicator", "região do indicador de turno")):
            if not g(f"regions.{key}"):
                out.append(Missing(label, "Calibração > Regiões"))
        if not has_template("turno"):
            out.append(Missing("indicador de turno", "Calibração > Modelos"))
        if not angle_trained:
            out.append(Missing("números do ângulo", "Calibração > Números"))
        if not wind_trained:
            out.append(Missing("números do vento", "Calibração > Números"))
        for who, tpl, label in (("self", "marcador_eu", "marcador do seu personagem"),
                                ("enemy", "marcador_inimigo", "marcador de um inimigo")):
            mode = g(f"markers.{who}.mode", "template")
            ok = (bool(g(f"markers.{who}.hsv_low")) and bool(g(f"markers.{who}.hsv_high"))) if mode == "color" \
                else has_template(tpl)
            if not ok:
                out.append(Missing(label, "Calibração > Modelos"))
        for tpl in ("vento_esquerda", "vento_direita"):  # sem o sentido, o vento lido não é usado
            if not has_template(tpl):
                out.append(Missing(COMMON_TEMPLATES[tpl], "Calibração > Modelos"))
    if profile is not None:
        for tpl, label in profile.templates().items():
            if not has_template(tpl):
                out.append(Missing(label.split(" (")[0].lower(), "Calibração > Alvos da instância", False))
    # sem repetições (o mesmo botão em duas telas)
    seen, uniq = set(), []
    for m in out:
        if m.label not in seen:
            seen.add(m.label)
            uniq.append(m)
    return uniq


def summary(missing: list[Missing], limit: int = 5) -> str:
    req = [m.label for m in missing if m.required]
    if not req:
        return ""
    more = f" e mais {len(req) - limit}" if len(req) > limit else ""
    return ", ".join(req[:limit]) + more
