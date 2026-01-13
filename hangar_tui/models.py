"""Data models for Hangar TUI."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
from datetime import datetime


class TodoStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class GitStatus(str, Enum):
    CLEAN = "clean"
    DIRTY = "dirty"
    NO_GIT = "no_git"


@dataclass
class Todo:
    content: str
    status: TodoStatus = TodoStatus.PENDING

    def cycle_status(self) -> None:
        """Cycle through status: pending -> in_progress -> completed -> pending."""
        cycle = [TodoStatus.PENDING, TodoStatus.IN_PROGRESS, TodoStatus.COMPLETED]
        current_idx = cycle.index(self.status)
        self.status = cycle[(current_idx + 1) % len(cycle)]

    def to_dict(self) -> dict:
        return {"content": self.content, "status": self.status.value}

    @classmethod
    def from_dict(cls, data: dict) -> "Todo":
        return cls(
            content=data["content"],
            status=TodoStatus(data.get("status", "pending")),
        )


@dataclass
class Project:
    name: str
    path: Path
    git_status: GitStatus = GitStatus.NO_GIT
    branch: Optional[str] = None
    last_commit_date: Optional[datetime] = None
    last_commit_message: Optional[str] = None
    todo_count: int = 0
    remote_url: Optional[str] = None
    pr_count: int = 0

    @property
    def status_icon(self) -> str:
        """Return an icon representing git status."""
        icons = {
            GitStatus.CLEAN: "✓",
            GitStatus.DIRTY: "●",
            GitStatus.NO_GIT: "○",
        }
        return icons[self.git_status]

    @property
    def status_color(self) -> str:
        """Return a color for the git status."""
        colors = {
            GitStatus.CLEAN: "green",
            GitStatus.DIRTY: "yellow",
            GitStatus.NO_GIT: "dim",
        }
        return colors[self.git_status]
