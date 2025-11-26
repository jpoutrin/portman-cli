"""Book command - reserve ports for services."""

import typer

from ..allocator import PortAllocationError, PortAllocator
from ..context import get_context
from ..discovery import discover_services, infer_service_type
from .common import console, get_db


def book(
    service: str | None = typer.Argument(None, help="Service name to book"),
    port: int | None = typer.Option(None, "-p", "--port", help="Preferred port"),
    auto: bool = typer.Option(False, "--auto", help="Auto-discover from docker-compose.yml"),
    compose_file: str | None = typer.Option(
        None, "-f", "--compose-file", help="Path to docker-compose file"
    ),
    quiet: bool = typer.Option(False, "-q", "--quiet", help="Minimal output"),
) -> None:
    """Book port(s) for service(s) in current context.

    Examples:
        portman book postgres
        portman book postgres --port 5433
        portman book --auto
        portman book --auto --compose-file docker-compose.prod.yml
    """
    db = get_db()
    ctx = get_context()
    allocator = PortAllocator(db)

    if auto:
        # Auto-discover from docker-compose
        services = discover_services(compose_file=compose_file)
        if not services:
            file_desc = compose_file if compose_file else "docker-compose.yml"
            console.print(f"[yellow]No services discovered from {file_desc}[/yellow]")
            return

        for svc in services:
            # Check if already allocated
            existing = db.get_allocation(ctx.hash, svc.name)
            if existing:
                if not quiet:
                    console.print(f"[dim]{svc.name}: {existing['port']} (already allocated)[/dim]")
                continue

            # Allocate port
            service_type = infer_service_type(svc.name)
            try:
                allocated_port = allocator.allocate(service_type, ctx.hash)
                db.create_allocation(
                    context_hash=ctx.hash,
                    context_path=ctx.path,
                    context_label=ctx.label,
                    service=svc.name,
                    port=allocated_port,
                    container_port=svc.container_port,
                    env_var=svc.env_var,
                    source=svc.source,
                )
                if not quiet:
                    console.print(f"[green]{svc.name}[/green]: {allocated_port}")
            except PortAllocationError as e:
                console.print(f"[red]Error allocating {svc.name}:[/red] {e}")
                continue

    elif service:
        # Book specific service
        existing = db.get_allocation(ctx.hash, service)
        if existing:
            console.print(f"[yellow]{service} already allocated:[/yellow] {existing['port']}")
            return

        service_type = infer_service_type(service)
        try:
            allocated_port = allocator.allocate(service_type, ctx.hash, port)
            db.create_allocation(
                context_hash=ctx.hash,
                context_path=ctx.path,
                context_label=ctx.label,
                service=service,
                port=allocated_port,
                source="manual",
            )
            if quiet:
                print(allocated_port)
            else:
                console.print(f"[green]{service}[/green]: {allocated_port}")
        except PortAllocationError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    else:
        console.print("[red]Error:[/red] Either specify service or use --auto")
        raise typer.Exit(1)
