from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_in_subprocess(tmp_path: Path, code: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    # Ensure the installed package (from the venv's site-packages / editable
    # install) is importable. Fall back to project root if needed.
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    # Strip any MAX_BROWSER_SLOTS / test-marker already in the parent env so
    # the subprocess only sees what .env provides.
    for noisy in ("SHOPPING_MCP_TEST_MARKER",):
        env.pop(noisy, None)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
    )


def test_package_import_loads_dotenv_from_cwd(tmp_path):
    """Importing shopping_mcp must pick up .env from the current directory.

    Before this change, load_dotenv() ran inside asgi.main(), which meant any
    code imported during module load (e.g. browser slot calculation, or
    BrowserConfig at first tool call in certain paths) did not see .env vars.
    """
    (tmp_path / ".env").write_text("SHOPPING_MCP_TEST_MARKER=present\n")

    result = _run_in_subprocess(
        tmp_path,
        "import os, shopping_mcp; "
        "print(os.getenv('SHOPPING_MCP_TEST_MARKER') or '')",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "present"
