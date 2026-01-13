"""Git operations for Hangar TUI."""

import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from ..models import GitStatus


@dataclass
class GitInfo:
    status: GitStatus
    branch: Optional[str] = None
    last_commit_date: Optional[datetime] = None
    last_commit_message: Optional[str] = None
    remote_url: Optional[str] = None
    uncommitted_count: int = 0


def run_git(path: Path, *args: str) -> Optional[str]:
    """Run a git command and return output, or None on error."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_git_info(path: Path) -> GitInfo:
    """Get git information for a project directory."""
    # Check if it's a git repo
    if not (path / ".git").is_dir():
        return GitInfo(status=GitStatus.NO_GIT)

    # Get branch name
    branch = run_git(path, "rev-parse", "--abbrev-ref", "HEAD")

    # Get last commit info
    last_commit_date = None
    last_commit_message = None
    commit_info = run_git(path, "log", "-1", "--format=%ci|%s")
    if commit_info and "|" in commit_info:
        date_str, message = commit_info.split("|", 1)
        try:
            last_commit_date = datetime.fromisoformat(date_str.strip())
        except ValueError:
            pass
        last_commit_message = message.strip()

    # Get remote URL
    remote_url = run_git(path, "remote", "get-url", "origin")

    # Check for uncommitted changes
    status_output = run_git(path, "status", "--porcelain")
    uncommitted_count = len(status_output.splitlines()) if status_output else 0
    git_status = GitStatus.DIRTY if uncommitted_count > 0 else GitStatus.CLEAN

    return GitInfo(
        status=git_status,
        branch=branch,
        last_commit_date=last_commit_date,
        last_commit_message=last_commit_message,
        remote_url=remote_url,
        uncommitted_count=uncommitted_count,
    )


@dataclass
class Commit:
    hash: str
    message: str
    date: datetime
    author: str


def get_recent_commits(path: Path, count: int = 5) -> list[Commit]:
    """Get recent commits for a project."""
    output = run_git(path, "log", f"-{count}", "--format=%H|%s|%ci|%an")
    if not output:
        return []

    commits = []
    for line in output.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            try:
                date = datetime.fromisoformat(parts[2].strip())
            except ValueError:
                date = datetime.now()
            commits.append(Commit(
                hash=parts[0][:7],
                message=parts[1],
                date=date,
                author=parts[3],
            ))
    return commits


def get_open_prs(path: Path) -> list[dict]:
    """Get open PRs for a project using gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--json", "number,title,headRefName,url"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            import json
            return json.loads(result.stdout)
        return []
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return []
