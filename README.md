# Hangar TUI

Terminal UI for navigating and managing projects in your `~/Hangar` workspace.

## Features

- **Project Navigation** - Browse projects with git status, branch, and todo count
- **Tmux Integration** - Open projects in a new tmux window with Claude | nvim split
- **Per-Project Todos** - Persistent todo lists for each project
- **GitHub Integration** - Open repos in browser with `g`
- **Project Status** - View commits, branches, and open PRs
- **Hangar ↔ Stash** - Archive projects to `~/Stash` and back

## Installation

```bash
cd ~/Hangar/hangar-tui
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Add to your `.zshrc`:
```bash
hangar() {
  source ~/Hangar/hangar-tui/.venv/bin/activate && command hangar "$@"
}
```

## Usage

```bash
hangar
```

## Keybindings

### Main View
| Key | Action |
|-----|--------|
| `↑/↓` or `j/k` | Navigate projects |
| `Enter` | Open in tmux (Claude \| nvim) |
| `l` | Open in tmux (Claude \| lazygit) |
| `g` | Open GitHub PRs in browser |
| `t` | Project todos |
| `s` | Project status |
| `i` | View README |
| `a` | Add project (clone from GitHub SSH URL) |
| `m` | Move to Stash / Hangar |
| `Tab` or `]` | Toggle Hangar/Stash view |
| `r` | Refresh |
| `q` | Quit |

### Todo Panel
| Key | Action |
|-----|--------|
| `↑/↓` or `j/k` | Navigate todos |
| `a` | Add todo |
| `e` | Edit todo |
| `d` | Delete todo |
| `Space` | Toggle status |
| `Esc` | Close |

## Folder Structure

```
~/
├── Hangar/                    # Active projects
│   ├── .claude/
│   │   ├── settings.local.json
│   │   └── todos/             # Per-project todo files
│   │       ├── project-a.json
│   │       └── project-b.json
│   ├── hangar-tui/            # This project
│   ├── project-a/
│   └── project-b/
└── Stash/                     # Archived projects
    └── old-project/
```

## Todo Storage

Todos are stored in `~/Hangar/.claude/todos/{project-name}.json`:

```json
{
  "items": [
    {"content": "Task description", "status": "pending"},
    {"content": "Another task", "status": "completed"}
  ]
}
```

Status values: `pending`, `in_progress`, `completed`
