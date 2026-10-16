"""Ponto de entrada. Sem argumentos abre a interface gráfica.

Opções (diagnóstico/CI; o usuário final não precisa delas):
  --selftest        verifica recursos, configuração, mira, visão e simulação; código 0 = ok
  --simulate N      roda N batalhas simuladas e mostra a precisão
  --gui-smoke S     abre a interface, exercita os botões em modo simulado e fecha após S segundos
  --home PASTA      usa outra pasta de dados
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path


def _selftest(home: Path | None) -> int:
    import numpy as np

    from . import __version__
    from .activities import activity_from_option
    from .paths import resource_root
    from .service import BotService
    from .simulation import drive, simulated_activity
    from .vision.digits import DigitReader
    from .vision.templates import match_template

    report, ok = {"versao": __version__, "recursos": str(resource_root()), "frozen": bool(getattr(sys, "frozen", False))}, True

    def check(name, fn):
        nonlocal ok
        t = time.time()
        try:
            value = fn()
            report[name] = {"ok": True, "valor": value, "s": round(time.time() - t, 2)}
        except Exception as exc:
            ok = False
            report[name] = {"ok": False, "erro": f"{type(exc).__name__}: {exc}",
                            "trace": traceback.format_exc(limit=4)}

    tmp = None
    if home is None:
        tmp = tempfile.TemporaryDirectory()
        home = Path(tmp.name)
    svc = BotService(home, start_hotkey=False)
    try:
        def resources():
            k = svc.paths.knowledge
            files = sorted(p.name for p in k.glob("*.json"))
            for need in ("angle_tables.json", "mechanics.json", "model_params.json", "sources.json"):
                assert need in files, f"faltando {need}"
            assert svc.paths.config_file.exists(), "config.json não criado"
            return files

        def aim():
            rec = svc.recommend(10, 0)
            assert rec.best is not None
            a65 = next(c for c in rec.candidates if c.method == "a65")
            assert abs(a65.force - 56.0) < 3, a65.force
            return rec.reason

        def vision():
            rng = np.random.default_rng(0)
            img = rng.integers(0, 255, (200, 300, 3), dtype=np.uint8)
            tpl = img[50:90, 100:160].copy()
            score, x, y, _, _ = match_template(img, tpl)
            assert score > 0.95 and (x, y) == (100, 50), (score, x, y)
            import cv2
            reader = DigitReader(home / "glifos_teste.json")

            def text_img(t):
                canvas = np.zeros((30, 90, 3), np.uint8)
                cv2.putText(canvas, t, (5, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                return canvas
            assert reader.learn(text_img("470"), "470")
            value, _ = reader.read(text_img("704"))
            assert value == 704, value
            return "modelos e dígitos ok"

        def simulation():
            d = activity_from_option("instancia_teste", "Teste", "instancia", "pve")
            runner, client, _, _, cleanup = simulated_activity(svc.kb, svc.params, d, runs=1)
            try:
                status = drive(runner)
            finally:
                cleanup()
            assert status.value == "concluido", (status, runner.reason)
            return runner.counters.as_dict()

        def gui_import():
            import importlib
            try:
                importlib.import_module("tkinter")
            except ImportError:
                return "tkinter ausente (esperado só fora do Windows)"
            importlib.import_module("ddbot.gui.main_window")
            return "interface carregável"

        check("recursos", resources)
        check("mira", aim)
        check("visao", vision)
        check("simulacao", simulation)
        check("interface", gui_import)
    finally:
        svc.close()
        import logging
        logging.shutdown()
        if tmp is not None:
            try:
                tmp.cleanup()
            except OSError:
                pass
    report["resultado"] = "OK" if ok else "FALHOU"
    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    _print(text)
    out = os.environ.get("DDBOT_SELFTEST_OUT")
    if out:
        Path(out).write_text(text, encoding="utf-8")
    return 0 if ok else 1


def _print(text):
    # no .exe sem console, stdout pode não existir
    if sys.stdout is not None:
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode("ascii", "replace").decode())


def _simulate(n: int, home: Path | None) -> int:
    from .knowledge import KnowledgeBase
    from .paths import Paths
    from .physics import PhysicsParams
    from .simulation import run_simulation

    paths = Paths(home)
    kb = KnowledgeBase(paths.data_dir)
    params = PhysicsParams.load(paths.knowledge / "model_params.json")
    for calibrate in (False, True):
        r = run_simulation(kb, params, battles=n, calibrate=calibrate)
        _print(json.dumps({"calibracao": calibrate, **r.as_dict()}, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="DDClassicoBot")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--simulate", type=int, default=0)
    ap.add_argument("--gui-smoke", type=float, default=0.0)
    ap.add_argument("--home", type=Path, default=None)
    args = ap.parse_args(argv)
    if args.home:
        os.environ["DDBOT_HOME"] = str(args.home)
    if args.selftest:
        return _selftest(args.home)
    if args.simulate:
        return _simulate(args.simulate, args.home)
    from .gui.main_window import run_gui
    return run_gui(home=args.home, smoke_seconds=args.gui_smoke)


if __name__ == "__main__":
    sys.exit(main())
