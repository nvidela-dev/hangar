"""GitHub operations for Hangar TUI."""

import subprocess
from pathlib import Path


def open_github(project_path: Path) -> bool:
    """Open the project's GitHub repo in the browser.

    Uses `gh repo view --web` which handles authentication and
    opens the correct URL.

    Returns True if successful.
    """
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--web"],
            cwd=str(project_path),
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
