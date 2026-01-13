"""Todo persistence for Hangar TUI."""

import json
from pathlib import Path

from ..models import Todo, TodoStatus

# Store todos in ~/Hangar/.claude/todos/
TODOS_DIR = Path.home() / "Hangar" / ".claude" / "todos"


def get_todos_path(project_name: str) -> Path:
    """Get the path to a project's todo file."""
    return TODOS_DIR / f"{project_name}.json"


def load_todos(project_name: str) -> list[Todo]:
    """Load todos for a project."""
    todos_path = get_todos_path(project_name)
    if not todos_path.exists():
        return []

    try:
        with open(todos_path) as f:
            data = json.load(f)
        return [Todo.from_dict(item) for item in data.get("items", [])]
    except (json.JSONDecodeError, KeyError, IOError):
        return []


def save_todos(project_name: str, todos: list[Todo]) -> bool:
    """Save todos for a project."""
    todos_path = get_todos_path(project_name)

    # Ensure directory exists
    TODOS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with open(todos_path, "w") as f:
            json.dump({"items": [t.to_dict() for t in todos]}, f, indent=2)
        return True
    except IOError:
        return False


def count_pending_todos(project_name: str) -> int:
    """Count pending todos for a project."""
    todos = load_todos(project_name)
    return sum(1 for t in todos if t.status != TodoStatus.COMPLETED)
