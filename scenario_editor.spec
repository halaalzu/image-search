# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

block_cipher = None

streamlit_datas, streamlit_binaries, streamlit_hidden = collect_all("streamlit")
plotly_datas, plotly_binaries, plotly_hidden = collect_all("plotly")
pandas_datas, pandas_binaries, pandas_hidden = collect_all("pandas")

hidden_imports = streamlit_hidden + plotly_hidden + pandas_hidden

datas = [
    ("scenario_editor", "scenario_editor"),
    ("includes", "includes"),
    ("config.ini", "."),
] + streamlit_datas + plotly_datas + pandas_datas

a = Analysis(
    ["scenario_editor_launcher.py"],
    pathex=["."],
    binaries=streamlit_binaries + plotly_binaries + pandas_binaries,
    datas=datas,
    hiddenimports=hidden_imports,
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
    name="scenario_editor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="scenario_editor",
    contents_directory=".",
)
