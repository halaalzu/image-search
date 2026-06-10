import os
import sys
from pathlib import Path

from streamlit.web import cli as stcli


def _bundle_root() -> Path:
    # In PyInstaller one-folder mode, executable lives in .../openmatb/scenario_editor/
    # and MATB root is its parent folder (.../openmatb).
    exe_dir = Path(sys.executable).resolve().parent
    return exe_dir.parent


def main() -> int:
    bundle_root = _bundle_root()
    os.environ.setdefault("OPENMATB_ROOT", str(bundle_root))
    app_path = bundle_root / "scenario_editor" / "app.py"

    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    return stcli.main()


if __name__ == "__main__":
    raise SystemExit(main())
