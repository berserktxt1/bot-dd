# -*- mode: python ; coding: utf-8 -*-
# Gera dist-unico/JonFlow.exe: um arquivo só, que roda sem a pasta _internal.
# Ao abrir, o PyInstaller extrai os recursos numa pasta temporária (início um pouco mais lento);
# os dados do usuário ficam em 'dados' ao lado do .exe, como na versão em pasta.
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
    a.binaries,
    a.datas,
    [],
    name="JonFlow",
    console=False,
    upx=False,
    runtime_tmpdir=None,
    version=str(ROOT / "packaging" / "version_info.txt"),
    icon=str(ROOT / "assets" / "jonflow.ico"),
)
