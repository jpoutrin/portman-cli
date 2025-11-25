"""Typer CLI for Portman."""

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .allocator import PortAllocationError, PortAllocator
from .context import get_context
from .db import Database
from .direnv import generate_direnvrc_helper, generate_envrc_content
from .discovery import discover_services, infer_service_type
from .pruner import Pruner
from .system import SystemScanner

app = typer.Typer(
    name="portman",
    help="Port Manager for Development Environments",
    no_args_is_help=True,
)
console = Console()
error_console = Console(stderr=True)


def get_db() -> Database:
    """Get database instance."""
    return Database()


# ============================================================================
# MAIN COMMANDS
# ============================================================================


@app.command()
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


@app.command()
def book(
    service: str | None = typer.Argument(None, help="Service name to book"),
    port: int | None = typer.Option(None, "-p", "--port", help="Preferred port"),
    auto: bool = typer.Option(False, "--auto", help="Auto-discover from docker-compose.yml"),
    quiet: bool = typer.Option(False, "-q", "--quiet", help="Minimal output"),
) -> None:
    """Book port(s) for service(s) in current context.

    Examples:
        portman book postgres
        portman book postgres --port 5433
        portman book --auto
    """
    db = get_db()
    ctx = get_context()
    allocator = PortAllocator(db)

    if auto:
        # Auto-discover from docker-compose
        services = discover_services()
        if not services:
            console.print("[yellow]No services discovered from docker-compose.yml[/yellow]")
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


@app.command()
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


@app.command(name="export")
def export_cmd(
    auto: bool = typer.Option(False, "--auto", help="Auto-discover and book services"),
    format: str = typer.Option("shell", "--format", "-f", help="Output format: shell, json, env"),
) -> None:
    """Export port allocations as environment variables.

    Designed for use with direnv:
        eval "$(portman export --auto)"

    Examples:
        portman export
        portman export --auto
        portman export --format json
    """
    db = get_db()
    ctx = get_context()

    # Auto-book if requested
    if auto:
        allocator = PortAllocator(db)
        services = discover_services()

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


# ============================================================================
# INFORMATION COMMANDS
# ============================================================================


@app.command()
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


@app.command()
def context() -> None:
    """Show current context information.

    Displays:
        - Context hash
        - Context path
        - Context label
        - Git remote (if applicable)
        - Git branch (if applicable)
    """
    ctx = get_context()

    console.print(f"[bold]Context:[/bold] {ctx.hash}")
    console.print(f"  [dim]Path:[/dim]   {ctx.path}")
    console.print(f"  [dim]Label:[/dim]  {ctx.label}")
    if ctx.remote:
        console.print(f"  [dim]Remote:[/dim] {ctx.remote}")
    if ctx.branch:
        console.print(f"  [dim]Branch:[/dim] {ctx.branch}")


@app.command()
def discover() -> None:
    """Discover services from docker-compose.yml without booking.

    Shows what services would be booked with `portman book --auto`.
    """
    services = discover_services()

    if not services:
        console.print("[yellow]No services discovered from docker-compose.yml[/yellow]")
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


# ============================================================================
# MAINTENANCE COMMANDS
# ============================================================================


@app.command()
def prune(
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be removed"),
    stale_days: int | None = typer.Option(
        None, "--stale", help="Also remove allocations not accessed in N days"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Remove orphaned port allocations.

    Checks if context paths still exist and removes allocations for deleted projects.

    Examples:
        portman prune --dry-run
        portman prune
        portman prune --stale 30
    """
    db = get_db()
    pruner = Pruner(db)

    # Run prune
    result = pruner.prune(dry_run=True)  # Always dry run first

    # Also check stale if requested
    if stale_days:
        stale_result = pruner.prune_stale(days=stale_days, dry_run=True)
        result.removed.extend(stale_result.removed)

    if not result.removed:
        console.print("[green]No orphaned allocations found[/green]")
        return

    # Show what would be removed
    console.print(f"[yellow]Would remove {len(result.removed)} allocation(s):[/yellow]")
    for alloc in result.removed:
        console.print(f"  - {alloc['context_label']}: {alloc['service']} ({alloc['port']})")

    if dry_run:
        console.print("\n[dim]Run without --dry-run to remove.[/dim]")
        return

    # Confirm deletion
    if not force:
        confirm = typer.confirm("Proceed with deletion?")
        if not confirm:
            console.print("[yellow]Cancelled[/yellow]")
            return

    # Actually prune
    result = pruner.prune(dry_run=False)
    if stale_days:
        stale_result = pruner.prune_stale(days=stale_days, dry_run=False)
        result.removed.extend(stale_result.removed)

    console.print(f"[green]Removed {len(result.removed)} allocation(s)[/green]")


@app.command()
def gc() -> None:
    """Alias for `portman prune`. Garbage collect orphaned allocations."""
    prune()


# ============================================================================
# CONFIGURATION COMMANDS
# ============================================================================


@app.command()
def init(
    shell: bool = typer.Option(False, "--shell", help="Output shell integration snippet"),
    direnv: bool = typer.Option(False, "--direnv", help="Output direnv integration snippet"),
) -> None:
    """Initialize portman and show setup instructions.

    Examples:
        portman init
        portman init --direnv
    """
    if direnv:
        console.print("[bold]Add to your .envrc:[/bold]")
        console.print(f"[green]{generate_envrc_content()}[/green]")
        return

    if shell:
        console.print("[bold]Direnv helper function:[/bold]")
        console.print(generate_direnvrc_helper())
        return

    # Default: show setup instructions
    console.print("[bold]Portman Setup[/bold]\n")
    console.print("1. Install direnv if not already installed:")
    console.print("   [dim]brew install direnv  # macOS[/dim]")
    console.print("   [dim]apt install direnv   # Debian/Ubuntu[/dim]\n")
    console.print("2. Add to your project's .envrc:")
    console.print(f"   [green]{generate_envrc_content().strip()}[/green]\n")
    console.print("3. Allow direnv:")
    console.print("   [dim]direnv allow[/dim]\n")
    console.print("4. Done! Ports will be allocated automatically.\n")
    console.print("[dim]Tip: Run 'portman status' to see your allocations[/dim]")


@app.command()
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


# ============================================================================
# ENTRY POINT
# ============================================================================


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
