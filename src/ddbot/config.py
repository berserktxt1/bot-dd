"""Configuração externa (JSON) com valores padrão mesclados e validados."""
from __future__ import annotations

import copy
import json
import logging
import threading
import time
from pathlib import Path

from .util import atomic_write_text

log = logging.getLogger(__name__)

DEFAULTS: dict = {
    # palavras que dizem ao "Detectar jogo" onde começar a procurar (launcher ou jogo); o resto vem dos
    # processos e do perfil confirmado. "Clássico" sozinho casaria com janelas que nada têm a ver com o jogo.
    "window": {"title_keywords": ["DDTank", "DDClássico", "DDClassico"], "profile": {}},
    "capture": {"fps": 4},
    "ruler": {"units_per_screen": 10, "playfield": [0.0, 0.0, 1.0, 1.0]},
    "regions": {},
    "markers": {
        "self": {"mode": "template", "hsv_low": None, "hsv_high": None},
        "enemy": {"mode": "template", "hsv_low": None, "hsv_high": None},
    },
    "thresholds": {"template": 0.80, "vision_min_confidence": 0.70, "auto_min_hit_probability": 0.30},
    "aim": {"allowed_methods": None, "target_width": 0.35, "sigma_wind": 0.10,
            "sigma_distance": 0.10, "weapon": "padrao"},
    "weapons": {"padrao": {"force_scale": 1.0, "drag_scale": 1.0, "angle_offset": 0.0, "blast_radius": 0.25}},
    "automation": {
        "server_rules_confirmed": False,
        "keys": {"angle_up": "up", "angle_down": "down", "fire": "space", "pass_turn": None,
                 "face_left": "left", "face_right": "right"},
        "power_mode": "timed",
        # medido por terceiros no servidor do jogo (AINBOT, 2026: 3,30 a 3,35 s e 44 a 94 ms até a barra começar);
        # outros servidores tinham 4 s. Confira no seu cliente (Configurações) ou use a leitura da barra
        "power_full_time_s": 3.33,
        "power_start_delay_s": 0.06,
        "power_offset": 0.0,
        "forbidden_templates": [],
        "allowed_paid_templates": [],
        "key_delay_ms": 45,
        "max_angle_presses": 120,
        "min_seconds_between_shots": 3.0,
        "post_shot_wait_s": 4.0,
        "turn_confirm_reads": 2,
        "bad_reads_per_turn": 3,
        "bad_read_seconds": 5.0,
        "battle_over_confirm_reads": 2,
    },
    "safety": {"emergency_hotkey": "<f12>", "require_foreground": True},
    "tracking": {"max_move_per_turn": 1.5, "max_uncertainty": 2.5, "area_attack_radius": 1.0},
    "instances": {"selected": None, "max_attempts": 3, "max_defeats": 2, "max_minutes": 60,
                  "unknown_state_timeout_s": 20, "action_timeout_s": 60,
                  "battle_timeout_s": 900, "runs": 1},
    "ui": {"language": "pt-BR", "minimize_during_run": True},
}

# faixas aceitas (mín, máx) para os valores que o usuário edita
RANGES = {
    "thresholds.template": (0.3, 0.99),
    "thresholds.vision_min_confidence": (0.0, 1.0),
    "thresholds.auto_min_hit_probability": (0.0, 1.0),
    "automation.power_full_time_s": (0.5, 15.0),
    "automation.power_start_delay_s": (0.0, 0.5),
    "automation.power_offset": (-20.0, 20.0),
    "automation.min_seconds_between_shots": (0.0, 60.0),
    "automation.post_shot_wait_s": (0.0, 30.0),
    "instances.max_defeats": (0, 1000),
    "instances.max_minutes": (1, 24 * 60),
    "instances.unknown_state_timeout_s": (3, 600),
    "instances.action_timeout_s": (5, 900),
    "ruler.units_per_screen": (1, 40),
}
LABELS = {
    "thresholds.template": "Semelhança mínima das imagens",
    "thresholds.vision_min_confidence": "Confiança mínima para atirar",
    "automation.power_full_time_s": "Segundos até a força 100",
    "automation.power_start_delay_s": "Espera até a barra começar a encher",
    "automation.power_offset": "Compensação de força",
    "automation.min_seconds_between_shots": "Intervalo entre disparos",
    "instances.max_defeats": "Limite de derrotas",
    "instances.max_minutes": "Tempo máximo",
    "instances.unknown_state_timeout_s": "Pausa por tela desconhecida",
    "instances.action_timeout_s": "Recuperação por tela parada",
    "ruler.units_per_screen": "Partes da régua",
}


def _merge(base: dict, override: dict, path="", problems=None) -> dict:
    """Mescla ``override`` sobre ``base``; valores de tipo incompatível ficam com o padrão."""
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        where = f"{path}{k}"
        cur = out.get(k)
        if isinstance(cur, dict):
            if isinstance(v, dict):
                out[k] = _merge(cur, v, where + ".", problems)
            elif problems is not None:
                problems.append(f"{where}: esperado um grupo de opções")
            continue
        if cur is not None and v is not None and not _compatible(cur, v):
            if problems is not None:
                problems.append(f"{where}: valor {v!r} inválido, usando {cur!r}")
            continue
        out[k] = v
    return out


def _compatible(default, value) -> bool:
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, (int, float)):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(default, str):
        return isinstance(value, str)
    if isinstance(default, list):
        return isinstance(value, list)
    return True


class Config:
    def __init__(self, path: Path | None = None, data: dict | None = None):
        self.path = Path(path) if path else None
        self._lock = threading.RLock()
        self.problems: list[str] = []
        loaded = {}
        if data is not None:
            loaded = data
        elif self.path and self.path.exists():
            loaded = self._read_file()
        self.data = _merge(DEFAULTS, loaded, problems=self.problems)
        for p in self.problems:
            log.warning("configuração: %s", p)

    def _read_file(self) -> dict:
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8-sig"))
            if not isinstance(loaded, dict):
                raise ValueError("o arquivo não contém um objeto JSON")
            return loaded
        except (OSError, ValueError) as exc:
            bad = self.path.with_name(f"config.corrompido-{time.strftime('%Y%m%d-%H%M%S')}.json")
            try:
                self.path.replace(bad)
            except OSError:
                bad = None
            msg = f"config.json inválido ({exc}); usando os valores padrão"
            if bad:
                msg += f"; o original foi guardado como {bad.name}"
            self.problems.append(msg)
            return {}

    def get(self, dotted: str, default=None):
        """Valor da chave; ``default`` se ela não existir ou estiver vazia (None)."""
        with self._lock:
            node = self.data
            for part in dotted.split("."):
                if not isinstance(node, dict) or part not in node:
                    return default
                node = node[part]
            return default if node is None else node

    def set(self, dotted: str, value):
        with self._lock:
            parts = dotted.split(".")
            node = self.data
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value

    @staticmethod
    def validate_values(values: dict) -> list[str]:
        """Problemas legíveis em valores digitados pelo usuário (chave pontuada -> valor)."""
        out = []
        for key, value in values.items():
            if key in RANGES and value is not None:
                lo, hi = RANGES[key]
                if not (lo <= float(value) <= hi):
                    out.append(f"{LABELS.get(key, key)} precisa estar entre {lo:g} e {hi:g}")
            if key == "safety.emergency_hotkey":
                from .automation.safety import HotkeyListener
                err = HotkeyListener.validate(value)
                if err:
                    out.append(err)
            if key.startswith("automation.keys.") and value:
                from .winapi import key_supported
                if not key_supported(value):
                    out.append(f"tecla não suportada: {value}")
        return out

    def save(self):
        if not self.path:
            return
        with self._lock:
            atomic_write_text(self.path, json.dumps(self.data, indent=2, ensure_ascii=False))
