"""Export command - output port allocations as environment variables."""

import json

import typer

from ..allocator import PortAllocationError, PortAllocator
from ..context import get_context
from ..discovery import discover_services, infer_service_type
from .common import get_db


def export_cmd(
    auto: bool = typer.Option(False, "--auto", help="Auto-discover and book services"),
    compose_file: str | None = typer.Option(
        None, "--compose-file", help="Path to docker-compose file"
    ),
    format: str = typer.Option("shell", "--format", help="Output format: shell, json, env"),
) -> None:
    """Export port allocations as environment variables.

    Designed for use with direnv:
        eval "$(portman export --auto)"

    Examples:
        portman export
        portman export --auto
        portman export --auto --compose-file docker-compose.prod.yml
        portman export --format json
    """
    db = get_db()
    ctx = get_context()

    # Auto-book if requested
    if auto:
        allocator = PortAllocator(db)
        services = discover_services(compose_file=compose_file)

        for svc in services:
            existing = db.get_allocation(ctx.hash, svc.name)
            if existing:
                # Touch to update timestamp
                db.touch_allocation(existing["id"])
                continue

            # Allocate
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
            except PortAllocationError:
                # Silently skip if can't allocate
                continue

    # Get allocations
    allocations = db.get_allocations_by_context(ctx.hash)

    if format == "json":
        output = {
            alloc["env_var"] or f"{alloc['service'].upper()}_PORT": alloc["port"]
            for alloc in allocations
        }
        print(json.dumps(output, indent=2))
    elif format == "env":
        for alloc in allocations:
            env_var = alloc["env_var"] or f"{alloc['service'].upper()}_PORT"
            print(f"{env_var}={alloc['port']}")
    else:  # shell
        for alloc in allocations:
            env_var = alloc["env_var"] or f"{alloc['service'].upper()}_PORT"
            print(f"export {env_var}={alloc['port']}")
        # Also export compose project name for isolation
        print(f"export COMPOSE_PROJECT_NAME={ctx.label.replace('/', '-')}")
