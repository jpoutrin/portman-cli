"""Discover command - show services and volumes from docker-compose files."""

from pathlib import Path

import typer
from rich.table import Table

from ..discovery import discover_services, discover_volumes
from .common import console, debug


def discover(
    compose_file: str | None = typer.Option(
        None, "-f", "--compose-file", help="Path to docker-compose file"
    ),
) -> None:
    """Discover services and volumes from docker-compose.yml without booking.

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
    volumes = discover_volumes(compose_file=compose_file)
    debug(f"Found {len(services)} services")
    debug(f"Found {len(volumes)} volumes")

    if not services and not volumes:
        file_desc = compose_file if compose_file else "docker-compose.yml"
        console.print(f"[yellow]No services or volumes discovered from {file_desc}[/yellow]")
        return

    if services:
        service_table = Table(title="Discovered Services")
        service_table.add_column("Service", style="green")
        service_table.add_column("Container Port", style="yellow")
        service_table.add_column("Env Var", style="blue")
        service_table.add_column("Source", style="dim")

        for svc in services:
            service_table.add_row(
                svc.name,
                str(svc.container_port),
                svc.env_var or "-",
                Path(svc.source).name if svc.source else "-",
            )

        console.print(service_table)

    if volumes:
        volume_table = Table(title="Discovered Volumes")
        volume_table.add_column("Service", style="green")
        volume_table.add_column("Compose Volume", style="yellow")
        volume_table.add_column("Docker Volume", style="blue")
        volume_table.add_column("Mount", style="magenta")
        volume_table.add_column("Source", style="dim")

        for volume in volumes:
            volume_table.add_row(
                volume.service or "-",
                volume.compose_volume_key,
                volume.docker_volume_name,
                volume.mount_target or "-",
                Path(volume.source).name if volume.source else "-",
            )

        console.print(volume_table)
