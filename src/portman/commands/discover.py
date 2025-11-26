"""Discover command - show services from docker-compose files."""

from pathlib import Path

import typer
from rich.table import Table

from ..discovery import discover_services
from .common import console, debug


def discover(
    compose_file: str | None = typer.Option(
        None, "-f", "--compose-file", help="Path to docker-compose file"
    ),
) -> None:
    """Discover services from docker-compose.yml without booking.

    Shows what services would be booked with `portman book --auto`.

    Examples:
        portman discover
        portman discover --compose-file docker-compose.prod.yml
    """
    # Debug logging
    debug(f"compose_file parameter = {compose_file!r}")

    if compose_file:
        console.print(f"[dim]Using compose file: {compose_file}[/dim]")

    services = discover_services(compose_file=compose_file)
    debug(f"Found {len(services)} services")

    if not services:
        file_desc = compose_file if compose_file else "docker-compose.yml"
        console.print(f"[yellow]No services discovered from {file_desc}[/yellow]")
        return

    table = Table(title="Discovered Services")
    table.add_column("Service", style="green")
    table.add_column("Container Port", style="yellow")
    table.add_column("Env Var", style="blue")
    table.add_column("Source", style="dim")

    for svc in services:
        table.add_row(
            svc.name,
            str(svc.container_port),
            svc.env_var or "-",
            Path(svc.source).name if svc.source else "-",
        )

    console.print(table)
