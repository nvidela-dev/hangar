"""Tmux operations for Hangar TUI."""

import subprocess
from pathlib import Path


def open_in_tmux(project_name: str, project_path: Path) -> bool:
    """Open a project in a new tmux window with Claude and nvim split.

    Creates a new tmux window with:
    - Left pane: claude CLI
    - Right pane: nvim

    Returns True if successful.
    """
    try:
        # Create new window with project name, starting in project directory
        subprocess.run(
            [
                "tmux", "new-window",
                "-n", project_name,
                "-c", str(project_path),
            ],
            check=True,
            capture_output=True,
        )

        # Split horizontally (side by side) and run nvim on the right
        subprocess.run(
            [
                "tmux", "split-window",
                "-h",  # Horizontal split (side by side)
                "-c", str(project_path),
                "nvim", ".",
            ],
            check=True,
            capture_output=True,
        )

        # Select the left pane and run claude
        subprocess.run(
            ["tmux", "select-pane", "-L"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["tmux", "send-keys", "claude", "Enter"],
            check=True,
            capture_output=True,
        )

        return True
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        # tmux not installed
        return False
