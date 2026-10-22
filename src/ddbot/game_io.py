"""Implementações reais de BattleView (captura + visão) e Shooter (teclado)."""
from __future__ import annotations

import logging
import math
import time

from . import winapi
from .automation.input import InputController
from .automation.safety import Aborted
from .capture import FrameSource, WindowCapture
from .combat import BattleObservation, BattleView, Shooter, ShotOutcome
from .strategy import apply_plan
from .vision.perception import Perception, Snapshot, to_ruler

log = logging.getLogger(__name__)


class VisionBattleView(BattleView):
    """Lê o combate na tela. O alvo é mantido pela proximidade com a última posição vista,
    para que dois inimigos não se misturem quando um deles some (invisibilidade)."""

    def __init__(self, source: FrameSource, perception: Perception, config, planner=None):
        self.source = source
        self.perception = perception
        self.config = config
        self.planner = planner  # strategy.StrategyPlanner: escolhe o alvo pela etapa da instância
        self._plan_role: str | None = None
        self.last_frame = None
        self.last_snapshot: Snapshot | None = None
        self._target_px: tuple[float, float] | None = None
        self._lost_reads = 0
        self._target_seq = 0  # cada alvo novo tem o próprio histórico no rastreador

    # leituras seguidas sem o alvo seguido, com outro inimigo visível, até trocar de alvo (~2 s):
    # o seguido morreu ou sumiu de vez; não dá para ficar esperando por ele a batalha inteira
    RETARGET_READS = 12

    def reset(self):
        self._target_px = None
        self._lost_reads = 0
        self._plan_role = None

    def _pick_target(self, snap: Snapshot):
        if not snap.enemies:
            return None
        if self.perception.manual_target or self._target_px is None:
            return self.perception.target(snap)
        tx, ty = self._target_px
        best = min(snap.enemies, key=lambda e: math.hypot(e.x - tx, e.y - ty))
        gate = float(self.config.get("tracking.max_move_per_turn", 1.5)) * 2 * max(snap.unit_px, 1.0)
        if math.hypot(best.x - tx, best.y - ty) > gate:
            # o inimigo seguido sumiu; o que restou é outro. Por pouco tempo é invisibilidade (espera);
            # se continuar assim, troca para um inimigo que está de fato na tela (nada é inventado)
            self._lost_reads += 1
            if self._lost_reads < self.RETARGET_READS:
                return None
            log.info("alvo seguido sumiu por %d leituras; mirando outro inimigo visível", self._lost_reads)
            self._lost_reads = 0
            self._target_seq += 1
            return self.perception.target(snap)
        self._lost_reads = 0
        return best

    def observe(self) -> BattleObservation:
        frame = self.source.grab()
        if frame is None:
            why = getattr(self.source, "unavailable", "") or "sem imagem da janela"
            return BattleObservation(False, None, notes=[why])
        snap = self.perception.analyze(frame)
        self.last_frame, self.last_snapshot = frame, snap
        over = snap.state if snap.state in ("vitoria", "derrota") else None
        in_battle = snap.state == "batalha" or bool(snap.my_turn)
        angle = snap.angle if snap.angle_confidence >= 0.5 else None
        obs = BattleObservation(in_battle=in_battle, my_turn=snap.my_turn, battle_over=over, snapshot=snap,
                                current_angle=angle, notes=list(snap.warnings),
                                wind_screen=snap.wind, wind_confidence=snap.wind_confidence)
        if self.planner is not None and in_battle and not self.perception.manual_target:
            plan = self.planner.update(snap.enemies, snap.statuses, snap.me, snap.unit_px)
            target = apply_plan(obs, plan)
            if plan.role != self._plan_role:
                self._plan_role = plan.role
                self._target_seq += 1  # outro papel, outro histórico no rastreador
            obs.target_id = f"{plan.role or 'alvo'}_{self._target_seq}"
        else:
            target = self._pick_target(snap)
            obs.target_id = f"alvo_{self._target_seq}"
        conv = to_ruler(snap, target, snap.wind)
        obs.turn_score = snap.turn_confidence
        # (nome legível, confiança): a menor vira ``obs.confidence``; as que ficam abaixo do mínimo vão para a
        # mensagem de "disparo não executado", para o usuário saber o que recalibrar
        reads = [("indicador de turno", snap.turn_confidence if snap.my_turn else 1.0)]
        if snap.me:
            obs.me_x = snap.me.x / snap.unit_px
            obs.me_y = snap.me.y / snap.unit_px
            reads.append(("seu personagem", snap.me.confidence))
        if conv is not None:
            distance, dy, wind_rel, direction = conv
            obs.distance, obs.dy, obs.wind, obs.direction = distance, dy, wind_rel, direction
            obs.target_x, obs.target_y = target.x / snap.unit_px, target.y / snap.unit_px
            obs.target_visible = True
            self._target_px = (target.x, target.y)
            reads.append(("alvo", target.confidence))
        else:
            obs.target_visible = False
        # vento entra na confiança sempre (também quando o alvo está oculto)
        reads.append(("vento", snap.wind_confidence if snap.wind is not None else 0.0))
        obs.confidence = float(min(c for _, c in reads))
        min_conf = float(self.config.get("thresholds.vision_min_confidence", 0.7))
        for name, c in reads:
            if c >= min_conf:
                continue
            if name == "vento" and snap.wind is None:
                why = next((w for w in snap.warnings if "vento" in w), "vento não lido")
                obs.weak_reads.append(why)
            else:
                obs.weak_reads.append(f"{name} {c:.2f}".replace(".", ","))
        return obs


class KeyboardShooter(Shooter):
    """Ajusta direção e ângulo com as teclas e segura o disparo pelo tempo/força desejados.

    Nada é disparado sem confirmação: se o ângulo não for confirmado na tela, se o turno
    acabar durante o ajuste ou se a direção não puder ser garantida, o disparo é cancelado.
    """

    ANGLE_SETTLE_S = 0.12

    def __init__(self, inp: InputController, view: VisionBattleView, config):
        self.inp = inp
        self.view = view
        self.config = config
        self.assumed_angle: float | None = None
        self.assumed_facing: int | None = None

    def reset(self):
        """Nova batalha: direção e ângulo anteriores não valem mais."""
        self.assumed_angle = None
        self.assumed_facing = None

    def _keys(self):
        return self.config.get("automation.keys", {}) or {}

    def _grab_snap(self):
        frame = self.view.source.grab()
        if frame is None:
            return None, None
        return frame, Snapshot(width=frame.shape[1], height=frame.shape[0])

    def _read_angle(self):
        frame, snap = self._grab_snap()
        if frame is None:
            return None
        self.view.perception.read_angle(frame, snap)
        return snap.angle if snap.angle_confidence >= 0.5 else None

    def _stable_angle(self):
        """Lê o ângulo até duas leituras seguidas coincidirem (o número na tela demora a atualizar)."""
        last = None
        for _ in range(4):
            self.inp.sleep(self.ANGLE_SETTLE_S)
            value = self._read_angle()
            if value is not None and value == last:
                return value
            last = value
        return None  # leituras que nunca coincidiram (ex.: 44/45/44/45) não confirmam nada

    def face(self, direction: int):
        keys = self._keys()
        key = keys.get("face_left") if direction < 0 else keys.get("face_right")
        if self.assumed_facing == direction:
            return
        if not key:
            raise Aborted("configure as teclas de virar para a esquerda/direita: sem elas não dá para garantir "
                          "a direção do disparo")
        self.inp.tap(key)
        self.assumed_facing = direction

    def set_angle(self, target: int, current: float | None):
        keys = self._keys()
        up, down = keys.get("angle_up") or "up", keys.get("angle_down") or "down"
        max_presses = int(self.config.get("automation.max_angle_presses", 120))
        has_reader = bool(self.config.get("regions.angle")) and self.view.perception.angle_reader.trained
        if current is None and has_reader:
            current = self._stable_angle()
        if current is None:
            current = self.assumed_angle
        if current is None:
            raise Aborted("ângulo atual desconhecido: treine a leitura do ângulo em Calibração > Números")
        for _ in range(3):
            diff = int(round(target - current))
            if diff == 0:
                self.assumed_angle = target
                return
            if abs(diff) > max_presses:
                raise Aborted(f"ajuste de ângulo excessivo ({diff})")
            self.inp.tap(up if diff > 0 else down, abs(diff))
            if not has_reader:
                # sem leitura na tela só resta confiar na contagem de toques
                self.assumed_angle = target
                return
            read = self._stable_angle()
            if read is None:
                break
            current = read
        if current is not None and int(round(current)) == target:
            self.assumed_angle = target
            return
        self.assumed_angle = None
        raise Aborted(f"ângulo não confirmado na tela (queria {target}, lido {current})")

    def _still_my_turn(self) -> bool | None:
        if not self.config.get("regions.turn_indicator") or not self.view.perception.templates.has("turno"):
            return None
        frame, snap = self._grab_snap()
        if frame is None:
            return False
        self.view.perception.read_turn(frame, snap)
        return snap.my_turn

    def charge_and_fire(self, force: float):
        fire = self._keys().get("fire") or "space"
        full = float(self.config.get("automation.power_full_time_s", 3.33))
        # atraso de reação (captura + SendInput) compensado em pontos de força; calibrável
        force = max(1.0, force - float(self.config.get("automation.power_offset", 0.0)))
        # a barra só começa a encher um pouco depois da tecla descer (medido no DDClássico por terceiros)
        timed = float(self.config.get("automation.power_start_delay_s", 0.0)) + full * force / 100.0
        if self.config.get("automation.power_mode") == "visual" and self.config.get("regions.power_bar"):
            frame, snap = self._grab_snap()
            if frame is not None:
                self.view.perception.read_power(frame, snap)
            if frame is None or snap.power is None:
                log.warning("barra de força não lida: usando o tempo de carga")
            else:
                state = {"seen": False, "t0": time.monotonic()}

                def reached():
                    elapsed = time.monotonic() - state["t0"]
                    try:
                        f, s = self._grab_snap()
                        if f is not None:
                            self.view.perception.read_power(f, s)
                    except Exception:  # uma falha de captura no meio da carga não pode soltar a tecla cedo
                        log.debug("leitura da barra falhou durante a carga", exc_info=True)
                        f = None
                    power = None if f is None else s.power
                    if power is not None and power > 0:
                        state["seen"] = True
                        return power >= force - 0.5
                    # barra vazia/ilegível: sem nenhuma leitura boa até aqui, vale o tempo (modo por tempo)
                    return not state["seen"] and elapsed >= timed
                # nunca segura além do tempo estimado (+10%), mesmo com leituras boas
                if not self.inp.hold(fire, timed * 1.1 + 0.05, until=reached, poll_s=0.005):
                    log.warning("barra de força não atingiu %.1f na leitura; solto pelo tempo", force)
                elif not state["seen"]:
                    log.warning("barra de força não lida durante a carga: solto pelo tempo")
                return
        self.inp.hold(fire, timed)

    def shoot(self, angle, force, direction, obs) -> ShotOutcome:
        log.info("executando disparo: ângulo %s, força %.1f, direção %s", angle, force, direction)
        try:
            self.face(direction)
            self.set_angle(angle, obs.current_angle)
            if self._still_my_turn() is False:
                raise Aborted("o turno acabou durante o ajuste")
        except Aborted:
            # sem confirmar não atira; passa o turno se houver tecla configurada
            pass_key = self._keys().get("pass_turn")
            if pass_key and not self.inp.kill.triggered:
                log.warning("disparo cancelado: passando o turno")
                try:
                    self.inp.tap(pass_key)
                except Aborted:
                    pass
            raise
        self.charge_and_fire(force)
        return ShotOutcome()  # impacto real é marcado pelo usuário ou por detector futuro


# ------------------------------------------------------------ atividades (telas e botões)
from .activities import SELECTION_PREFIXES, Actor, ScreenReader, ScreenState  # noqa: E402
from .vision.templates import TemplateLibrary  # noqa: E402


class VisionScreenReader(ScreenReader):
    """Identifica a tela atual pelos modelos ``estado_*``.

    Janela minimizada/fechada e janela sem foco são estados próprios: a rotina pausa em vez
    de tentar "recuperar" com cliques numa tela que o bot não está vendo.
    """

    def __init__(self, source: FrameSource, perception: Perception, require_foreground: bool = True):
        self.source = source
        self.perception = perception
        self.require_foreground = require_foreground
        self.last: ScreenState | None = None

    def read(self) -> ScreenState:
        frame = self.source.grab()
        if frame is None:
            self.last = ScreenState("janela_indisponivel", 1.0, None,
                                    getattr(self.source, "unavailable", "") or "sem imagem da janela")
            return self.last
        if self.require_foreground and not self.source.is_foreground():
            self.last = ScreenState("janela_sem_foco", 1.0, frame, "a janela do jogo não está na frente")
            return self.last
        snap = Snapshot(width=frame.shape[1], height=frame.shape[0])
        self.perception.classify_state(frame, snap)
        self.last = ScreenState(snap.state, snap.state_confidence, frame, self.perception.explain_state(snap),
                                dict(snap.state_scores))
        return self.last


class GameActor(Actor):
    """Clica em botões localizados por modelo de imagem.

    Proteções: limiar de confiança; intervalo mínimo entre cliques no mesmo botão (devolve
    ``None`` = adiado, não "não encontrado"); a janela precisa ter o mesmo tamanho do quadro
    em que o botão foi achado; o ponto precisa cair dentro da área cliente e sobre a
    própria janela do jogo (nada de clicar em outra janela por cima nem fora da tela).

    A janela sob o ponto precisa ser a própria área do jogo ou uma janela interna dela. Com o
    jogo dentro do launcher, os botões do launcher têm a mesma janela principal: comparar só
    a janela principal deixaria o clique cair no launcher.

    ``window_at``/``contains`` consultam o Windows; os testes injetam versões simuladas para
    não depender do que estiver aberto na área de trabalho de quem roda a suíte.
    """

    AMBIGUITY_MARGIN = 0.03  # outra opção quase tão parecida no mesmo lugar: não dá para ter certeza

    def __init__(self, inp: InputController, source: FrameSource, templates: TemplateLibrary, config,
                 min_repeat_s: float = 1.0, clock=time.monotonic, window_at=None, contains=None):
        self.inp = inp
        self.source = source
        self.templates = templates
        self.config = config
        self.min_repeat_s = min_repeat_s
        self.clock = clock
        self.window_at = window_at or winapi.window_at
        self.contains = contains or winapi.is_same_or_child
        self._last_click: dict[str, float] = {}
        self.last_refusal = ""  # por que o último clique numa opção foi recusado (vai para a mensagem da pausa)

    def threshold(self) -> float:
        return float(self.config.get("thresholds.template", 0.8))

    def find(self, template: str, frame):
        if frame is None or not self.templates.has(template):
            return None
        m = self.templates.best(template, frame)
        return m if m and m.score >= self.threshold() else None

    def ambiguous(self, template: str, m, frame) -> str | None:
        """Outra opção do mesmo tipo (instância, partida ou dificuldade) casa no mesmo lugar quase tão bem.

        Ex.: Olimpíadas Bugou e Castelo do Reino de Bugou com cartões parecidos. Na dúvida o bot não
        clica: escolher a atividade errada é pior do que pausar.
        """
        prefix = next((p for p in SELECTION_PREFIXES if template.startswith(p)), None)
        if prefix is None:
            return None
        for other in self.templates.keys():
            if other == template or not other.startswith(prefix):
                continue
            o = self.templates.best(other, frame)
            if o and o.score >= self.threshold() and o.score >= m.score - self.AMBIGUITY_MARGIN \
                    and overlap(o.rect, m.rect) > 0.5:
                return f"a imagem também se parece com {other} ({o.score:.2f} contra {m.score:.2f})"
        return None

    def _screen_point(self, frame, cx, cy):
        info = getattr(self.source, "info", None)
        if info is None:
            if isinstance(self.source, WindowCapture):
                # a janela do jogo fechou (ou o launcher o reabriu) entre a leitura e o clique: sem ela
                # não há como saber onde clicar; nunca clica em coordenadas da área de trabalho
                log.warning("a janela do jogo não existe mais; clique cancelado")
                return None
            ox, oy = self.source.origin  # fontes de teste/imagem: só a origem
            return ox + cx, oy + cy
        h, w = frame.shape[:2]
        if (info.width, info.height) != (w, h):
            log.warning("janela mudou de tamanho entre a leitura e o clique; clique cancelado")
            return None
        x, y = info.left + cx, info.top + cy
        if not (info.left <= x < info.left + info.width and info.top <= y < info.top + info.height):
            return None
        under = self.window_at(x, y)
        if not under:
            # nenhuma janela no ponto: ele está fora de qualquer monitor (jogo parcialmente fora da tela)
            if winapi.IS_WINDOWS or self.window_at is not winapi.window_at:
                log.warning("o ponto do clique está fora da tela; clique cancelado")
                return None
        elif not self.contains(self.source.hwnd, under):
            log.warning("o ponto do clique não está sobre a área do jogo (launcher ou outra janela); "
                        "clique cancelado")
            return None
        return x, y

    def click(self, template: str, frame) -> bool | None:
        m = self.find(template, frame)
        if m is None:
            self.last_refusal = ""
            return False
        now = self.clock()
        if now - self._last_click.get(template, -1e9) < self.min_repeat_s:
            return None  # adiado: o mesmo botão foi clicado há instantes
        doubt = self.ambiguous(template, m, frame)
        if doubt:
            if doubt != self.last_refusal:
                log.warning("clique em %s recusado: %s", template, doubt)
            self.last_refusal = doubt
            return False
        cx, cy = m.center
        point = self._screen_point(frame, cx, cy)
        if point is None:
            return False
        self.last_refusal = ""
        self._last_click[template] = now
        log.info("clicando em %s (%.2f) em %d,%d", template, m.score, cx, cy)
        self.inp.click(*point)
        return True

    def press(self, key: str):
        self.inp.tap(key)

    def visible(self, template: str, frame) -> bool:
        m = self.find(template, frame)
        return m is not None and self.ambiguous(template, m, frame) is None


def overlap(a, b) -> float:
    """Fração da menor das duas áreas (x, y, w, h) que está dentro da outra."""
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    small = min(a[2] * a[3], b[2] * b[3])
    return (ix * iy) / small if small > 0 else 0.0
