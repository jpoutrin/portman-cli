"""Helpers for tracking Docker volumes."""

from pathlib import Path
from typing import Any

from .context import Context
from .db import Database
from .discovery import DiscoveredVolume, is_portman_volume_name
from .system import DockerInspector


def sync_discovered_volumes(
    db: Database,
    ctx: Context,
    volumes: list[DiscoveredVolume],
) -> None:
    """Upsert discovered volumes into the registry."""
    for volume in volumes:
        db.upsert_tracked_volume(
            context_hash=ctx.hash,
            context_path=ctx.path,
            context_label=ctx.label,
            service=volume.service,
            compose_file=volume.source,
            compose_volume_key=volume.compose_volume_key,
            docker_volume_name=volume.docker_volume_name,
            source_mount=volume.source_mount,
            owner=volume.owner,
            ownership_token=volume.ownership_token,
        )


def resolve_volume_status(volume: dict[str, Any], inspector: DockerInspector | None) -> str:
    """Resolve the human-readable status for a tracked volume."""
    if inspector is None or not inspector.is_docker_available():
        return "unknown"

    exists = inspector.inspect_volume(volume["docker_volume_name"]) is not None
    context_exists = Path(volume["context_path"]).exists()

    if exists and not context_exists:
        return "orphaned"
    if exists:
        return "present"
    if context_exists:
        return "uncreated"
    return "missing"


def can_safely_delete_tracked_volume(volume: dict[str, Any]) -> bool:
    """Return True when the tracked volume is Portman-owned and safe to delete."""
    return volume["owner"] == "portman" and is_portman_volume_name(volume["docker_volume_name"])
