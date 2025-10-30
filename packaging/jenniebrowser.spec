# -*- mode: python ; coding: utf-8 -*-

import pathlib
import sys

_spec_path_value = globals().get("__file__")
if not _spec_path_value:
    for _arg in reversed(sys.argv):
        if _arg and _arg.endswith(".spec"):
            _spec_path_value = _arg
            break

if not _spec_path_value:
    _spec_path_value = pathlib.Path.cwd()

project_root = pathlib.Path(_spec_path_value).resolve().parents[1]
src_dir = project_root / "src"
resources_dir = src_dir / "jenniebrowser" / "resources"

block_cipher = None

a = Analysis(
    [str(src_dir / "jenniebrowser" / "app.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=[
        (str(resources_dir / "default_filters.txt"), "jenniebrowser/resources"),
        (str(resources_dir / "startpage.html"), "jenniebrowser/resources"),
    ],
    hiddenimports=[
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="jenniebrowser",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="jenniebrowser",
)
