"""Typer CLI for Portman - Main entry point."""

import typer

from . import __version__
from .commands import (
    book,
    config,
    context,
    discover,
    export_cmd,
    gc,
    get,
    init,
    list_cmd,
    prune,
    release,
    status,
)

app = typer.Typer(
    name="portman",
    help="Port Manager for Development Environments",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(f"portman version {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Port Manager for Development Environments."""
    pass

# Register all commands
app.command()(get)
app.command()(book)
app.command()(release)
app.command(name="export")(export_cmd)
app.command()(status)
app.command(name="list")(list_cmd)
app.command()(context)
app.command()(discover)
app.command()(prune)
app.command()(gc)
app.command()(init)
app.command()(config)


def main() -> None:
    """Main entry point."""
    app()
