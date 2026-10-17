# -*- mode: python ; coding: utf-8 -*-
# Gera dist/JonFlow/JonFlow.exe (pasta portátil, sem console).
from pathlib import Path

ROOT = Path(SPECPATH).parent

datas = [
    (str(ROOT / "data" / "knowledge"), "data/knowledge"),
    (str(ROOT / "data" / "instances"), "data/instances"),
    (str(ROOT / "data" / "templates"), "data/templates"),
    (str(ROOT / "config" / "default_config.json"), "config"),
    (str(ROOT / "assets" / "jonflow-icon.png"), "assets"),
]

a = Analysis(
    [str(ROOT / "packaging" / "run_ddbot.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=["pynput.keyboard._win32", "pynput.mouse._win32", "PIL._tkinter_finder"],
    excludes=["matplotlib", "scipy", "pandas", "pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JonFlow",
    console=False,
    upx=False,
    version=str(ROOT / "packaging" / "version_info.txt"),
    icon=str(ROOT / "assets" / "jonflow.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="JonFlow")
