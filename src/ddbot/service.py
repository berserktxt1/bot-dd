"""Camada de aplicação: monta e liga todos os componentes. A GUI só conversa com ela.

Separação:
- percepção: ``capture`` + ``vision`` (o que está na tela, com confiança);
- decisão: ``aiming``, ``tracking``, ``combat`` e ``activities`` (o que fazer);
- execução: ``automation`` (teclado/mouse com travas) ou executores simulados.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__, winapi
from .activities import (ActivityDef, ActivityRunner, RunLimits, RunStatus, activity_from_option,
                         load_activities)
from .aiming import Aimer, ShotContext
from .automation.input import InputBackend, InputController
from .automation.safety import HotkeyListener, KillSwitch
from .calibration import Calibrator, ShotStore
from .capture import FrameSource, WindowCapture, save_image
from .combat import CombatEngine, Mode
from .config import Config
from .game_io import GameActor, KeyboardShooter, VisionBattleView, VisionScreenReader
from .knowledge import KnowledgeBase
from .log import setup_logging
from .paths import Paths
from .physics import PhysicsParams
from .tracking import TargetTracker
from .vision.perception import Perception, Snapshot
from .vision.templates import TemplateLibrary

log = logging.getLogger(__name__)


@dataclass
class HistoryEntry:
    when: float
    kind: str
    message: str
    data: dict = field(default_factory=dict)


class BotService:
    def __init__(self, home: Path | None = None, input_backend: InputBackend | None = None,
                 start_hotkey: bool = True):
        self.paths = Paths(home)
        self.log_file = setup_logging(self.paths.logs)
        log.info("DDClássico Bot %s — dados em %s", __version__, self.paths.root)
        self.config = Config(self.paths.config_file)
        self.kb = KnowledgeBase(self.paths.data_dir)
        self.params = PhysicsParams.load(self.paths.knowledge / "model_params.json")
        self.store = ShotStore(self.paths.db)
        self.calibrator = Calibrator(self.store, self.params)
        self.aimer = Aimer(self.kb, self.params, self.calibrator)
        self.templates = TemplateLibrary(self.paths.templates)
        self.perception = Perception(self.config, self.templates, self.paths.templates)
        self.kill = KillSwitch()
        self.events: "queue.Queue[HistoryEntry]" = queue.Queue(maxsize=2000)
        self.history: list[HistoryEntry] = []
        self.source: FrameSource | None = None
        self.window: winapi.WindowInfo | None = None
        self.runner: ActivityRunner | None = None
        self.engine: CombatEngine | None = None
        self.input_backend = input_backend
        self.simulated = False
        self._lock = threading.RLock()
        self.hotkey = None
        if start_hotkey:
            self.hotkey = HotkeyListener(self.config.get("safety.emergency_hotkey", "<f12>"), self.emergency_stop)
            self.hotkey.start()

    # ------------------------------------------------------------- eventos
    def _push(self, kind, message, **data):
        e = HistoryEntry(time.time(), kind, message, data)
        with self._lock:
            self.history.append(e)
            del self.history[:-500]
        try:
            self.events.put_nowait(e)
        except queue.Full:
            pass

    # -------------------------------------------------------------- janela
    def find_windows(self, all_windows=False) -> list[winapi.WindowInfo]:
        if all_windows:
            return winapi.list_windows()
        return winapi.find_game_windows(self.config.get("window.title_keywords", []))

    def select_window(self, info: winapi.WindowInfo):
        self.window = info
        self.source = WindowCapture(info.hwnd)
        self._push("etapa", f"janela selecionada: {info.title} ({info.width}x{info.height})")

    def set_source(self, source: FrameSource):
        """Fonte alternativa (imagens salvas) para diagnóstico offline."""
        self.source = source

    def grab(self):
        return self.source.grab() if self.source else None

    def analyze(self, frame=None) -> tuple[object, Snapshot | None]:
        frame = self.grab() if frame is None else frame
        if frame is None:
            return None, None
        return frame, self.perception.analyze(frame)

    def save_capture(self, frame, label="captura") -> Path:
        return save_image(self.paths.captures / f"{label}_{time.strftime('%Y%m%d_%H%M%S')}.png", frame)

    # ----------------------------------------------------------- atividades
    def activities(self) -> tuple[list[ActivityDef], list[str]]:
        return load_activities(self.paths.instances)

    def create_activity(self, option_template: str, name: str, kind: str, category: str) -> ActivityDef:
        d = activity_from_option(option_template, name, kind, category)
        d.save(self.paths.instances)
        self._push("etapa", f"atividade criada: {name} ({kind}, {category})")
        return d

    def delete_activity(self, d: ActivityDef):
        if d.path and d.path.exists():
            d.path.unlink()

    def _input(self) -> InputController:
        fg = None
        if self.config.get("safety.require_foreground", True) and self.source is not None:
            fg = self.source.is_foreground
        return InputController(self.kill, self.input_backend, foreground_check=fg,
                               key_delay_s=float(self.config.get("automation.key_delay_ms", 45)) / 1000)

    def build_runner(self, d: ActivityDef, runs: int, simulated=False) -> ActivityRunner:
        limits = RunLimits.from_config(self.config, runs)
        if simulated:
            from .simulation import SimulatedClient, SimulatedShooter, SimulatedView, SimulatedWorld
            world = SimulatedWorld(self.params)
            option = next((a.target for acts in d.flow.values() for a in acts
                           if a.kind == "clicar" and a.target and a.target.startswith(("instancia_", "partida_"))),
                          "instancia_teste")
            client = SimulatedClient(world, option=option)
            sim_store = ShotStore(self.paths.root / "simulacao.sqlite3")
            sim_cal = Calibrator(sim_store, self.params, sources=("simulado",))
            cfg = Config(data={**self.config.data,
                               "automation": {**self.config.data["automation"], "server_rules_confirmed": True,
                                              "min_seconds_between_shots": 0},
                               "thresholds": {**self.config.data["thresholds"], "auto_min_hit_probability": 0.0}})
            engine = CombatEngine(SimulatedView(world), SimulatedShooter(world),
                                  Aimer(self.kb, self.params, sim_cal), sim_cal, TargetTracker(), self.kill, cfg,
                                  on_event=self._combat_event, source="simulado")
            engine.set_mode(Mode.AUTO)
            reader, actor, run_cfg = client, client, cfg
        else:
            if self.source is None:
                raise RuntimeError("selecione a janela do jogo primeiro")
            inp = self._input()
            view = VisionBattleView(self.source, self.perception, self.config)
            engine = CombatEngine(view, KeyboardShooter(inp, view, self.config), self.aimer, self.calibrator,
                                  self._tracker(), self.kill, self.config, on_event=self._combat_event)
            ok, why = engine.set_mode(Mode.AUTO)
            if not ok:
                raise RuntimeError(why)
            reader = VisionScreenReader(self.source, self.perception)
            actor = GameActor(inp, self.source, self.templates, self.config)
            run_cfg = self.config
        runner = ActivityRunner(d, reader, actor, engine.step, self.kill, run_cfg, limits,
                                on_event=self._run_event,
                                state_threshold=float(self.config.get("thresholds.template", 0.8)),
                                on_battle_start=engine.reset_battle)
        self.engine = engine
        self.simulated = simulated
        return runner

    def _tracker(self) -> TargetTracker:
        g = self.config.get
        return TargetTracker(max_move_per_turn=float(g("tracking.max_move_per_turn", 1.5)),
                             max_uncertainty=float(g("tracking.max_uncertainty", 2.5)),
                             area_attack_radius=float(g("tracking.area_attack_radius", 1.0)))

    def _run_event(self, e):
        self._push(e.kind, e.message, **e.data)

    def _combat_event(self, e):
        self._push("combate" if e.kind != "aviso" else "aviso", e.message,
                   **{k: v for k, v in e.data.items() if k in ("shot_id", "result", "decisao")})

    def start(self, d: ActivityDef, runs: int, simulated=False) -> tuple[bool, str]:
        if self.runner and self.runner.alive:
            return False, "já existe uma rotina em execução"
        if self.kill.triggered:
            self.kill.reset()
        try:
            runner = self.build_runner(d, runs, simulated)
        except RuntimeError as exc:
            return False, str(exc)
        ok, why = runner.check_allowed()
        if not ok:
            return False, why
        if not simulated and self.window is not None:
            winapi.set_foreground(self.window.hwnd)
        self.runner = runner
        runner.start()
        return True, ""

    def pause(self):
        if self.runner:
            self.runner.pause()

    def resume(self):
        if self.runner:
            self.runner.resume()

    def stop(self, wait_s=3.0):
        if self.runner:
            self.runner.request_stop("parado pelo usuário")
            self.runner.pause_event.clear()
            self.runner.join(wait_s)
            if self.runner.alive:  # algo bloqueou: força parada imediata
                self.kill.trigger("parada forçada")
                self.runner.join(wait_s)

    def emergency_stop(self):
        self.kill.trigger("tecla de emergência")
        self._push("erro", "PARADA DE EMERGÊNCIA acionada")

    @property
    def status(self) -> RunStatus:
        return self.runner.status if self.runner else RunStatus.IDLE

    # ------------------------------------------------------ mira assistida
    def start_assist(self):
        """Só lê a tela e sugere ângulo/força; não envia nenhuma tecla."""
        if self.source is None:
            raise RuntimeError("selecione a janela do jogo primeiro")
        self.stop_assist()
        view = VisionBattleView(self.source, self.perception, self.config)
        self.assist_engine = CombatEngine(view, None, self.aimer, self.calibrator, self._tracker(), self.kill,
                                          self.config, on_event=self._combat_event)
        if not (self.runner and self.runner.alive):
            self.engine = self.assist_engine
        self.assist_engine.start(interval_s=0.3)

    def stop_assist(self):
        eng = getattr(self, "assist_engine", None)
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
        self._push("etapa", f"modelo físico reajustado com {info.get('n')} disparos")

    # ---------------------------------------------------------- mira manual
    def recommend(self, distance, wind, dy=0.0):
        g = self.config.get
        ctx = ShotContext(distance=float(distance), wind=float(wind), dy=float(dy),
                          target_width=float(g("aim.target_width", 0.35)))
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
