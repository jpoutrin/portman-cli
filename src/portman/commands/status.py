"""Status command - show port allocations."""

import typer
from rich.table import Table

from ..context import get_context
from ..system import SystemScanner
from .common import console, get_db


def status(
    all: bool = typer.Option(False, "-a", "--all", help="Show all contexts, not just current"),
    live: bool = typer.Option(False, "--live", help="Check if ports are actually listening"),
) -> None:
    """Show port allocations status.

    Examples:
        portman status
        portman status --all
        portman status --all --live
    """
    db = get_db()
    ctx = get_context()

    if all:
        allocations = db.get_all_allocations()
    else:
        allocations = db.get_allocations_by_context(ctx.hash)

    if not allocations:
        console.print("[yellow]No allocations found[/yellow]")
        return

    # Check live status if requested
    listening_ports: set[int] = set()
    if live:
        scanner = SystemScanner()
        listening_ports = scanner.get_listening_ports()

    # Build table
    table = Table(title="Port Allocations" if all else "Current Context Allocations")
    if all:
        table.add_column("Context", style="cyan")
        table.add_column("Label", style="blue")
    table.add_column("Service", style="green")
    table.add_column("Port", style="yellow")
    if live:
        table.add_column("Status", style="magenta")

    for alloc in allocations:
        row = []
        if all:
            row.append(alloc["context_hash"][:8])
            row.append(alloc["context_label"] or "-")
        row.append(alloc["service"])
        row.append(str(alloc["port"]))
        if live:
            if alloc["port"] in listening_ports:
                row.append("● LISTEN")
            else:
                row.append("○ free")
        table.add_row(*row)

    console.print(table)
