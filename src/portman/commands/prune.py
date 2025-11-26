"""Prune command - remove orphaned port allocations."""

import typer

from ..pruner import Pruner
from .common import console, get_db


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
