"""O que falta calibrar para uma atividade rodar sozinha no jogo real.

Sem as telas, os botões e as leituras do combate capturados do cliente do usuário, o bot
não reconhece nada e a rotina pararia em "tela desconhecida". Esta verificação diz antes
de começar exatamente o que falta, onde capturar e como fazer (uma frase objetiva por item).

Obrigatório: as telas em que o fluxo age (lobby, Cais de Expedição, sala, escolha, batalha, vitória, derrota),
os botões que o fluxo precisa clicar (inclusive a opção da instância e o botão da dificuldade),
e no combate o ângulo, o vento, o indicador de turno, as setas do vento e os marcadores dos
personagens (o de inimigo só é recomendado quando os alvos da instância cobrem todas as etapas). Telas e botões opcionais (carregando, etapa concluída, recompensa, confirmar) só
entram como recomendação.

Com uma estratégia de instância, os alvos (rainha, Barão...) e os estados (escudo, pavio)
entram como recomendação: sem eles a etapa mira qualquer inimigo visível e o bot avisa. Os alvos
de etapas que não são combate comum (pontuação, corrida, papéis que não podem ser atingidos)
são obrigatórios: sem eles a etapa não age.
"""
from __future__ import annotations

from dataclasses import dataclass

from .activities import CLICKS, COMMON_TEMPLATES, ActivityDef
from .vision.perception import REGION_KEYS, STATE_LABELS

OPTIONAL_STATES = ("carregando", "etapa_concluida", "recompensa", "aviso_sozinho")

# onde cada tela costuma ser vista (para dizer ao usuário quando capturar), já com a preposição:
# "Deixe o jogo na tela principal" (e não "em a tela principal")
STATE_HINTS = {
    "lobby": "na tela principal, depois de entrar no jogo",
    "cais_expedicao": "no Cais de Expedição (a lista de salas, aberta pelo botão do lobby)",
    "menu_instancias": "na janela de escolher a instância, aberta dentro da sala",
    "aviso_sozinho": "no aviso que aparece ao clicar em Iniciar sozinho numa instância difícil",
    "menu_partidas": "no menu em que se escolhe a modalidade de partida",
    "sala": "na sala, antes de iniciar (com ou sem instância escolhida)",
    "carregando": "na tela de carregamento da batalha",
    "batalha": "numa batalha em andamento",
    "vitoria": "na tela de vitória",
    "derrota": "na tela de derrota",
    "etapa_concluida": "no aviso de etapa concluída",
    "recompensa": "na tela das cartas/recompensas",
}


@dataclass
class Missing:
    label: str          # o que falta, como aparece na Calibração
    where: str          # aba/página da Calibração
    required: bool = True
    how: str = ""       # instrução objetiva
    key: str = ""       # modelo, região ou leitor (a Calibração já abre com ele escolhido)


def _how_state(state: str) -> str:
    label = STATE_LABELS.get(state, state)
    where = STATE_HINTS.get(state, f"na tela {label}")
    return (f"Deixe o jogo {where}, clique em Capturar tela do jogo, arraste sobre um pedaço que só "
            f"aparece nessa tela (um título ou botão fixo) e salve como \"Tela: {label}\".")


def _how_button(desc: str) -> str:
    return (f"Com esse botão visível no jogo, capture a tela, arraste só sobre o botão e salve como "
            f"\"{desc}\". Duas ou três amostras ajudam.")


def check(d: ActivityDef, has_template, config, angle_trained: bool, wind_trained: bool,
          profile=None, difficulty_labels: dict[str, str] | None = None,
          option_labels: dict[str, str] | None = None) -> list[Missing]:
    difficulty_labels = difficulty_labels or {}
    option_labels = option_labels or {}
    out: list[Missing] = []
    for state, actions in d.flow.items():
        acts = {a.kind for a in actions}
        required = state not in OPTIONAL_STATES and bool(acts & {"clicar", "combate", "concluir"})
        if not has_template(f"estado_{state}"):
            out.append(Missing(f"tela {STATE_LABELS.get(state, state)}", "Calibração > Modelos", required,
                               _how_state(state), f"estado_{state}"))
        for a in actions:
            if a.kind not in CLICKS or not a.target or has_template(a.target):
                continue
            need = a.kind == "clicar" and required
            if a.target.startswith(("instancia_", "partida_")):
                name = option_labels.get(a.target) or d.name
                where = ("na sala, abra a escolha da instância" if a.target.startswith("instancia_")
                         else "abra no jogo o menu de partidas")
                out.append(Missing(f"opção {name} no menu", "Calibração > Menu", need,
                                   f"No jogo, {where} com a opção {name} visível, capture a tela, clique em "
                                   f"Detectar opções, escolha a opção na lista e indique que ela é {name}.",
                                   a.target))
            elif a.target in difficulty_labels:
                desc = difficulty_labels[a.target]
                out.append(Missing(desc[:1].lower() + desc[1:], "Calibração > Modelos", need,
                                   "Na sala, abra a escolha da instância com uma instância escolhida, capture a "
                                   "tela, arraste "
                                   f"só sobre o botão e salve como \"{desc}\". Vale para todas as instâncias.",
                                   a.target))
            else:
                desc = COMMON_TEMPLATES.get(a.target, a.target)
                out.append(Missing(desc.split(" (")[0], "Calibração > Modelos", need, _how_button(desc), a.target))
    if any(a.kind == "combate" for acts in d.flow.values() for a in acts):
        g = config.get
        for key, label in (("angle", "região do número do ângulo"), ("wind", "região do vento"),
                           ("turn_indicator", "região do indicador de turno")):
            if not g(f"regions.{key}"):
                out.append(Missing(label, "Calibração > Regiões", True,
                                   "Numa batalha, capture a tela e clique em Sugerir regiões (confira na imagem), "
                                   f"ou arraste sobre a área e salve como \"{REGION_KEYS[key]}\".", key))
        if not has_template("turno"):
            out.append(Missing("indicador de turno", "Calibração > Modelos", True,
                               "No seu turno, capture a tela, arraste sobre o que indica que é a sua vez e salve "
                               f"como \"{COMMON_TEMPLATES['turno']}\".", "turno"))
        if not angle_trained:
            out.append(Missing("números do ângulo", "Calibração > Números", True,
                               "Com a região do ângulo salva, capture a tela numa batalha, digite o ângulo que "
                               "aparece e clique em Aprender. Repita com outros ângulos até cobrir de 0 a 9.",
                               "angle"))
        if not wind_trained:
            out.append(Missing("números do vento", "Calibração > Números", True,
                               "Com a região do vento salva (só os números, sem a seta), digite o vento que "
                               "aparece e clique em Aprender. Repita em turnos diferentes até cobrir de 0 a 9.",
                               "wind"))
        roles_cover = profile is not None and roles_cover_stages(profile, has_template)
        for who, tpl, label in (("self", "marcador_eu", "marcador do seu personagem"),
                                ("enemy", "marcador_inimigo", "marcador de um inimigo")):
            mode = g(f"markers.{who}.mode", "template")
            ok = (bool(g(f"markers.{who}.hsv_low")) and bool(g(f"markers.{who}.hsv_high"))) if mode == "color" \
                else has_template(tpl)
            if not ok:
                # com os alvos da instância capturados para todas as etapas (formiga e rainha, por exemplo), o
                # marcador genérico não é preciso para achar os inimigos: fica só como recomendação
                needed = not (who == "enemy" and roles_cover)
                out.append(Missing(label, "Calibração > Modelos", needed,
                                   f"Numa batalha, capture a tela, arraste sobre a marca (seta ou nome) acima do "
                                   f"personagem e salve como \"{COMMON_TEMPLATES[tpl]}\".", tpl))
        for tpl in ("vento_esquerda", "vento_direita"):  # sem o sentido, o vento lido não é usado
            if not has_template(tpl):
                out.append(Missing(COMMON_TEMPLATES[tpl], "Calibração > Modelos", True,
                                   "Quando o vento soprar nesse sentido, capture a tela, arraste só sobre a seta "
                                   f"do vento e salve como \"{COMMON_TEMPLATES[tpl]}\".", tpl))
    if profile is not None:
        needed = profile.required_templates()
        for tpl, label in profile.templates().items():
            if not has_template(tpl):
                name = label.split(" (")[0]
                out.append(Missing(name[:1].lower() + name[1:], "Calibração > Alvos da instância", tpl in needed,
                                   f"Numa batalha de {profile.name}, capture a tela, arraste sobre "
                                   f"{name.split(': ', 1)[-1].lower()} e salve em Alvos. Duas ou três amostras "
                                   "ajudam.", tpl))
    # sem repetições (o mesmo botão em duas telas)
    seen, uniq = set(), []
    for m in out:
        if m.label not in seen:
            seen.add(m.label)
            uniq.append(m)
    return uniq


def roles_cover_stages(profile, has_template) -> bool:
    """Toda etapa da estratégia tem pelo menos um alvo com papel (não genérico) cujo modelo foi capturado."""
    for st in profile.stages:
        roles = [r for r in st.targets if r in profile.roles and r not in st.ignore]
        if not any(has_template(profile.role_template(r)) for r in roles):
            return False
    return bool(profile.stages)


def summary(missing: list[Missing], limit: int = 5) -> str:
    req = [m.label for m in missing if m.required]
    if not req:
        return ""
    more = f" e mais {len(req) - limit}" if len(req) > limit else ""
    return ", ".join(req[:limit]) + more
