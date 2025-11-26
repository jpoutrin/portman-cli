"""Release command - free up port allocations."""

import typer

from ..context import get_context
from .common import console, get_db


def release(
    service: str | None = typer.Argument(None, help="Service to release"),
    all: bool = typer.Option(False, "--all", help="Release all ports for current context"),
) -> None:
    """Release port allocation(s) for current context.

    Examples:
        portman release postgres
        portman release --all
    """
    db = get_db()
    ctx = get_context()

    if all:
        count = db.delete_allocations_by_context(ctx.hash)
        console.print(f"[green]Released {count} allocation(s)[/green]")
    elif service:
        deleted = db.delete_allocation_by_service(ctx.hash, service)
        if deleted:
            console.print(f"[green]Released {service}[/green]")
        else:
            console.print(f"[yellow]No allocation found for {service}[/yellow]")
    else:
        console.print("[red]Error:[/red] Specify service or use --all")
        raise typer.Exit(1)
