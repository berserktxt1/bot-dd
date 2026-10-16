"""Configuração externa (JSON) com valores padrão mesclados."""
from __future__ import annotations

import copy
import json
import threading
from pathlib import Path

DEFAULTS: dict = {
    "window": {"title_keywords": ["DDTank", "DDClássico", "DDClassico", "Clássico", "Classico"]},
    "capture": {"fps": 4},
    "ruler": {"units_per_screen": 10, "playfield": [0.0, 0.0, 1.0, 1.0]},
    "regions": {},
    "markers": {
        "self": {"mode": "template", "hsv_low": None, "hsv_high": None},
        "enemy": {"mode": "template", "hsv_low": None, "hsv_high": None},
        "marker_to_feet": 0.0,
    },
    "thresholds": {"template": 0.80, "vision_min_confidence": 0.70, "auto_min_hit_probability": 0.30},
    "aim": {"allowed_methods": None, "target_width": 0.35, "sigma_wind": 0.10,
            "sigma_distance": 0.10, "weapon": "padrao"},
    "weapons": {"padrao": {"force_scale": 1.0, "drag_scale": 1.0, "angle_offset": 0.0, "blast_radius": 0.25}},
    "automation": {
        "server_rules_confirmed": False,
        "keys": {"angle_up": "up", "angle_down": "down", "fire": "space", "pass_turn": None,
                 "face_left": None, "face_right": None, "close": "esc"},
        "power_mode": "timed",
        "power_full_time_s": 4.0,
        "power_offset": 0.0,
        "forbidden_templates": [],
        "allowed_paid_templates": [],
        "key_delay_ms": 45,
        "max_angle_presses": 120,
        "min_seconds_between_shots": 3.0,
        "post_shot_wait_s": 4.0,
    },
    "safety": {"emergency_hotkey": "<f12>", "require_foreground": True},
    "tracking": {"max_move_per_turn": 1.5, "max_uncertainty": 2.5, "area_attack_radius": 1.0},
    "instances": {"selected": None, "max_attempts": 3, "max_defeats": 2, "max_minutes": 60,
                  "unknown_state_timeout_s": 20, "action_timeout_s": 60,
                  "battle_timeout_s": 900, "runs": 1},
    "ui": {"language": "pt-BR"},
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, path: Path | None = None, data: dict | None = None):
        self.path = Path(path) if path else None
        self._lock = threading.RLock()
        loaded = {}
        if data is not None:
            loaded = data
        elif self.path and self.path.exists():
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        self.data = _merge(DEFAULTS, loaded)

    def get(self, dotted: str, default=None):
        with self._lock:
            node = self.data
            for part in dotted.split("."):
                if not isinstance(node, dict) or part not in node:
                    return default
                node = node[part]
            return node

    def set(self, dotted: str, value):
        with self._lock:
            parts = dotted.split(".")
            node = self.data
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value

    def save(self):
        if not self.path:
            return
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
