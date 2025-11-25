"""Cleanup logic for orphaned allocations."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import Database


@dataclass
class PruneResult:
    """Result of a prune operation."""

    removed: list[dict[str, Any]]  # Allocations removed
    kept: list[dict[str, Any]]  # Allocations kept
    errors: list[str]  # Errors encountered


class Pruner:
    """Clean up orphaned port allocations."""

    def __init__(self, db: Database) -> None:
        """Initialize pruner.

        Args:
            db: Database instance
        """
        self.db = db

    def prune(self, dry_run: bool = False) -> PruneResult:
        """Remove allocations whose context no longer exists.

        Checks:
        1. Does the context_path still exist?
        2. If it's a git repo, does the context hash still match?

        Args:
            dry_run: If True, don't delete, just report what would be deleted

        Returns:
            PruneResult with details of operation
        """
        result = PruneResult(removed=[], kept=[], errors=[])

        allocations = self.db.get_all_allocations()

        for alloc in allocations:
            try:
                if self._is_orphan(alloc):
                    if not dry_run:
                        self.db.delete_allocation(alloc["id"])
                    result.removed.append(alloc)
                else:
                    result.kept.append(alloc)
            except Exception as e:
                result.errors.append(f"{alloc['context_label']}: {e}")

        return result

    def prune_stale(self, days: int = 30, dry_run: bool = False) -> PruneResult:
        """Remove allocations not accessed in the last N days.

        Useful for cleaning up old projects even if the directory still exists.

        Args:
            days: Number of days of inactivity
            dry_run: If True, don't delete, just report what would be deleted

        Returns:
            PruneResult with details of operation
        """
        result = PruneResult(removed=[], kept=[], errors=[])

        stale_allocations = self.db.get_stale_allocations(days=days)

        for alloc in stale_allocations:
            if not dry_run:
                self.db.delete_allocation(alloc["id"])
            result.removed.append(alloc)

        return result

    def _is_orphan(self, allocation: dict[str, Any]) -> bool:
        """Determine if an allocation is orphaned.

        An allocation is orphaned if:
        - The context_path no longer exists

        Args:
            allocation: Allocation dict from database

        Returns:
            True if orphaned, False otherwise
        """
        context_path = Path(allocation["context_path"])

        # Path doesn't exist anymore
        if not context_path.exists():
            return True

        # Path exists, keep the allocation
        # Note: We don't check if the hash changed because that would be
        # a different context (e.g., different branch), not an orphan
        return False
