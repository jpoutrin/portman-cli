"""Cleanup logic for orphaned allocations and tracked volumes."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import Database
from .system import DockerInspector
from .volumes import can_safely_delete_tracked_volume


@dataclass
class PruneResult:
    """Result of a prune operation."""

    removed: list[dict[str, Any]]
    kept: list[dict[str, Any]]
    errors: list[str]
    removed_tracked_volumes: list[dict[str, Any]]
    kept_tracked_volumes: list[dict[str, Any]]
    removed_docker_volumes: list[str]
    skipped_tracked_volumes: list[str]


class Pruner:
    """Clean up orphaned allocations and tracked volumes."""

    def __init__(self, db: Database, docker: DockerInspector | None = None) -> None:
        """Initialize pruner."""
        self.db = db
        self.docker = docker or DockerInspector()

    def prune(self, dry_run: bool = False) -> PruneResult:
        """Remove orphaned allocations and tracked volumes."""
        result = PruneResult(
            removed=[],
            kept=[],
            errors=[],
            removed_tracked_volumes=[],
            kept_tracked_volumes=[],
            removed_docker_volumes=[],
            skipped_tracked_volumes=[],
        )

        for alloc in self.db.get_all_allocations():
            try:
                if self._is_orphan(alloc):
                    if not dry_run:
                        self.db.delete_allocation(alloc["id"])
                    result.removed.append(alloc)
                else:
                    result.kept.append(alloc)
            except Exception as exc:
                result.errors.append(f"{alloc['context_label']}: {exc}")

        volume_candidates = [
            volume for volume in self.db.get_all_tracked_volumes() if self._is_orphan(volume)
        ]
        self._prune_tracked_volumes(volume_candidates, result, dry_run=dry_run)
        return result

    def prune_stale(self, days: int = 30, dry_run: bool = False) -> PruneResult:
        """Remove stale allocations and tracked volumes."""
        result = PruneResult(
            removed=[],
            kept=[],
            errors=[],
            removed_tracked_volumes=[],
            kept_tracked_volumes=[],
            removed_docker_volumes=[],
            skipped_tracked_volumes=[],
        )

        for alloc in self.db.get_stale_allocations(days=days):
            if not dry_run:
                self.db.delete_allocation(alloc["id"])
            result.removed.append(alloc)

        volume_candidates = self.db.get_stale_tracked_volumes(days=days)
        self._prune_tracked_volumes(volume_candidates, result, dry_run=dry_run)
        return result

    def _prune_tracked_volumes(
        self,
        candidates: list[dict[str, Any]],
        result: PruneResult,
        *,
        dry_run: bool,
    ) -> None:
        """Prune tracked volumes with safe Docker deletion semantics."""
        docker_available = self.docker.is_docker_available()

        for volume in self.db.get_all_tracked_volumes():
            if volume not in candidates:
                result.kept_tracked_volumes.append(volume)

        for volume in candidates:
            label = volume["docker_volume_name"]

            if not can_safely_delete_tracked_volume(volume):
                result.skipped_tracked_volumes.append(
                    f"{label}: skipped because ownership could not be verified"
                )
                continue

            if not docker_available:
                result.skipped_tracked_volumes.append(
                    f"{label}: skipped because Docker is unavailable"
                )
                continue

            exists_in_docker = self.docker.inspect_volume(label) is not None

            if dry_run:
                result.removed_tracked_volumes.append(volume)
                if exists_in_docker:
                    result.removed_docker_volumes.append(label)
                continue

            if exists_in_docker:
                if not self.docker.remove_volume(label):
                    result.errors.append(f"{label}: failed to delete Docker volume")
                    continue
                result.removed_docker_volumes.append(label)

            self.db.delete_tracked_volume(volume["id"])
            result.removed_tracked_volumes.append(volume)

    def _is_orphan(self, resource: dict[str, Any]) -> bool:
        """Determine if a tracked resource is orphaned."""
        return not Path(resource["context_path"]).exists()
