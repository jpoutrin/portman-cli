"""Status command - show port allocations."""

from pathlib import Path

import typer
from rich.table import Table

from ..context import get_context
from ..system import DockerInspector, SystemScanner
from ..volumes import resolve_volume_status
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
        tracked_volumes = db.get_all_tracked_volumes()
    else:
        allocations = db.get_allocations_by_context(ctx.hash)
        tracked_volumes = db.get_tracked_volumes_by_context(ctx.hash)

    if not allocations and not tracked_volumes:
        console.print("[yellow]No tracked resources found[/yellow]")
        return

    # Check live status if requested
    listening_ports: set[int] = set()
    if live:
        scanner = SystemScanner()
        listening_ports = scanner.get_listening_ports()

    if allocations:
        title = "Port Allocations" if all else "Current Context Port Allocations"
        allocation_table = Table(title=title)
        if all:
            allocation_table.add_column("Context", style="cyan")
            allocation_table.add_column("Label", style="blue")
        allocation_table.add_column("Service", style="green")
        allocation_table.add_column("Port", style="yellow")
        if live:
            allocation_table.add_column("Status", style="magenta")

        for alloc in allocations:
            row = []
            if all:
                row.append(alloc["context_hash"][:8])
                row.append(alloc["context_label"] or "-")
            row.append(alloc["service"])
            row.append(str(alloc["port"]))
            if live:
                row.append("● LISTEN" if alloc["port"] in listening_ports else "○ free")
            allocation_table.add_row(*row)

        console.print(allocation_table)

    if tracked_volumes:
        inspector = DockerInspector()
        if not inspector.is_docker_available():
            inspector = None

        volume_table = Table(title="Tracked Volumes" if all else "Current Context Tracked Volumes")
        if all:
            volume_table.add_column("Context", style="cyan")
            volume_table.add_column("Label", style="blue")
        volume_table.add_column("Service", style="green")
        volume_table.add_column("Compose Volume", style="yellow")
        volume_table.add_column("Docker Volume", style="blue")
        volume_table.add_column("Status", style="magenta")
        volume_table.add_column("Source", style="dim")

        for volume in tracked_volumes:
            row = []
            if all:
                row.append(volume["context_hash"][:8])
                row.append(volume["context_label"] or "-")
            row.extend(
                [
                    volume["service"] or "-",
                    volume["compose_volume_key"],
                    volume["docker_volume_name"],
                    resolve_volume_status(volume, inspector),
                    Path(volume["compose_file"]).name,
                ]
            )
            volume_table.add_row(*row)

        console.print(volume_table)
