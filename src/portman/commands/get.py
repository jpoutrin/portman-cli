"""Get command - retrieve port for a service."""

import typer

from ..allocator import PortAllocationError, PortAllocator
from ..context import get_context
from ..discovery import infer_service_type
from .common import console, error_console, get_db


def get(
    service: str = typer.Argument(..., help="Service name (e.g., postgres, redis)"),
    quiet: bool = typer.Option(False, "-q", "--quiet", help="Output only the port number"),
    book: bool = typer.Option(True, "--book/--no-book", help="Auto-book if not allocated"),
) -> None:
    """Get the port for a service in current context.

    If not allocated and --book is set (default), automatically allocates a port.

    Examples:
        portman get postgres
        portman get redis -q
        PGPORT=$(portman get postgres -q)
    """
    db = get_db()
    ctx = get_context()

    # Check if already allocated
    alloc = db.get_allocation(ctx.hash, service)

    if alloc:
        # Update access timestamp
        db.touch_allocation(alloc["id"])
        port = alloc["port"]
    elif book:
        # Allocate new port
        allocator = PortAllocator(db)
        service_type = infer_service_type(service)
        try:
            port = allocator.allocate(service_type, ctx.hash)
            # Create allocation in DB
            db.create_allocation(
                context_hash=ctx.hash,
                context_path=ctx.path,
                context_label=ctx.label,
                service=service,
                port=port,
                source="manual",
            )
        except PortAllocationError as e:
            error_console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    else:
        error_console.print(
            f"[yellow]No port allocated for '{service}' in current context[/yellow]"
        )
        raise typer.Exit(1)

    if quiet:
        print(port)
    else:
        console.print(f"[green]{service}[/green]: {port}")
