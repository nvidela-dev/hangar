"""Main Textual application for Hangar TUI."""

import shutil
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

from .models import GitStatus, Project, Todo, TodoStatus
from .services.git import get_git_info, get_recent_commits, get_open_prs, count_open_prs
from .services.github import open_github_prs
from .services.todos import count_pending_todos, load_todos, save_todos
from .services.tmux import open_in_tmux, open_in_tmux_claude, open_in_tmux_lazygit, open_in_tmux_nvim

HANGAR_PATH = Path.home() / "Hangar"
STASH_PATH = Path.home() / "Stash"
EXCLUDED_DIRS = {".claude", ".DS_Store", ".git"}


class TodoScreen(ModalScreen):
    """Modal screen for viewing and editing project todos."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("a", "add", "Add"),
        Binding("d", "delete", "Delete"),
        Binding("e", "edit", "Edit"),
        Binding("space", "toggle", "Toggle Status"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    CSS = """
    TodoScreen {
        align: center middle;
    }
    TodoScreen > Container {
        width: 80%;
        height: 80%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    TodoScreen .title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    TodoScreen DataTable {
        height: 1fr;
    }
    TodoScreen .footer-hint {
        text-align: center;
        color: $text-muted;
        padding-top: 1;
    }
    """

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.todos: list[Todo] = []

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(f"Todos: {self.project.name}", classes="title")
            yield DataTable(id="todo-table")
            yield Label("a:Add  d:Delete  e:Edit  Space:Toggle  Esc:Close", classes="footer-hint")

    def on_mount(self) -> None:
        self.todos = load_todos(self.project.name)
        table = self.query_one("#todo-table", DataTable)
        table.add_columns("Status", "Todo")
        table.cursor_type = "row"
        self._refresh_table()

    def _refresh_table(self) -> None:
        table = self.query_one("#todo-table", DataTable)
        table.clear()
        for todo in self.todos:
            status_icon = {
                TodoStatus.PENDING: "○",
                TodoStatus.IN_PROGRESS: "◐",
                TodoStatus.COMPLETED: "●",
            }[todo.status]
            status_color = {
                TodoStatus.PENDING: "white",
                TodoStatus.IN_PROGRESS: "yellow",
                TodoStatus.COMPLETED: "green",
            }[todo.status]
            table.add_row(f"[{status_color}]{status_icon}[/]", todo.content)

    def _save(self) -> None:
        save_todos(self.project.name, self.todos)

    def action_close(self) -> None:
        self.dismiss()

    def action_toggle(self) -> None:
        table = self.query_one("#todo-table", DataTable)
        if table.row_count == 0:
            return
        row_idx = table.cursor_row
        if 0 <= row_idx < len(self.todos):
            self.todos[row_idx].cycle_status()
            self._save()
            self._refresh_table()
            table.move_cursor(row=row_idx)

    def action_delete(self) -> None:
        table = self.query_one("#todo-table", DataTable)
        if table.row_count == 0:
            return
        row_idx = table.cursor_row
        if 0 <= row_idx < len(self.todos):
            self.todos.pop(row_idx)
            self._save()
            self._refresh_table()

    def action_add(self) -> None:
        self.app.push_screen(
            TodoInputScreen("Add Todo", ""),
            callback=self._on_add_complete,
        )

    def _on_add_complete(self, content: str | None) -> None:
        if content:
            self.todos.append(Todo(content=content))
            self._save()
            self._refresh_table()

    def action_edit(self) -> None:
        table = self.query_one("#todo-table", DataTable)
        if table.row_count == 0:
            return
        row_idx = table.cursor_row
        if 0 <= row_idx < len(self.todos):
            self.app.push_screen(
                TodoInputScreen("Edit Todo", self.todos[row_idx].content),
                callback=lambda c: self._on_edit_complete(row_idx, c),
            )

    def _on_edit_complete(self, row_idx: int, content: str | None) -> None:
        if content and 0 <= row_idx < len(self.todos):
            self.todos[row_idx].content = content
            self._save()
            self._refresh_table()

    def action_cursor_down(self) -> None:
        table = self.query_one("#todo-table", DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        table = self.query_one("#todo-table", DataTable)
        table.action_cursor_up()


class TodoInputScreen(ModalScreen[str | None]):
    """Modal for inputting todo text."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS = """
    TodoInputScreen {
        align: center middle;
    }
    TodoInputScreen > Container {
        width: 60%;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    TodoInputScreen .title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    """

    def __init__(self, title: str, initial: str) -> None:
        super().__init__()
        self.title_text = title
        self.initial = initial

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(self.title_text, classes="title")
            yield Input(value=self.initial, id="todo-input")

    def on_mount(self) -> None:
        self.query_one("#todo-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class StatusScreen(ModalScreen):
    """Modal screen showing project status details."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close"),
    ]

    CSS = """
    StatusScreen {
        align: center middle;
    }
    StatusScreen > Container {
        width: 80%;
        height: 80%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    StatusScreen .title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    StatusScreen .section {
        padding-top: 1;
        text-style: bold;
        color: $primary;
    }
    StatusScreen .content {
        padding-left: 2;
    }
    """

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(f"Status: {self.project.name}", classes="title")
            yield Static(id="status-content")

    def on_mount(self) -> None:
        content = self.query_one("#status-content", Static)
        lines = []

        # Git info
        lines.append("[bold cyan]Git Status[/]")
        if self.project.git_status == GitStatus.NO_GIT:
            lines.append("  Not a git repository")
        else:
            lines.append(f"  Branch: {self.project.branch or 'unknown'}")
            status = "Clean" if self.project.git_status == GitStatus.CLEAN else "Has uncommitted changes"
            lines.append(f"  Status: {status}")

        # Recent commits
        if self.project.git_status != GitStatus.NO_GIT:
            lines.append("")
            lines.append("[bold cyan]Recent Commits[/]")
            commits = get_recent_commits(self.project.path)
            if commits:
                for c in commits[:5]:
                    date_str = c.date.strftime("%Y-%m-%d")
                    lines.append(f"  {c.hash} {date_str} {c.message[:50]}")
            else:
                lines.append("  No commits")

            # Open PRs
            lines.append("")
            lines.append("[bold cyan]Open PRs[/]")
            prs = get_open_prs(self.project.path)
            if prs:
                for pr in prs:
                    lines.append(f"  #{pr['number']} {pr['title'][:40]}")
            else:
                lines.append("  No open PRs")

        content.update("\n".join(lines))

    def action_close(self) -> None:
        self.dismiss()


class HangarApp(App):
    """Main Hangar TUI application."""

    TITLE = "Hangar"
    CSS = """
    Screen {
        background: $surface;
    }
    #main-container {
        height: 100%;
    }
    #project-table {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("enter", "open_tmux", "Open"),
        Binding("c", "open_claude", "Claude"),
        Binding("l", "open_lazygit", "Lazygit"),
        Binding("n", "open_nvim", "Neovim"),
        Binding("g", "open_github", "PRs"),
        Binding("t", "open_todos", "Todos"),
        Binding("s", "open_status", "Status"),
        Binding("m", "move_project", "Move"),
        Binding("tab", "toggle_view", "Toggle View"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.viewing_stash = False
        self.projects: list[Project] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-container"):
            yield DataTable(id="project-table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#project-table", DataTable)
        table.add_columns("", "Project", "Branch", "Last Commit", "Todos", "PRs")
        table.cursor_type = "row"
        self._refresh_projects()

    def _get_current_path(self) -> Path:
        return STASH_PATH if self.viewing_stash else HANGAR_PATH

    def _refresh_projects(self) -> None:
        base_path = self._get_current_path()
        self.projects = []

        if not base_path.exists():
            base_path.mkdir(parents=True, exist_ok=True)

        for item in sorted(base_path.iterdir()):
            if item.is_dir() and item.name not in EXCLUDED_DIRS:
                git_info = get_git_info(item)
                todo_count = count_pending_todos(item.name)
                pr_count = count_open_prs(item) if git_info.remote_url else 0
                self.projects.append(Project(
                    name=item.name,
                    path=item,
                    git_status=git_info.status,
                    branch=git_info.branch,
                    last_commit_date=git_info.last_commit_date,
                    last_commit_message=git_info.last_commit_message,
                    remote_url=git_info.remote_url,
                    todo_count=todo_count,
                    pr_count=pr_count,
                ))

        table = self.query_one("#project-table", DataTable)
        table.clear()
        for proj in self.projects:
            date_str = proj.last_commit_date.strftime("%Y-%m-%d") if proj.last_commit_date else "-"
            todo_str = str(proj.todo_count) if proj.todo_count > 0 else "-"
            pr_str = f"[cyan]{proj.pr_count}[/]" if proj.pr_count > 0 else "-"
            table.add_row(
                f"[{proj.status_color}]{proj.status_icon}[/]",
                proj.name,
                proj.branch or "-",
                date_str,
                todo_str,
                pr_str,
            )

    def _get_selected_project(self) -> Project | None:
        table = self.query_one("#project-table", DataTable)
        if table.row_count == 0:
            return None
        row_idx = table.cursor_row
        if 0 <= row_idx < len(self.projects):
            return self.projects[row_idx]
        return None

    def action_refresh(self) -> None:
        self._refresh_projects()

    def action_toggle_view(self) -> None:
        self.viewing_stash = not self.viewing_stash
        self._refresh_projects()

    def action_open_tmux(self) -> None:
        project = self._get_selected_project()
        if project:
            if open_in_tmux(project.name, project.path):
                self.notify(f"Opened {project.name} in tmux")
            else:
                self.notify("Failed to open in tmux", severity="error")

    def action_open_github(self) -> None:
        project = self._get_selected_project()
        if project:
            if project.remote_url:
                if open_github_prs(project.path):
                    self.notify(f"Opening {project.name} PRs")
                else:
                    self.notify("Failed to open GitHub PRs", severity="error")
            else:
                self.notify("No GitHub remote", severity="warning")

    def action_open_claude(self) -> None:
        project = self._get_selected_project()
        if project:
            if open_in_tmux_claude(project.name, project.path):
                self.notify(f"Opened {project.name} with Claude")
            else:
                self.notify("Failed to open Claude", severity="error")

    def action_open_lazygit(self) -> None:
        project = self._get_selected_project()
        if project:
            if open_in_tmux_lazygit(project.name, project.path):
                self.notify(f"Opened {project.name} with lazygit")
            else:
                self.notify("Failed to open lazygit", severity="error")

    def action_open_nvim(self) -> None:
        project = self._get_selected_project()
        if project:
            if open_in_tmux_nvim(project.name, project.path):
                self.notify(f"Opened {project.name} with neovim")
            else:
                self.notify("Failed to open neovim", severity="error")

    def action_open_todos(self) -> None:
        project = self._get_selected_project()
        if project:
            self.push_screen(TodoScreen(project), callback=lambda _: self._refresh_projects())

    def action_open_status(self) -> None:
        project = self._get_selected_project()
        if project:
            self.push_screen(StatusScreen(project))

    def action_move_project(self) -> None:
        project = self._get_selected_project()
        if not project:
            return

        src = project.path
        dest_base = HANGAR_PATH if self.viewing_stash else STASH_PATH
        dest = dest_base / project.name

        # Ensure destination directory exists
        dest_base.mkdir(parents=True, exist_ok=True)

        try:
            shutil.move(str(src), str(dest))
            location = "Hangar" if self.viewing_stash else "Stash"
            self.notify(f"Moved {project.name} to {location}")
            self._refresh_projects()
        except Exception as e:
            self.notify(f"Failed to move: {e}", severity="error")

    def action_cursor_down(self) -> None:
        table = self.query_one("#project-table", DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        table = self.query_one("#project-table", DataTable)
        table.action_cursor_up()
