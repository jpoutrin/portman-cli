"""Config command - manage port range configuration."""

import typer
from rich.table import Table

from .common import console, get_db


def config(
    show: bool = typer.Option(False, "--show", help="Show current configuration"),
    set_range: str | None = typer.Option(
        None, "--set-range", help="Set port range: service:start-end"
    ),
) -> None:
    """Manage portman configuration.

    Examples:
        portman config --show
        portman config --set-range postgres:5500-5599
    """
    db = get_db()

    if show:
        ranges = db.get_all_port_ranges()
        table = Table(title="Port Ranges Configuration")
        table.add_column("Service", style="green")
        table.add_column("Range Start", style="yellow")
        table.add_column("Range End", style="yellow")

        for r in ranges:
            table.add_row(r.service, str(r.start), str(r.end))

        console.print(table)
        return

    if set_range:
        # Parse service:start-end
        parts = set_range.split(":")
        if len(parts) != 2:
            console.print("[red]Error:[/red] Format should be service:start-end")
            raise typer.Exit(1)

        service = parts[0]
        range_parts = parts[1].split("-")
        if len(range_parts) != 2:
            console.print("[red]Error:[/red] Range should be start-end")
            raise typer.Exit(1)

        try:
            start = int(range_parts[0])
            end = int(range_parts[1])
        except ValueError:
            console.print("[red]Error:[/red] Ports must be integers")
            raise typer.Exit(1)

        if start >= end:
            console.print("[red]Error:[/red] Start must be less than end")
            raise typer.Exit(1)

        db.set_port_range(service, start, end)
        console.print(f"[green]Set range for {service}: {start}-{end}[/green]")
        return

    console.print("[yellow]Use --show or --set-range[/yellow]")
