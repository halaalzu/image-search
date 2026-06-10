"""
PyInstaller runtime hook — runs before any app code.

OpenMATB uses Path('.') everywhere to locate data files
(includes/, locales/, config.ini, etc.) and to write output
(sessions/, sync/, logs).

Strategy:
  - With contents_directory='.' in the spec, ALL support files
    (DLLs, data, .pyz archive) land directly next to openmatb.exe.
  - We simply chdir to the exe's folder, which makes every Path('.')
    reference resolve correctly for both reads and writes.
  - Session data therefore lives next to the exe and is NOT wiped
    if you ever rebuild the bundle.
"""
import os
import sys

if getattr(sys, 'frozen', False):
    # sys.executable is the path to openmatb.exe.
    # With contents_directory='.', config.ini / includes/ / locales/ are
    # all in the same folder as the exe.
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))

    # Fallback: if for some reason data files ended up in _internal/,
    # prefer that dir so reads still work (writes still go to exe_dir).
    if not os.path.exists(os.path.join(exe_dir, 'config.ini')):
        internal = getattr(sys, '_MEIPASS', exe_dir)
        if os.path.exists(os.path.join(internal, 'config.ini')):
            exe_dir = internal

    os.chdir(exe_dir)
