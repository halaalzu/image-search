# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for OpenMATB (Modified for TMS study)
#
# Build with:   pyinstaller openmatb.spec --clean
# Output:       dist\openmatb\openmatb.exe  (+ all support files)
#
# The entire dist\openmatb\ folder can be zipped and shared.
# The recipient just unzips and double-clicks openmatb.exe — no Python needed.
# ===========================================================================

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# ---------------------------------------------------------------------------
# Collect pyglet fully (it loads media drivers, image codecs, etc. at runtime
# via string-based imports that static analysis cannot detect).
# ---------------------------------------------------------------------------
pyglet_datas, pyglet_binaries, pyglet_hiddenimports = collect_all('pyglet')

# rstr is used for callsign regex generation and has sub-modules.
rstr_datas, rstr_binaries, rstr_hiddenimports = collect_all('rstr')

# pylsl may ship a native library (liblsl64.dll on Windows) — collect it.
try:
    pylsl_datas, pylsl_binaries, pylsl_hiddenimports = collect_all('pylsl')
except Exception:
    pylsl_datas, pylsl_binaries, pylsl_hiddenimports = [], [], []

# ---------------------------------------------------------------------------
# Hidden imports — modules loaded dynamically that PyInstaller won't find
# by tracing imports statically.
# ---------------------------------------------------------------------------
hidden_imports = [
    # ----- All OpenMATB plugins -----
    # (plugins/__init__.py already imports them, but listing here is belt-and-braces)
    'plugins',
    'plugins.abstract',
    'plugins.sysmon',
    'plugins.communications',
    'plugins.track',
    'plugins.resman',
    'plugins.scheduling',
    'plugins.healthbar',
    'plugins.healthbar_bus',
    'plugins.instructions',
    'plugins.genericscales',
    'plugins.eyetracker',
    'plugins.flash',
    'plugins.chrono',
    'plugins.performance',
    'plugins.parallelport',
    'plugins.labstreaminglayer',

    # ----- All core modules -----
    'core',
    'core.clock',
    'core.constants',
    'core.container',
    'core.error',
    'core.logger',
    'core.logreader',
    'core.modaldialog',
    'core.pseudorandom',
    'core.replayscheduler',
    'core.scenario',
    'core.scheduler',
    'core.utils',
    'core.window',

    # ----- All core widgets -----
    'core.widgets',
    'core.widgets.abstractwidget',
    'core.widgets.button',
    'core.widgets.frame',
    'core.widgets.healthbar',
    'core.widgets.light',
    'core.widgets.performancescale',
    'core.widgets.pump',
    'core.widgets.pumpflow',
    'core.widgets.radio',
    'core.widgets.reticle',
    'core.widgets.scale',
    'core.widgets.schedule',
    'core.widgets.simplehtml',
    'core.widgets.simpletext',
    'core.widgets.slider',
    'core.widgets.tank',
    'core.widgets.timeline',

    # ----- pyglet media drivers (loaded by string at runtime) -----
    'pyglet.media.drivers',
    'pyglet.media.drivers.directsound',
    'pyglet.media.drivers.openal',
    'pyglet.media.drivers.pulse',
    'pyglet.media.drivers.silent',
    'pyglet.libs',
    'pyglet.libs.win32',

    # ----- Standard library modules used dynamically -----
    'winsound',       # beep alerts (Windows only — silently absent elsewhere)
    'gettext',
    'threading',
    'wave',
    'struct',
    'io',
    'math',

    # ----- Third-party -----
    'pyparallel',
] + pyglet_hiddenimports + rstr_hiddenimports + pylsl_hiddenimports

# ---------------------------------------------------------------------------
# Data files — everything non-.py that the app reads at runtime.
#
# Tuple format: (source_path, dest_folder_inside_bundle)
# After the build, all datas land next to openmatb.exe, so Path('.')
# in the app code resolves correctly (see runtime_hook_cwd.py).
# ---------------------------------------------------------------------------
datas = [
    # Core resource tree
    ('includes',   'includes'),   # sounds, scenarios, images, instructions, questionnaires
    ('locales',    'locales'),    # gettext translation files (.mo / .po)

    # Root-level config, version tag, and native DLL
    ('config.ini',    '.'),       # application settings (screen_index, language, etc.)
    ('VERSION',       '.'),       # version string read by scheduler.py at startup
    ('inpout32.dll',  '.'),       # parallel-port DLL (Windows, used by parallelport plugin)

    # Locale pot/README that live inside locales/ — already captured above,
    # but listing separately makes intent clear.
] + pyglet_datas + rstr_datas + pylsl_datas

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=pyglet_binaries + rstr_binaries + pylsl_binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    # runtime_hook runs BEFORE any app code; it sets the working directory
    # to the exe's folder so all Path('.') lookups resolve correctly.
    runtime_hooks=['runtime_hook_cwd.py'],
    excludes=[
        # Heavy packages that OpenMATB doesn't use — shaves ~20 MB off the bundle
        'matplotlib', 'numpy', 'scipy', 'pandas', 'PIL', 'cv2',
        'tkinter', 'wx', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
        'IPython', 'jupyter', 'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ---------------------------------------------------------------------------
# EXE
#   console=True  → keeps a small terminal window open alongside the MATB
#                   window.  Useful in a lab to see tracebacks if something
#                   crashes.  Change to False to hide it completely.
# ---------------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # binaries go into COLLECT, not embedded in exe
    name='openmatb',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,            # ← set False to hide the terminal window
)

# ---------------------------------------------------------------------------
# COLLECT — produces the dist\openmatb\ folder
#
# contents_directory='.' puts all support files (DLLs, data, .pyz) directly
# next to openmatb.exe rather than in an _internal/ sub-folder.
# This is how PyInstaller 5.x behaved and is necessary here because the app
# uses Path('.') everywhere to locate config.ini, includes/, locales/, etc.
# ---------------------------------------------------------------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='openmatb',
    contents_directory='.',   # ← keep all files flat next to the .exe
)
