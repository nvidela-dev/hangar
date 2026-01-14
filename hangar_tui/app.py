"""Main Textual application for Hangar TUI."""

import shutil
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    Static,
    TextArea,
)

from .models import GitStatus, Project, Todo, TodoStatus
from .services.git import get_git_info, get_recent_commits, get_open_prs, count_open_prs, clone_repo, validate_ssh_url
from .services.github import open_github_prs
from .services.todos import count_pending_todos, load_todos, save_todos
from .services.tmux import open_in_tmux, open_in_tmux_claude, open_in_tmux_lazygit, open_in_tmux_nvim
from .services.claude_config import parse_claude_md, save_claude_md, ConfigSection

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


class ReadmeScreen(ModalScreen):
    """Modal screen showing project README."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close"),
        Binding("j", "scroll_down", "Down", show=False),
        Binding("k", "scroll_up", "Up", show=False),
    ]

    CSS = """
    ReadmeScreen {
        align: center middle;
    }
    ReadmeScreen > Container {
        width: 90%;
        height: 90%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    ReadmeScreen .title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    ReadmeScreen VerticalScroll {
        height: 1fr;
    }
    ReadmeScreen .no-readme {
        text-align: center;
        color: $text-muted;
        padding-top: 2;
    }
    """

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(f"README: {self.project.name}", classes="title")
            yield VerticalScroll(id="readme-scroll")

    def on_mount(self) -> None:
        scroll = self.query_one("#readme-scroll", VerticalScroll)
        readme_path = self.project.path / "README.md"

        if readme_path.exists():
            try:
                content = readme_path.read_text()
                scroll.mount(Markdown(content))
            except Exception:
                scroll.mount(Static("Failed to read README", classes="no-readme"))
        else:
            scroll.mount(Static("No README.md found", classes="no-readme"))

    def action_close(self) -> None:
        self.dismiss()

    def action_scroll_down(self) -> None:
        self.query_one("#readme-scroll", VerticalScroll).scroll_down()

    def action_scroll_up(self) -> None:
        self.query_one("#readme-scroll", VerticalScroll).scroll_up()


class AddProjectScreen(ModalScreen[str | None]):
    """Modal for adding a new project from GitHub SSH URL."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS = """
    AddProjectScreen {
        align: center middle;
    }
    AddProjectScreen > Container {
        width: 70%;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    AddProjectScreen .title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    AddProjectScreen .hint {
        color: $text-muted;
        padding-bottom: 1;
    }
    AddProjectScreen .error {
        color: $error;
        padding-top: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.error_label: Label | None = None

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("Add Project", classes="title")
            yield Label("Enter GitHub SSH URL (e.g., git@github.com:owner/repo.git)", classes="hint")
            yield Input(placeholder="git@github.com:owner/repo.git", id="url-input")
            yield Label("", id="error-label", classes="error")

    def on_mount(self) -> None:
        self.query_one("#url-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        error_label = self.query_one("#error-label", Label)
        url = event.value.strip()
        if url:
            is_valid, message = validate_ssh_url(url)
            if not is_valid:
                error_label.update(message)
            else:
                error_label.update("")
        else:
            error_label.update("")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        url = event.value.strip()
        if url:
            is_valid, message = validate_ssh_url(url)
            if is_valid:
                self.dismiss(url)
            else:
                self.query_one("#error-label", Label).update(message)
        else:
            self.query_one("#error-label", Label).update("Please enter a URL")

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfigScreen(ModalScreen):
    """Modal screen for viewing and editing CLAUDE.md sections."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close"),
        Binding("a", "add", "Add"),
        Binding("e", "edit", "Edit"),
        Binding("d", "delete", "Delete"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    CSS = """
    ConfigScreen {
        align: center middle;
    }
    ConfigScreen > Container {
        width: 90%;
        height: 90%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    ConfigScreen .title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    ConfigScreen DataTable {
        height: 1fr;
    }
    ConfigScreen .footer-hint {
        text-align: center;
        color: $text-muted;
        padding-top: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.preamble = ""
        self.sections: list[ConfigSection] = []

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("CLAUDE.md Configuration", classes="title")
            yield DataTable(id="config-table")
            yield Label("a:Add  e:Edit  d:Delete  Esc:Close", classes="footer-hint")

    def on_mount(self) -> None:
        self.preamble, self.sections = parse_claude_md()
        table = self.query_one("#config-table", DataTable)
        table.add_columns("Level", "Section", "Preview")
        table.cursor_type = "row"
        self._refresh_table()

    def _refresh_table(self) -> None:
        table = self.query_one("#config-table", DataTable)
        table.clear()
        for section in self.sections:
            level_str = "#" * section.level
            preview = section.content[:60].replace("\n", " ") + "..." if len(section.content) > 60 else section.content.replace("\n", " ")
            table.add_row(level_str, section.title, preview)

    def _save(self) -> bool:
        return save_claude_md(self.preamble, self.sections)

    def action_close(self) -> None:
        self.dismiss()

    def action_add(self) -> None:
        self.app.push_screen(
            ConfigEditScreen("Add Section", "", "", 2),
            callback=self._on_add_complete,
        )

    def _on_add_complete(self, result: tuple[str, str, int] | None) -> None:
        if result:
            title, content, level = result
            self.sections.append(ConfigSection(title=title, content=content, level=level))
            if self._save():
                self._refresh_table()
            else:
                self.app.notify("Failed to save", severity="error")

    def action_edit(self) -> None:
        table = self.query_one("#config-table", DataTable)
        if table.row_count == 0:
            return
        row_idx = table.cursor_row
        if 0 <= row_idx < len(self.sections):
            section = self.sections[row_idx]
            self.app.push_screen(
                ConfigEditScreen("Edit Section", section.title, section.content, section.level),
                callback=lambda r: self._on_edit_complete(row_idx, r),
            )

    def _on_edit_complete(self, row_idx: int, result: tuple[str, str, int] | None) -> None:
        if result and 0 <= row_idx < len(self.sections):
            title, content, level = result
            self.sections[row_idx].title = title
            self.sections[row_idx].content = content
            self.sections[row_idx].level = level
            if self._save():
                self._refresh_table()
            else:
                self.app.notify("Failed to save", severity="error")

    def action_delete(self) -> None:
        table = self.query_one("#config-table", DataTable)
        if table.row_count == 0:
            return
        row_idx = table.cursor_row
        if 0 <= row_idx < len(self.sections):
            self.sections.pop(row_idx)
            if self._save():
                self._refresh_table()
            else:
                self.app.notify("Failed to save", severity="error")

    def action_cursor_down(self) -> None:
        table = self.query_one("#config-table", DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        table = self.query_one("#config-table", DataTable)
        table.action_cursor_up()


class ConfigEditScreen(ModalScreen[tuple[str, str, int] | None]):
    """Modal for editing a config section."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
    ]

    CSS = """
    ConfigEditScreen {
        align: center middle;
    }
    ConfigEditScreen > Container {
        width: 80%;
        height: 80%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    ConfigEditScreen .title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    ConfigEditScreen .field-label {
        padding-top: 1;
        color: $primary;
    }
    ConfigEditScreen TextArea {
        height: 1fr;
    }
    ConfigEditScreen .footer-hint {
        text-align: center;
        color: $text-muted;
        padding-top: 1;
    }
    """

    def __init__(self, title: str, section_title: str, content: str, level: int) -> None:
        super().__init__()
        self.title_text = title
        self.section_title = section_title
        self.content = content
        self.level = level

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(self.title_text, classes="title")
            yield Label("Section Title:", classes="field-label")
            yield Input(value=self.section_title, id="title-input")
            yield Label("Level (1-6):", classes="field-label")
            yield Input(value=str(self.level), id="level-input")
            yield Label("Content:", classes="field-label")
            yield TextArea(self.content, id="content-area")
            yield Label("Ctrl+S:Save  Esc:Cancel", classes="footer-hint")

    def on_mount(self) -> None:
        self.query_one("#title-input", Input).focus()

    def action_save(self) -> None:
        title = self.query_one("#title-input", Input).value.strip()
        level_str = self.query_one("#level-input", Input).value.strip()
        content = self.query_one("#content-area", TextArea).text

        if not title:
            self.app.notify("Title is required", severity="error")
            return

        try:
            level = int(level_str)
            if not 1 <= level <= 6:
                raise ValueError()
        except ValueError:
            self.app.notify("Level must be 1-6", severity="error")
            return

        self.dismiss((title, content, level))

    def action_cancel(self) -> None:
        self.dismiss(None)


class HangarApp(App):
    """Main Hangar TUI application."""

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
        Binding("i", "open_readme", "Readme"),
        Binding("m", "move_project", "Move"),
        Binding("a", "add_project", "Add"),
        Binding(".", "open_config", "Config"),
        Binding("tab", "toggle_view", "Toggle View"),
        Binding("]", "toggle_view", "Toggle View", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.viewing_stash = False
        self.projects: list[Project] = []
        self.title = "Hangar"

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
        self.title = "Stash" if self.viewing_stash else "Hangar"
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

    def action_open_readme(self) -> None:
        project = self._get_selected_project()
        if project:
            self.push_screen(ReadmeScreen(project))

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

    def action_add_project(self) -> None:
        if self.viewing_stash:
            self.notify("Switch to Hangar view to add projects", severity="warning")
            return
        self.push_screen(AddProjectScreen(), callback=self._on_add_project)

    def _on_add_project(self, url: str | None) -> None:
        if not url:
            return
        self.notify(f"Cloning repository...")
        success, message = clone_repo(url, HANGAR_PATH)
        if success:
            self.notify(f"Added project: {message}")
            self._refresh_projects()
        else:
            self.notify(f"Clone failed: {message}", severity="error")

    def action_open_config(self) -> None:
        self.push_screen(ConfigScreen())

    def action_cursor_down(self) -> None:
        table = self.query_one("#project-table", DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        table = self.query_one("#project-table", DataTable)
        table.action_cursor_up()
