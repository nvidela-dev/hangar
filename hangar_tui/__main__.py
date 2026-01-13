"""Entry point for Hangar TUI."""

from .app import HangarApp


def main() -> None:
    """Run the Hangar TUI application."""
    app = HangarApp()
    app.run()


if __name__ == "__main__":
    main()
