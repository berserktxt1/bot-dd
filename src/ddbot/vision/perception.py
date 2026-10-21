"""Percepção do jogo: combina estados, turno, vento, ângulo, força e personagens em um
``Snapshot`` com confianças explícitas. Também desenha a sobreposição de diagnóstico."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from ..config import Config
from .digits import DigitReader
from .regions import crop, expand, frac_to_px, valid_roi
from .templates import TemplateLibrary, find_all

log = logging.getLogger(__name__)

MAX_WIND = 10.0  # o indicador do jogo mostra valores pequenos; acima disso é leitura errada

# estados reconhecidos por modelos "estado_<nome>"
STATES = ["batalha", "vitoria", "derrota", "recompensa", "etapa_concluida", "lobby", "cais_expedicao",
          "menu_instancias", "aviso_sozinho", "menu_partidas", "sala", "carregando", "desconectado"]
# telas que aparecem POR CIMA de outra (cuja imagem continua visível atrás): reconhecidas, valem mais que ela
OVERLAY_STATES = ("vitoria", "derrota", "desconectado", "menu_instancias", "aviso_sozinho")
STATE_LABELS = {
    "batalha": "Batalha", "vitoria": "Vitória", "derrota": "Derrota", "recompensa": "Recompensa",
    "etapa_concluida": "Etapa concluída", "lobby": "Lobby", "cais_expedicao": "Cais de Expedição",
    "menu_instancias": "Escolha da instância", "aviso_sozinho": "Aviso de instância difícil (um jogador)",
    "menu_partidas": "Menu de partidas",
    "sala": "Sala/preparação", "carregando": "Carregando", "desconectado": "Desconectado",
    "desconhecido": "Desconhecido",
}
# regiões configuráveis (frações x, y, largura, altura da área cliente)
REGION_KEYS = {
    "angle": "Número do ângulo",
    "wind": "Indicador de vento",
    "power_bar": "Barra de força",
    "turn_indicator": "Indicador de turno",
    "playfield": "Área de jogo (régua de 10 partes)",
    "states": "Área dos avisos de estado (opcional)",
}


@dataclass
class Character:
    x: float          # pixels na área cliente
    y: float
    confidence: float
    kind: str         # "eu" | "inimigo"
    source: str       # "modelo" | "cor" | "manual"


@dataclass
class Snapshot:
    width: int = 0
    height: int = 0
    state: str = "desconhecido"
    state_confidence: float = 0.0
    my_turn: bool | None = None
    turn_confidence: float = 0.0
    wind: float | None = None           # + = soprando para a direita da tela
    wind_confidence: float = 0.0
    wind_magnitude: float | None = None  # valor lido quando a direção não foi reconhecida
    angle: float | None = None
    angle_confidence: float = 0.0
    power: float | None = None          # 0-100 lido da barra
    me: Character | None = None
    enemies: list[Character] = field(default_factory=list)  # ``kind``: papel na instância ou "inimigo"
    statuses: list[Character] = field(default_factory=list)  # estados especiais vistos (``kind`` = estado)
    unit_px: float = 0.0                # pixels por unidade de régua
    warnings: list[str] = field(default_factory=list)
    regions_px: dict = field(default_factory=dict)
    state_scores: dict = field(default_factory=dict)  # semelhança de cada tela calibrada (diagnóstico)

    def summary(self) -> dict:
        return {
            "estado": STATE_LABELS.get(self.state, self.state), "conf_estado": round(self.state_confidence, 2),
            "meu_turno": self.my_turn, "vento": self.wind, "angulo": self.angle, "forca": self.power,
            "eu": None if not self.me else (round(self.me.x), round(self.me.y)),
            "inimigos": len(self.enemies), "avisos": self.warnings,
            # semelhança das telas calibradas (as 4 maiores): mostra por que uma tela não foi reconhecida
            "telas_parecidas": {STATE_LABELS.get(st, st): round(sc, 2) for st, sc in
                                sorted(self.state_scores.items(), key=lambda kv: -kv[1])[:4]},
        }


class Perception:
    def __init__(self, config: Config, templates: TemplateLibrary, glyph_dir: Path):
        self.config = config
        self.templates = templates
        self.angle_reader = DigitReader(Path(glyph_dir) / "glifos_angulo.json")
        self.wind_reader = DigitReader(Path(glyph_dir) / "glifos_vento.json")
        self.manual_me: tuple[float, float] | None = None       # frações da área cliente
        self.manual_target: tuple[float, float] | None = None
        self.selected_enemy: int = 0
        self.profile = None  # InstanceProfile da rotina: reconhece papéis (rainha, Barão...) e estados

    # ------------------------------------------------------------------ regiões
    def region(self, key):
        if key == "playfield":
            return self.config.get("ruler.playfield")
        return self.config.get(f"regions.{key}")

    def threshold(self):
        return float(self.config.get("thresholds.template", 0.8))

    def explain_state(self, snap: Snapshot, top: int = 3) -> str:
        """Por que a tela foi (ou não) reconhecida: as telas calibradas mais parecidas, com a nota, e o mínimo."""
        if not snap.state_scores:
            return "nenhuma tela calibrada (Calibração > Modelos)"
        ranked = sorted(snap.state_scores.items(), key=lambda kv: -kv[1])[:top]
        parts = ", ".join(f"{STATE_LABELS.get(st, st)} {sc:.2f}".replace(".", ",") for st, sc in ranked)
        return f"mais parecidas: {parts} (mínimo {self.threshold():.2f})".replace(".", ",")

    # ------------------------------------------------------------------ leitura
    def classify_state(self, img, snap: Snapshot):
        roi = self.region("states")
        sub, (ox, oy, _, _) = crop(img, roi)
        best, best_score = "desconhecido", 0.0
        scores = {}
        for st in STATES:
            key = f"estado_{st}"
            if not self.templates.has(key):
                continue
            m = self.templates.best(key, sub, (ox, oy))
            if m:
                scores[st] = m.score
            if m and m.score > best_score:
                best, best_score = st, m.score
        # o aviso de resultado/desconexão aparece POR CIMA da batalha (cujo painel continua visível); a
        # janela de escolher a instância e o aviso de instância difícil, por cima da sala: reconhecidos,
        # valem mais que a tela de baixo, mesmo com semelhança um pouco menor
        over = [(sc, st) for st, sc in scores.items() if st in OVERLAY_STATES and sc >= self.threshold()]
        if over:
            best_score, best = max(over)
        snap.state_scores = scores
        if best_score >= self.threshold():
            snap.state, snap.state_confidence = best, best_score
        else:
            snap.state, snap.state_confidence = "desconhecido", best_score
            if not any(self.templates.has(f"estado_{s}") for s in STATES):
                snap.warnings.append("nenhum modelo de estado capturado (Calibração > Modelos)")

    def read_turn(self, img, snap: Snapshot):
        roi = self.region("turn_indicator")
        if roi is None or not self.templates.has("turno"):
            snap.my_turn = None
            snap.warnings.append("indicador de turno não calibrado")
            return
        sub, (ox, oy, _, _) = crop(img, roi)
        m = self.templates.best("turno", sub, (ox, oy))
        snap.turn_confidence = m.score if m else 0.0
        snap.my_turn = bool(m and m.score >= self.threshold())

    def read_wind(self, img, snap: Snapshot):
        roi = self.region("wind")
        if roi is None:
            snap.warnings.append("região do vento não calibrada")
            return
        sub, (ox, oy, _, _) = crop(img, roi)
        value, conf = self.wind_reader.read(sub)
        if value is None:
            snap.warnings.append("vento não reconhecido (treine os dígitos do vento)")
            return
        if abs(value) > MAX_WIND:
            snap.warnings.append(f"vento lido fora da faixa ({value}); leitura descartada")
            return
        direction, dconf = 0, 0.0
        value = abs(value)  # o sentido vem só das setas (um "-" lido junto não pode inverter de novo)
        # as setas ficam ao lado dos números: procura numa área maior que a dos dígitos, para a região
        # dos dígitos poder ser justa (uma seta dentro dela viraria um "dígito" a mais)
        arrows, _ = crop(img, expand(roi, 1.0, 0.75))
        left = self.templates.best("vento_esquerda", arrows) if self.templates.has("vento_esquerda") else None
        right = self.templates.best("vento_direita", arrows) if self.templates.has("vento_direita") else None
        ls = left.score if left else 0.0
        rs = right.score if right else 0.0
        if max(ls, rs) >= self.threshold() * 0.9 and abs(ls - rs) > 0.05:
            direction, dconf = (-1 if ls > rs else 1), max(ls, rs)
        if value == 0:
            direction, dconf = 1, conf
        if direction == 0:
            # sem o sentido não dá para usar o vento: um sinal chutado erra o dobro
            snap.warnings.append(f"vento {value} com direção incerta (capture as setas do vento)")
            snap.wind_magnitude = value
            return
        snap.wind, snap.wind_confidence = direction * value, min(conf, dconf)

    def read_angle(self, img, snap: Snapshot):
        roi = self.region("angle")
        if roi is None:
            return
        sub, _ = crop(img, roi)
        value, conf = self.angle_reader.read(sub)
        if value is not None and 0 <= value <= 90:
            snap.angle, snap.angle_confidence = value, conf

    def read_power(self, img, snap: Snapshot):
        roi = self.region("power_bar")
        if roi is None:
            return
        snap.power = power_fill(crop(img, roi)[0], self.config.get("markers.power_hsv"))

    def _locate(self, img, kind, key, cfg):
        pf = self.region("playfield")
        sub, (ox, oy, _, _) = crop(img, pf)
        found: list[Character] = []
        if cfg.get("mode") == "color" and cfg.get("hsv_low") and cfg.get("hsv_high"):
            hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, np.array(cfg["hsv_low"]), np.array(cfg["hsv_high"]))
            n, _, stats, cents = cv2.connectedComponentsWithStats(mask)
            min_area = max(12, sub.shape[0] * sub.shape[1] // 40000)
            for i in range(1, n):
                if stats[i][4] >= min_area:
                    found.append(Character(cents[i][0] + ox, cents[i][1] + oy, 0.75, kind, "cor"))
        elif self.templates.has(key):
            # escala do marcador pela melhor ocorrência (zoom/resolução diferentes da captura), com a
            # amostra que venceu: o tamanho de uma amostra não serve para outra de tamanho diferente
            best = self.templates.best(key, sub)
            tpl = self.templates.get(key)[best.template if best else 0]
            scale = (best.rect[2] / tpl.shape[1]) if best and best.score >= self.threshold() else 1.0
            for score, x, y, w, h in find_all(sub, tpl, self.threshold(), scale=scale,
                                              max_hits=1 if kind == "eu" else 8):
                found.append(Character(x + w / 2 + ox, y + h / 2 + oy, score, kind, "modelo"))
        return found

    def locate_characters(self, img, snap: Snapshot):
        h, w = img.shape[:2]
        me = self._locate(img, "eu", "marcador_eu", self.config.get("markers.self", {}))
        enemies = self._locate(img, "inimigo", "marcador_inimigo", self.config.get("markers.enemy", {}))
        if self.manual_me:
            me = [Character(self.manual_me[0] * w, self.manual_me[1] * h, 1.0, "eu", "manual")]
        if self.manual_target:
            enemies = [Character(self.manual_target[0] * w, self.manual_target[1] * h, 1.0, "inimigo", "manual")]
        snap.me = max(me, key=lambda c: c.confidence) if me else None
        if snap.me:
            enemies = [e for e in enemies if abs(e.x - snap.me.x) > 5 or abs(e.y - snap.me.y) > 5]
        if self.profile is not None and not self.manual_target:
            enemies = self._with_roles(img, snap, enemies)
        snap.enemies = sorted(enemies, key=lambda c: c.x)
        if snap.me is None:
            snap.warnings.append("meu personagem não localizado (calibre o marcador ou marque manualmente)")
        if not snap.enemies:
            snap.warnings.append("nenhum inimigo localizado")

    def _with_roles(self, img, snap: Snapshot, generic: list[Character]) -> list[Character]:
        """Inimigos com papel (modelos ``alvo_<instancia>_<papel>``) e estados (``status_...``).

        O mesmo inimigo achado pelo marcador genérico e pelo modelo do papel fica uma vez só,
        com o papel. A distância para juntar os dois é medida na régua (o marcador costuma
        ficar acima do corpo).
        """
        p = self.profile
        pf = frac_to_px(self.region("playfield") or [0, 0, 1, 1], img.shape)
        unit = pf[2] / float(self.config.get("ruler.units_per_screen", 10))
        found: list[Character] = []
        for role in p.roles:
            key = p.role_template(role)
            if self.templates.has(key):
                found += self._locate(img, role, key, {})
        # uma ocorrência por inimigo: no mesmo lugar fica o papel de maior semelhança (o modelo de um
        # lacaio pode casar com o chefe, e o chefe não pode virar lacaio por vir antes na lista)
        roles: list[Character] = []
        for c in sorted(found, key=lambda c: c.confidence, reverse=True):
            if all(abs(c.x - o.x) > 0.4 * unit or abs(c.y - o.y) > 0.4 * unit for o in roles):
                roles.append(c)
        for st in p.statuses:
            key = p.status_template(st)
            if self.templates.has(key):
                snap.statuses += self._locate(img, st, key, {})
        if snap.me:
            roles = [e for e in roles if abs(e.x - snap.me.x) > 5 or abs(e.y - snap.me.y) > 5]
        rest = [g for g in generic
                if all(abs(g.x - r.x) > 0.6 * unit or abs(g.y - r.y) > 1.5 * unit for r in roles)]
        return roles + rest

    # --------------------------------------------------------------- principal
    def analyze(self, img: np.ndarray) -> Snapshot:
        h, w = img.shape[:2]
        snap = Snapshot(width=w, height=h)
        pf = frac_to_px(self.region("playfield") or [0, 0, 1, 1], img.shape)
        snap.unit_px = pf[2] / float(self.config.get("ruler.units_per_screen", 10))
        for key in REGION_KEYS:
            roi = self.region(key)
            if roi:
                if not valid_roi(roi):
                    snap.warnings.append(f"região '{REGION_KEYS[key]}' inválida: selecione de novo em Calibração")
                    continue
                snap.regions_px[key] = frac_to_px(roi, img.shape)
        for step in (self.classify_state, self.read_turn, self.read_wind, self.read_angle,
                     self.read_power, self.locate_characters):
            try:
                step(img, snap)
            except Exception as exc:  # um leitor com erro não derruba os outros
                log.exception("falha em %s", step.__name__)
                snap.warnings.append(f"erro em {step.__name__}: {exc}")
        return snap

    def target(self, snap: Snapshot) -> Character | None:
        if not snap.enemies:
            return None
        return snap.enemies[min(self.selected_enemy, len(snap.enemies) - 1)]


def power_fill(bar: np.ndarray, hsv_cfg=None) -> float | None:
    """Fração preenchida da barra (0-100) pela coluna mais à direita com cor saturada."""
    if bar is None or bar.size == 0:
        return None
    hsv = cv2.cvtColor(bar, cv2.COLOR_BGR2HSV)
    if hsv_cfg and hsv_cfg.get("low") and hsv_cfg.get("high"):
        mask = cv2.inRange(hsv, np.array(hsv_cfg["low"]), np.array(hsv_cfg["high"]))
    else:
        mask = ((hsv[..., 1] > 90) & (hsv[..., 2] > 90)).astype(np.uint8) * 255
    cols = (mask > 0).mean(axis=0) > 0.4
    if not cols.any() or not cols[:max(1, len(cols) // 50 + 1)].any():
        return 0.0
    # trecho contínuo a partir da esquerda: marcas coloridas à direita não contam
    gaps = np.nonzero(~cols)[0]
    filled = int(gaps[0]) if len(gaps) else len(cols)
    return float(filled / len(cols) * 100.0)


def to_ruler(snap: Snapshot, target: Character, wind_screen: float | None):
    """Converte pixels para distância/altura em régua e vento relativo ao disparo."""
    if snap.me is None or target is None or snap.unit_px <= 0:
        return None
    dx_px = target.x - snap.me.x
    direction = 1 if dx_px >= 0 else -1
    distance = abs(dx_px) / snap.unit_px
    dy = (snap.me.y - target.y) / snap.unit_px
    wind_rel = None if wind_screen is None else wind_screen * direction
    return distance, dy, wind_rel, direction


def draw_overlay(img: np.ndarray, snap: Snapshot, recommendation=None, trajectory_px=None) -> np.ndarray:
    out = img.copy()
    colors = {"angle": (0, 200, 255), "wind": (255, 200, 0), "power_bar": (0, 255, 0),
              "turn_indicator": (255, 0, 255), "playfield": (180, 180, 180), "states": (120, 120, 255)}
    for key, (x, y, w, h) in snap.regions_px.items():
        cv2.rectangle(out, (x, y), (x + w, y + h), colors.get(key, (255, 255, 255)), 2)
        cv2.putText(out, key, (x + 3, y + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, colors.get(key, (255, 255, 255)), 1)
    if "playfield" in snap.regions_px and snap.unit_px > 0:
        x, y, w, h = snap.regions_px["playfield"]
        for i in range(11):
            xi = int(x + i * snap.unit_px)
            cv2.line(out, (xi, y + h - 12), (xi, y + h), (200, 200, 200), 1)
    if snap.me:
        cv2.circle(out, (int(snap.me.x), int(snap.me.y)), 14, (0, 255, 0), 2)
        cv2.putText(out, f"EU {snap.me.confidence:.2f}", (int(snap.me.x) + 16, int(snap.me.y)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    for i, e in enumerate(snap.enemies):
        cv2.circle(out, (int(e.x), int(e.y)), 14, (0, 0, 255), 2)
        cv2.putText(out, f"INIMIGO {i + 1} {e.confidence:.2f}", (int(e.x) + 16, int(e.y)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    if trajectory_px is not None and len(trajectory_px) > 1:
        pts = np.asarray(trajectory_px, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(out, [pts], False, (0, 255, 255), 2)
    lines = [f"Estado: {STATE_LABELS.get(snap.state, snap.state)} ({snap.state_confidence:.2f})",
             f"Meu turno: {snap.my_turn}  Vento: {snap.wind}  Angulo: {snap.angle}  Forca: "
             f"{None if snap.power is None else round(snap.power)}"]
    if recommendation is not None and recommendation.best:
        b = recommendation.best
        lines.append(f"Sugestao: {b.angle} graus / forca {b.force:.1f} ({b.method}, P~{b.hit_probability:.0%})")
    for i, text in enumerate(lines):
        cv2.putText(out, text, (10, 22 + 20 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
        cv2.putText(out, text, (10, 22 + 20 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    return out
