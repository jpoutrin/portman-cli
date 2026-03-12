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

    total_candidates = (
        len(result.removed)
        + len(result.removed_tracked_volumes)
        + len(result.removed_docker_volumes)
        + len(result.skipped_tracked_volumes)
    )

    if total_candidates == 0:
        console.print("[green]No orphaned tracked resources found[/green]")
        return

    if result.removed:
        console.print(f"[yellow]Port allocations to remove: {len(result.removed)}[/yellow]")
        for alloc in result.removed:
            console.print(f"  - {alloc['context_label']}: {alloc['service']} ({alloc['port']})")

    if result.removed_tracked_volumes:
        console.print(
            f"[yellow]Tracked volume records to remove: {len(result.removed_tracked_volumes)}[/yellow]"
        )
        for volume in result.removed_tracked_volumes:
            console.print(
                f"  - {volume['context_label']}: {volume['docker_volume_name']}"
                f" ({volume['compose_volume_key']})"
            )

    if result.removed_docker_volumes:
        console.print(f"[yellow]Docker volumes to delete: {len(result.removed_docker_volumes)}[/yellow]")
        for docker_volume in result.removed_docker_volumes:
            console.print(f"  - {docker_volume}")

    if result.skipped_tracked_volumes:
        console.print(f"[yellow]Skipped volume candidates: {len(result.skipped_tracked_volumes)}[/yellow]")
        for message in result.skipped_tracked_volumes:
            console.print(f"  - {message}")

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
        result.removed_tracked_volumes.extend(stale_result.removed_tracked_volumes)
        result.removed_docker_volumes.extend(stale_result.removed_docker_volumes)
        result.skipped_tracked_volumes.extend(stale_result.skipped_tracked_volumes)
        result.errors.extend(stale_result.errors)

    console.print(
        "[green]Removed "
        f"{len(result.removed)} allocation(s), "
        f"{len(result.removed_tracked_volumes)} tracked volume record(s), and "
        f"{len(result.removed_docker_volumes)} Docker volume(s)[/green]"
    )
    for error in result.errors:
        console.print(f"[red]Error:[/red] {error}")
