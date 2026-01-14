"""Claude config service for parsing and editing CLAUDE.md."""

import re
from dataclasses import dataclass
from pathlib import Path


CLAUDE_MD_PATH = Path.home() / "Hangar" / "CLAUDE.md"


@dataclass
class ConfigSection:
    """A section in CLAUDE.md."""
    title: str
    content: str
    level: int = 2  # Header level (## = 2, ### = 3, etc.)

    def to_markdown(self) -> str:
        """Convert section back to markdown."""
        header = "#" * self.level
        return f"{header} {self.title}\n\n{self.content}"


def parse_claude_md(path: Path = CLAUDE_MD_PATH) -> tuple[str, list[ConfigSection]]:
    """Parse CLAUDE.md into preamble and sections.

    Returns (preamble, sections) where preamble is content before first header.
    """
    if not path.exists():
        return "", []

    text = path.read_text()
    lines = text.split("\n")

    preamble_lines = []
    sections: list[ConfigSection] = []
    current_section: ConfigSection | None = None
    current_content: list[str] = []

    for line in lines:
        # Check for header
        header_match = re.match(r'^(#{1,6})\s+(.+)$', line)

        if header_match:
            # Save previous section if exists
            if current_section is not None:
                current_section.content = "\n".join(current_content).strip()
                sections.append(current_section)

            level = len(header_match.group(1))
            title = header_match.group(2).strip()
            current_section = ConfigSection(title=title, content="", level=level)
            current_content = []
        elif current_section is None:
            # Before any header - this is preamble
            preamble_lines.append(line)
        else:
            # Content of current section
            current_content.append(line)

    # Save last section
    if current_section is not None:
        current_section.content = "\n".join(current_content).strip()
        sections.append(current_section)

    preamble = "\n".join(preamble_lines).strip()
    return preamble, sections


def save_claude_md(preamble: str, sections: list[ConfigSection], path: Path = CLAUDE_MD_PATH) -> bool:
    """Save sections back to CLAUDE.md.

    Returns True on success, False on failure.
    """
    try:
        parts = []
        if preamble:
            parts.append(preamble)

        for section in sections:
            parts.append(section.to_markdown())

        content = "\n\n".join(parts) + "\n"
        path.write_text(content)
        return True
    except Exception:
        return False


def add_section(title: str, content: str, level: int = 2) -> bool:
    """Add a new section to CLAUDE.md."""
    preamble, sections = parse_claude_md()
    sections.append(ConfigSection(title=title, content=content, level=level))
    return save_claude_md(preamble, sections)


def update_section(index: int, title: str, content: str) -> bool:
    """Update an existing section."""
    preamble, sections = parse_claude_md()
    if 0 <= index < len(sections):
        sections[index].title = title
        sections[index].content = content
        return save_claude_md(preamble, sections)
    return False


def delete_section(index: int) -> bool:
    """Delete a section by index."""
    preamble, sections = parse_claude_md()
    if 0 <= index < len(sections):
        sections.pop(index)
        return save_claude_md(preamble, sections)
    return False
