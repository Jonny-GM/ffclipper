"""Command-line interface entry point."""

import sys

from cyclopts import App

from .backend import ffclipper

app = App()
app.default(ffclipper)


def main(argv: list[str] | None = None) -> int:
    """Run the ffclipper CLI."""
    argv = sys.argv[1:] if argv is None else argv
    return app(argv)


if __name__ == "__main__":
    raise SystemExit(main())
