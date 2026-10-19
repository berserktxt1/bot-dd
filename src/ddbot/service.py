"""Camada de aplicação: monta e liga todos os componentes. A GUI só conversa com ela.

Separação:
- percepção: ``capture`` + ``vision`` (o que está na tela, com confiança);
- decisão: ``aiming``, ``tracking``, ``combat`` e ``activities`` (o que fazer);
- execução: ``automation`` (teclado/mouse com travas) ou executores simulados.
"""
from __future__ import annotations

import logging
import queue
import shutil
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import __version__, winapi
from .activities import (ActivityDef, ActivityRunner, RunLimits, RunStatus, activity_from_option,
                         load_activities, slug, unique_slug)
from .aiming import Aimer, ShotContext, Weapon
from .automation.input import InputBackend, InputController
from .automation.safety import HotkeyListener, KillSwitch
from .calibration import Calibrator, ShotStore
from .capture import FrameSource, WindowCapture, save_image
from .combat import CombatEngine, Mode
from .config import Config
from .game_io import GameActor, KeyboardShooter, VisionBattleView, VisionScreenReader
from .detection import Detection, detect
from .game_window import GAME, LAUNCHER_ONLY, GameWindowProfile, WindowRule, rank_candidates, validate_choice
from .knowledge import KnowledgeBase
from .log import setup_logging
from .paths import Paths
from .physics import PhysicsParams
from .strategy import InstanceProfile, StrategyPlanner, load_profiles, match_profile
from .tracking import TargetTracker
from .util import mask_home
from .vision.perception import Perception, Snapshot
from .vision.templates import TemplateLibrary

log = logging.getLogger(__name__)

MAX_CAPTURES = 200


@dataclass
class HistoryEntry:
    when: float
    kind: str
    message: str
    data: dict = field(default_factory=dict)


def _load_or_restore(path: Path, packaged: Path, loader, what: str, notes: list[str]):
    """Carrega um arquivo do usuário; se estiver corrompido, guarda-o e volta à cópia do programa."""
    try:
        return loader(path)
    except Exception as exc:
        if not packaged.exists():
            raise
        bad = path.with_name(f"{path.stem}.corrompido-{time.strftime('%Y%m%d-%H%M%S')}{path.suffix}")
        try:
            if path.exists():
                path.replace(bad)
        except OSError:
            pass
        shutil.copy2(packaged, path)
        notes.append(f"{what} estava inválido ({exc}); restaurado o original do programa")
        return loader(path)


class BotService:
    def __init__(self, home: Path | None = None, input_backend: InputBackend | None = None,
                 start_hotkey: bool = True):
        self.paths = Paths(home)
        self.log_file = setup_logging(self.paths.logs)
        log.info("JonFlow %s, dados em %s", __version__, mask_home(str(self.paths.root)))
        self.startup_notes: list[str] = list(self.paths.notes)
        self.config = Config(self.paths.config_file)
        self.startup_notes += self.config.problems
        pk = self.paths.resources / "data" / "knowledge"
        self.kb = _load_or_restore(self.paths.knowledge / "angle_tables.json", pk / "angle_tables.json",
                                   lambda p: KnowledgeBase(self.paths.data_dir), "a base de tabelas",
                                   self.startup_notes)
        self.params = _load_or_restore(self.paths.knowledge / "model_params.json", pk / "model_params.json",
                                       PhysicsParams.load, "o modelo físico", self.startup_notes)
        self.store = ShotStore(self.paths.db)
        self.calibrator = Calibrator(self.store, self.params, weapon_lookup=self.weapon_by_name)
        self.aimer = Aimer(self.kb, self.params, self.calibrator)
        self.templates = TemplateLibrary(self.paths.templates)
        self.perception = Perception(self.config, self.templates, self.paths.templates)
        self.profiles, errors = load_profiles(self.paths.knowledge / "instances.json")
        if errors or not self.profiles:
            self.profiles, _ = load_profiles(pk / "instances.json")
            self.startup_notes += [f"perfis de instância: {e}" for e in errors]
        self.kill = KillSwitch()
        self.events: "queue.Queue[HistoryEntry]" = queue.Queue(maxsize=2000)
        self.history: list[HistoryEntry] = []
        self.source: FrameSource | None = None
        self.window: winapi.WindowInfo | None = None
        self.runner: ActivityRunner | None = None
        self.engine: CombatEngine | None = None
        self.assist_engine: CombatEngine | None = None
        self.input_backend = input_backend
        self.simulated = False
        self._sim_store: ShotStore | None = None
        self._lock = threading.RLock()
        self.hotkey = None
        self.hotkey_ok: bool | None = None  # None = não pedida (testes/simulação)
        if start_hotkey:
            self.hotkey = HotkeyListener(self.config.get("safety.emergency_hotkey", "<f12>"), self.emergency_stop)
            self.hotkey_ok = self.hotkey.start()
            if not self.hotkey_ok:
                self.startup_notes.append(f"tecla de emergência indisponível ({self.hotkey.error}); "
                                          "o modo automático no jogo fica bloqueado")
        for note in self.startup_notes:
            self.push_event("aviso", note)

    # ------------------------------------------------------------- eventos
    def push_event(self, kind, message, **data):
        e = HistoryEntry(time.time(), kind, message, data)
        with self._lock:
            self.history.append(e)
            del self.history[:-500]
        try:
            self.events.put_nowait(e)
        except queue.Full:
            pass

    _push = push_event  # nome antigo, mantido para chamadas internas

    # -------------------------------------------------------------- janela
    def find_windows(self, all_windows=False) -> list[winapi.WindowInfo]:
        if all_windows:
            return winapi.list_windows()
        return winapi.find_game_windows(self.config.get("window.title_keywords", []))

    def inventory(self, ranked: bool = True) -> list[winapi.WindowInfo]:
        """Janelas principais e internas visíveis.

        ``ranked=False`` mantém a ordem do Windows (da frente para trás), usada para saber
        qual janela está sob um ponto da tela.
        """
        out = []
        for w in winapi.list_windows(min_size=150):
            out.append(w)
            out += winapi.child_windows(w.hwnd, min_size=150)
        return rank_candidates(out, self.config.get("window.title_keywords", [])) if ranked else out

    @property
    def profile(self) -> GameWindowProfile:
        return GameWindowProfile.from_config(self.config)

    def detect_game(self, baseline: set[int] | None = None, rejected: set[int] | None = None) -> Detection:
        """Procura o jogo e o launcher (janelas, processos e o perfil confirmado antes)."""
        return detect(self.inventory(), winapi.process_parents(), winapi.own_pid(),
                      self.config.get("window.title_keywords", []), self.profile, baseline, rejected)

    def auto_connect(self, baseline: set[int] | None = None, rejected: set[int] | None = None) -> Detection:
        """Detecta o jogo e conecta sozinho quando a evidência é forte.

        Não troca de janela no meio de uma rotina. Com evidência fraca (o usuário precisa
        confirmar), só informa; a confirmação chega por ``confirm_game``.
        """
        found = self.detect_game(baseline, rejected)
        running = bool(self.runner and self.runner.alive)
        if found.state == GAME and found.confident and not running:
            if self.window is None or self.window.hwnd != found.game.hwnd:
                self.select_window(found.game)
                self._remember(found.game, found.launcher)
        elif self.window is not None and not running and winapi.IS_WINDOWS \
                and winapi.window_info(self.window.hwnd) is None:
            self._drop_window("a janela do jogo foi fechada")
        return found

    def _remember(self, game: winapi.WindowInfo, launcher: winapi.WindowInfo | None):
        """Guarda o programa e a classe do jogo (e do launcher) para reencontrá-los sozinho depois."""
        prof = self.profile
        rule = WindowRule.of(game)
        lrule = WindowRule.of(launcher) if launcher else prof.launcher
        new = GameWindowProfile(rule, lrule if lrule != rule else None)
        if new != prof:
            self.config.set("window.profile", new.to_dict())
            try:
                self.config.save()
            except OSError as exc:
                log.warning("não foi possível gravar o perfil da janela: %s", exc)

    def confirm_game(self, game: winapi.WindowInfo, launcher: winapi.WindowInfo | None = None) -> str | None:
        """O usuário confirmou (ou escolheu) a janela do jogo. Devolve um erro legível ou None."""
        err = validate_choice(game, launcher)
        if err:
            return err
        if self.runner and self.runner.alive:
            return "pare a rotina antes de trocar de janela"
        self.select_window(game)
        self._remember(game, launcher)
        return None

    def mark_launcher(self, launcher: winapi.WindowInfo):
        """O usuário disse que a janela encontrada é o launcher (o jogo ainda não abriu)."""
        top = launcher
        if launcher.parent:
            top = winapi.window_info(winapi.root_of(launcher.hwnd)) or launcher
        prof = self.profile
        rule = WindowRule.of(top)
        game = prof.game if prof.game and prof.game != rule else None
        self.config.set("window.profile", GameWindowProfile(game, rule).to_dict())
        try:
            self.config.save()
        except OSError as exc:
            log.warning("não foi possível gravar o perfil da janela: %s", exc)
        if self.window is not None and self.window.hwnd in (launcher.hwnd, top.hwnd):
            self._drop_window("a janela escolhida era o launcher")

    def _drop_window(self, why: str):
        old, self.source, self.window = self.source, None, None
        if old is not None:
            old.close()
        self.push_event("aviso", f"janela do jogo desconectada: {why}")

    def select_window(self, info: winapi.WindowInfo):
        if self.runner and self.runner.alive:
            raise RuntimeError("pare a rotina antes de trocar de janela")
        old = self.source
        self.window = info
        self.source = WindowCapture(info.hwnd)
        if old is not None:
            old.close()
        self.push_event("etapa", f"janela selecionada: {info.title} ({info.width}x{info.height})")

    def set_source(self, source: FrameSource):
        """Fonte alternativa (imagens salvas) para diagnóstico offline."""
        old, self.source = self.source, source
        if old is not None and old is not source:
            old.close()

    def grab(self):
        return self.source.grab() if self.source else None

    def analyze(self, frame=None) -> tuple[object, Snapshot | None]:
        frame = self.grab() if frame is None else frame
        if frame is None:
            return None, None
        return frame, self.perception.analyze(frame)

    def release_thread(self):
        """Threads de trabalho chamam ao terminar: libera a captura aberta por elas."""
        if self.source is not None:
            self.source.release_thread()

    def save_capture(self, frame, label="captura") -> Path:
        path = save_image(self.paths.captures / f"{label}_{time.strftime('%Y%m%d_%H%M%S')}_"
                          f"{int(time.time() * 1000) % 1000:03d}.png", frame)
        # as capturas podem ter nome do personagem e chat: guarda só as mais recentes
        files = sorted(self.paths.captures.glob("*.png"), key=lambda p: p.stat().st_mtime)
        for old in files[:-MAX_CAPTURES]:
            try:
                old.unlink()
            except OSError:
                pass
        return path

    # ----------------------------------------------------------- atividades
    def activities(self) -> tuple[list[ActivityDef], list[str]]:
        return load_activities(self.paths.instances)

    def _taken_names(self) -> set[str]:
        names = {p.stem for p in self.paths.instances.glob("*.json")}
        names |= {p.name for p in self.paths.templates.iterdir() if p.is_dir()}
        return names

    def create_activity(self, option_template: str, name: str, kind: str, category: str) -> ActivityDef:
        key = unique_slug(slug(f"{kind}_{name}"), {p.stem for p in self.paths.instances.glob("*.json")})
        prof = match_profile(name, self.profiles) if kind == "instancia" else None
        prof = prof if prof is not None and prof.runnable else None
        d = activity_from_option(option_template, name, kind, category, key=key,
                                 strategy=prof.key if prof else None)
        d.save(self.paths.instances)
        self.push_event("etapa", f"atividade criada: {name} ({kind}, {category})")
        if prof is not None:
            self.push_event("etapa", f"estratégia {prof.name} associada a {name} pelo nome; troque em "
                            "Calibração > Menu se não for esta instância")
        return d

    def strategies(self) -> list[InstanceProfile]:
        """Perfis com estratégia própria (os de pesquisa não jogam sozinhos)."""
        return [p for p in self.profiles.values() if p.runnable]

    def profile_for(self, d: ActivityDef) -> InstanceProfile | None:
        p = self.profiles.get(d.strategy) if d.strategy else None
        return p if p is not None and p.runnable else None

    def set_strategy(self, d: ActivityDef, key: str | None):
        if key is not None and (key not in self.profiles or not self.profiles[key].runnable):
            raise ValueError(f"estratégia desconhecida: {key}")
        d.strategy = key
        if d.path is not None:
            d.save(d.path.parent)
        label = self.profiles[key].name if key else "genérica (inimigo selecionado)"
        self.push_event("etapa", f"{d.name}: estratégia {label}")

    def create_activity_from_image(self, img, name: str, kind: str, category: str) -> ActivityDef:
        """Guarda a imagem da opção como modelo e cria a atividade, sem misturar com nomes existentes."""
        if not name.strip():
            raise ValueError("Dê um nome para a atividade.")
        tpl = unique_slug(slug(f"{kind}_{name}"), self._taken_names())
        self.templates.add(tpl, img)
        return self.create_activity(tpl, name.strip(), kind, category)

    def delete_activity(self, d: ActivityDef):
        if d.path and d.path.exists():
            d.path.unlink()

    def readiness(self, d: ActivityDef):
        """O que falta calibrar para ``d`` rodar sozinha no jogo real (lista vazia = nada)."""
        from .readiness import check
        return check(d, self.templates.has, self.config, self.perception.angle_reader.trained,
                     self.perception.wind_reader.trained, profile=self.profile_for(d))

    # ------------------------------------------------------------ armas
    def weapon_by_name(self, name: str) -> Weapon:
        w = self.config.get(f"weapons.{name}", {}) or {}
        return Weapon(name=name, **{k: float(v) for k, v in w.items()
                                    if k in ("force_scale", "drag_scale", "angle_offset", "blast_radius")})

    # ----------------------------------------------------------- execução
    def _input(self, cancel_check=None) -> InputController:
        fg = None
        if self.config.get("safety.require_foreground", True) and self.source is not None:
            fg = self.source.is_foreground
        keys_ok = getattr(self.source, "keyboard_focused", None) if fg else None
        return InputController(self.kill, self.input_backend, foreground_check=fg, cancel_check=cancel_check,
                               key_focus_check=keys_ok,
                               key_delay_s=float(self.config.get("automation.key_delay_ms", 45)) / 1000)

    def _check_keys(self) -> str | None:
        keys = self.config.get("automation.keys", {}) or {}
        for name in ("angle_up", "angle_down", "fire", "face_left", "face_right", "pass_turn"):
            k = keys.get(name)
            if k and not winapi.key_supported(k):
                return f"a tecla '{k}' configurada não é suportada; corrija em Configurações"
        return None

    def build_runner(self, d: ActivityDef, runs: int, simulated=False, faults: dict | None = None
                     ) -> tuple[ActivityRunner, CombatEngine]:
        limits = RunLimits.from_config(self.config, runs)
        holder: dict = {}
        profile = self.profile_for(d)
        planner = None

        def cancel():
            r = holder.get("runner")
            return r.cancel_reason() if r else None

        if simulated:
            from .simulation import (DEMO_SCENARIOS, InstanceWorld, SimulatedClient, SimulatedShooter, SimulatedView,
                                     SimulatedWorld, demo_option)
            if profile is not None and profile.key in DEMO_SCENARIOS:
                planner = StrategyPlanner(profile, has_template=lambda name: True, on_event=self._strategy_event)
                world = InstanceWorld(self.params, profile, planner)
            else:
                world = SimulatedWorld(self.params)
            client = SimulatedClient(world, option=demo_option(d), faults=faults)
            if self._sim_store is None:
                self._sim_store = ShotStore(self.paths.root / "simulacao.sqlite3")
            sim_cal = Calibrator(self._sim_store, self.params, sources=("simulado",))
            cfg = Config(data={**self.config.data,
                               "automation": {**self.config.data["automation"], "server_rules_confirmed": True,
                                              "min_seconds_between_shots": 0, "post_shot_wait_s": 0.3},
                               "thresholds": {**self.config.data["thresholds"], "auto_min_hit_probability": 0.0}})
            engine = CombatEngine(SimulatedView(world), SimulatedShooter(world),
                                  Aimer(self.kb, self.params, sim_cal), sim_cal, TargetTracker(), self.kill, cfg,
                                  on_event=self._combat_event, source="simulado", cancel_check=cancel)
            engine.set_mode(Mode.AUTO)
            reader, actor, run_cfg = client, client, cfg
        else:
            if self.source is None:
                raise RuntimeError("selecione a janela do jogo primeiro")
            bad = self._check_keys()
            if bad:
                raise RuntimeError(bad)
            inp = self._input(cancel)
            if profile is not None:
                planner = StrategyPlanner(profile, has_template=self.templates.has, on_event=self._strategy_event,
                                          cluster_radius=float(self.config.get("strategy.cluster_radius", 1.0)))
            self.perception.profile = profile  # papéis e estados desta instância (ou nenhum)
            view = VisionBattleView(self.source, self.perception, self.config, planner=planner)
            engine = CombatEngine(view, KeyboardShooter(inp, view, self.config), self.aimer, self.calibrator,
                                  self._tracker(), self.kill, self.config, on_event=self._combat_event,
                                  cancel_check=cancel)
            ok, why = engine.set_mode(Mode.AUTO)
            if not ok:
                raise RuntimeError(why)
            reader = VisionScreenReader(self.source, self.perception,
                                        require_foreground=bool(self.config.get("safety.require_foreground", True)))
            actor = GameActor(inp, self.source, self.templates, self.config)
            run_cfg = self.config
        engine.planner = planner

        def battle_start():
            engine.reset_battle()
            if planner is not None:
                planner.on_battle_start()
        runner = ActivityRunner(d, reader, actor, engine.step, self.kill, run_cfg, limits,
                                on_event=self._run_event,
                                state_threshold=float(self.config.get("thresholds.template", 0.8)),
                                on_battle_start=battle_start,
                                on_activity_start=planner.reset_run if planner is not None else None,
                                on_failure_frame=lambda f, why: self.push_event(
                                    "aviso", f"tela salva para diagnóstico: {self.save_capture(f, 'falha').name}"))
        holder["runner"] = runner
        return runner, engine

    def _tracker(self) -> TargetTracker:
        g = self.config.get
        return TargetTracker(max_move_per_turn=float(g("tracking.max_move_per_turn", 1.5)),
                             max_uncertainty=float(g("tracking.max_uncertainty", 2.5)),
                             area_attack_radius=float(g("tracking.area_attack_radius", 1.0)))

    def _strategy_event(self, kind, message):
        self.push_event("etapa" if kind == "etapa" else "aviso", message)

    def _run_event(self, e):
        self.push_event(e.kind, e.message, **e.data)

    def _combat_event(self, e):
        self.push_event("combate" if e.kind != "aviso" else "aviso", e.message,
                        **{k: v for k, v in e.data.items() if k in ("shot_id", "result", "decisao")})

    def start(self, d: ActivityDef, runs: int, simulated=False, faults: dict | None = None) -> tuple[bool, str]:
        if self.runner and self.runner.alive:
            return False, "já existe uma rotina em execução"
        # clicar em Iniciar recomeça depois de uma emergência antiga; uma emergência apertada DURANTE o
        # início (procura da janela, espera do foco) cancela este início
        if self.kill.triggered:
            self.kill.reset()
        ok, why = self._start(d, runs, simulated, faults)
        if not ok and not (self.runner and self.runner.alive):
            self.perception.profile = None  # o perfil da instância só vale durante a rotina dela
        return ok, why

    def _start(self, d, runs, simulated, faults) -> tuple[bool, str]:
        if not simulated:
            found = self.auto_connect()
            if self.source is None:
                if found.state == LAUNCHER_ONLY:
                    return False, ("o launcher está aberto, mas o jogo ainda não iniciou: entre no jogo pelo "
                                   "launcher e clique em Iniciar")
                if found.state == GAME:
                    return False, "confirme a janela do jogo: clique em Detectar jogo"
                return False, ("a janela do jogo não foi encontrada: abra o DDClássico pelo launcher e clique em "
                               "Detectar jogo")
        if not simulated and self.hotkey is not None and not self.hotkey_ok:
            return False, ("a tecla de emergência não está funcionando; sem ela o modo automático no jogo fica "
                           "bloqueado (veja o Registro técnico)")
        try:
            runner, engine = self.build_runner(d, runs, simulated, faults)
        except RuntimeError as exc:
            return False, str(exc)
        ok, why = runner.check_allowed()
        if not ok:
            return False, why
        if not simulated:
            from .readiness import summary
            missing = summary(self.readiness(d))
            if missing:
                return False, f"falta calibrar para jogar sozinho: {missing}"
        if not simulated and self.window is not None:
            winapi.set_foreground(self.window.hwnd)
            deadline = time.monotonic() + 2.0
            while not self.source.is_foreground() and time.monotonic() < deadline:
                time.sleep(0.1)
            if winapi.IS_WINDOWS and not self.source.is_foreground():
                return False, "não foi possível trazer a janela do jogo para a frente; clique nela e tente de novo"
        if self.kill.triggered:
            return False, f"parada de emergência acionada durante o início ({self.kill.reason})"
        self.stop_assist()
        self.runner, self.engine, self.simulated = runner, engine, simulated
        runner.start()
        return True, ""

    def pause(self):
        if self.runner:
            self.runner.pause()

    def resume(self):
        if self.runner:
            if not self.simulated and self.profile.configured and isinstance(self.source, WindowCapture) \
                    and winapi.window_info(self.source.hwnd) is None:
                found = self.detect_game()  # o jogo foi reaberto pelo launcher: janela nova
                if found.state == GAME and found.confident:
                    self.source.rebind(found.game.hwnd)
                    self.window = found.game
                    self.push_event("etapa", "jogo reaberto: reconectado à janela nova")
            self.runner.resume()

    def stop(self, wait_s=6.0):
        """Para a rotina; as ações em andamento são interrompidas entre uma tecla e outra."""
        if self.runner:
            self.runner.request_stop("parado pelo usuário")
            self.runner.pause_event.clear()
            self.runner.join(wait_s)
            if self.runner.alive:  # algo bloqueou: força parada imediata
                self.kill.trigger("parada forçada")
                self.runner.join(wait_s)

    def emergency_stop(self):
        self.kill.trigger("tecla de emergência")
        self.push_event("erro", "PARADA DE EMERGÊNCIA acionada")

    @property
    def status(self) -> RunStatus:
        return self.runner.status if self.runner else RunStatus.IDLE

    # ------------------------------------------------------ teste de controles
    def test_controls(self) -> str:
        """Lê o ângulo, aperta 'aumentar' uma vez, lê de novo e desfaz. Não atira."""
        if self.source is None:
            raise RuntimeError("selecione a janela do jogo primeiro")
        if (self.runner and self.runner.alive) or self.assist_alive:
            raise RuntimeError("pare a rotina e a mira assistida antes de testar os controles")
        if not self.config.get("automation.server_rules_confirmed", False):
            raise RuntimeError("autorize o modo automático em Configurações antes de enviar teclas")
        if self.kill.triggered:
            raise RuntimeError("a parada de emergência está acionada; clique em Iniciar ou reabra o programa")
        bad = self._check_keys()
        if bad:
            raise RuntimeError(bad)
        try:
            if self.window is not None:
                winapi.set_foreground(self.window.hwnd)
                self.kill.sleep(0.5)
            inp = self._input()
            view = VisionBattleView(self.source, self.perception, self.config)
            sh = KeyboardShooter(inp, view, self.config)
            keys = self.config.get("automation.keys", {})
            before = sh._read_angle()
            inp.tap(keys.get("angle_up", "up"))
            self.kill.sleep(0.4)
            after = sh._read_angle()
            inp.tap(keys.get("angle_down", "down"))
        finally:
            self.release_thread()
        if before is None or after is None:
            return f"ângulo lido antes={before}, depois={after}: treine os dígitos do ângulo e confira a região"
        if after == before + 1:
            return f"OK: o ângulo foi de {before:.0f} para {after:.0f} e voltou"
        return (f"o ângulo foi de {before:.0f} para {after:.0f} (esperado {before + 1:.0f}); "
                "confira as teclas e se é o seu turno")

    # ------------------------------------------------------ mira assistida
    def start_assist(self):
        """Só lê a tela e sugere ângulo/força; não envia nenhuma tecla."""
        if self.source is None:
            raise RuntimeError("selecione a janela do jogo primeiro")
        self.stop_assist()
        if not (self.runner and self.runner.alive):
            self.perception.profile = None  # a mira assistida sugere para o inimigo escolhido, sem estratégia
        view = VisionBattleView(self.source, self.perception, self.config)
        self.assist_engine = CombatEngine(view, None, self.aimer, self.calibrator, self._tracker(), self.kill,
                                          self.config, on_event=self._combat_event)
        self.assist_engine.on_thread_exit = self.release_thread
        if not (self.runner and self.runner.alive):
            self.engine = self.assist_engine
        self.assist_engine.start(interval_s=0.3)

    @property
    def assist_alive(self) -> bool:
        eng = self.assist_engine
        return bool(eng and eng._thread and eng._thread.is_alive())

    def stop_assist(self):
        eng = self.assist_engine
        if eng is not None:
            eng.stop()
            eng.join(2.0)
            self.assist_engine = None

    def apply_params(self, params: PhysicsParams, info: dict):
        params.save(self.paths.knowledge / "model_params.json",
                    {"origem": "reajuste com disparos observados", "tipo": "observado", "reajuste": info})
        self.params = params
        self.aimer.params = params
        self.calibrator.params = params
        self.calibrator.rebuild()
        self.push_event("etapa", f"modelo físico reajustado com {info.get('n')} disparos")

    # ---------------------------------------------------------- mira manual
    def recommend(self, distance, wind, dy=0.0):
        g = self.config.get
        weapon = self.weapon_by_name(g("aim.weapon", "padrao"))
        ctx = ShotContext(distance=float(distance), wind=float(wind), dy=float(dy),
                          target_width=float(g("aim.target_width", 0.35)), weapon=replace(weapon))
        return self.aimer.recommend(ctx)

    def close(self):
        try:
            self.stop_assist()
            self.stop(1.0)
        finally:
            if self.hotkey:
                self.hotkey.stop()
            if self.source:
                self.source.close()
            self.store.close()
            if self._sim_store is not None:
                self._sim_store.close()
                self._sim_store = None
