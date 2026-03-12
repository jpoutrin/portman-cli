"""Service and volume discovery from docker-compose files."""

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .context import get_context

COMPOSE_FILENAMES = [
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
]


@dataclass
class DiscoveredService:
    """A service discovered from docker-compose."""

    name: str
    container_port: int
    env_var: str | None
    source: str


@dataclass
class DiscoveredVolume:
    """A named Docker volume discovered from docker-compose."""

    service: str | None
    compose_volume_key: str
    docker_volume_name: str
    mount_target: str | None
    source: str
    owner: str
    ownership_token: str
    source_mount: str


def discover_services(
    path: Path | None = None, compose_file: str | None = None
) -> list[DiscoveredService]:
    """Discover services requiring port allocation from docker-compose files."""
    services: list[DiscoveredService] = []

    for resolved_compose_file in _resolve_compose_files(path=path, compose_file=compose_file):
        services.extend(_parse_compose_file(resolved_compose_file)["services"])

    return services


def discover_volumes(
    path: Path | None = None, compose_file: str | None = None
) -> list[DiscoveredVolume]:
    """Discover named Docker volumes from docker-compose files."""
    base_path = (path or Path.cwd()).resolve()
    context_hash = get_context(base_path).hash
    discovered: list[DiscoveredVolume] = []

    for resolved_compose_file in _resolve_compose_files(path=base_path, compose_file=compose_file):
        parsed = _parse_compose_file(resolved_compose_file)
        discovered.extend(
            _build_discovered_volumes(
                compose_path=resolved_compose_file,
                context_hash=context_hash,
                service_mounts=parsed["volume_mounts"],
                declared_volumes=parsed["declared_volumes"],
            )
        )

    return discovered


def build_tracked_volume_name(context_hash: str, compose_volume_key: str) -> str:
    """Build the deterministic Portman-owned Docker volume name."""
    safe_key = re.sub(r"[^a-zA-Z0-9_.-]+", "-", compose_volume_key)
    return f"portman_{context_hash}_{safe_key}"


def build_volume_ownership_token(
    context_hash: str, compose_file: str, compose_volume_key: str
) -> str:
    """Build a stable ownership token for tracked volumes."""
    raw = f"{context_hash}:{compose_file}:{compose_volume_key}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def is_portman_volume_name(name: str) -> bool:
    """Return True when the Docker volume name matches Portman's naming scheme."""
    return bool(re.match(r"^portman_[0-9a-f]{12}_[A-Za-z0-9_.-]+$", name))


def _resolve_compose_files(path: Path | None, compose_file: str | None) -> list[Path]:
    """Resolve compose files to parse."""
    from .console import debug

    base_path = (path or Path.cwd()).resolve()
    resolved_files: list[Path] = []

    debug(f"_resolve_compose_files(path={base_path}, compose_file={compose_file!r})")

    if compose_file:
        compose_path = Path(compose_file)
        if not compose_path.is_absolute():
            compose_path = base_path / compose_path
        if compose_path.exists():
            resolved_files.append(compose_path.resolve())
        return resolved_files

    for filename in COMPOSE_FILENAMES:
        compose_path = base_path / filename
        if compose_path.exists():
            resolved_files.append(compose_path.resolve())

    return resolved_files


def _parse_compose_file(file_path: Path) -> dict[str, Any]:
    """Parse a docker-compose file for services and named volume mounts."""
    services: list[DiscoveredService] = []
    volume_mounts: list[dict[str, Any]] = []
    declared_volumes: set[str] = set()

    try:
        with file_path.open() as handle:
            data = yaml.safe_load(handle)
    except (OSError, yaml.YAMLError):
        return {
            "services": services,
            "volume_mounts": volume_mounts,
            "declared_volumes": declared_volumes,
        }

    if not isinstance(data, dict):
        return {
            "services": services,
            "volume_mounts": volume_mounts,
            "declared_volumes": declared_volumes,
        }

    declared = data.get("volumes", {})
    if isinstance(declared, dict):
        declared_volumes = {key for key in declared if isinstance(key, str)}

    for svc_name, svc_config in data.get("services", {}).items():
        if not isinstance(svc_config, dict):
            continue

        image = svc_config.get("image", "")

        for port_def in svc_config.get("ports", []):
            parsed_service = _parse_port_definition(port_def, svc_name, image)
            if parsed_service:
                parsed_service.source = str(file_path)
                services.append(parsed_service)

        for volume_def in svc_config.get("volumes", []):
            parsed_volume = _parse_volume_definition(volume_def)
            if parsed_volume:
                parsed_volume["service"] = svc_name
                parsed_volume["source"] = str(file_path)
                volume_mounts.append(parsed_volume)

    return {
        "services": services,
        "volume_mounts": volume_mounts,
        "declared_volumes": declared_volumes,
    }


def _build_discovered_volumes(
    *,
    compose_path: Path,
    context_hash: str,
    service_mounts: list[dict[str, Any]],
    declared_volumes: set[str],
) -> list[DiscoveredVolume]:
    """Build discovered volume records from parsed compose mounts."""
    discovered: list[DiscoveredVolume] = []
    referenced_keys = {mount["compose_volume_key"] for mount in service_mounts}
    service_map: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for mount in service_mounts:
        service_map[mount["compose_volume_key"]].append(mount)

    for compose_volume_key in sorted(referenced_keys):
        docker_volume_name = build_tracked_volume_name(context_hash, compose_volume_key)
        ownership_token = build_volume_ownership_token(
            context_hash=context_hash,
            compose_file=str(compose_path),
            compose_volume_key=compose_volume_key,
        )
        for mount in service_map[compose_volume_key]:
            discovered.append(
                DiscoveredVolume(
                    service=mount["service"],
                    compose_volume_key=compose_volume_key,
                    docker_volume_name=docker_volume_name,
                    mount_target=mount.get("mount_target"),
                    source=str(compose_path),
                    owner="portman",
                    ownership_token=ownership_token,
                    source_mount=mount["source_mount"],
                )
            )

    for compose_volume_key in sorted(declared_volumes - referenced_keys):
        discovered.append(
            DiscoveredVolume(
                service=None,
                compose_volume_key=compose_volume_key,
                docker_volume_name=build_tracked_volume_name(context_hash, compose_volume_key),
                mount_target=None,
                source=str(compose_path),
                owner="portman",
                ownership_token=build_volume_ownership_token(
                    context_hash=context_hash,
                    compose_file=str(compose_path),
                    compose_volume_key=compose_volume_key,
                ),
                source_mount=compose_volume_key,
            )
        )

    return discovered


def _parse_port_definition(
    port_def: Any, service_name: str, image: str = ""
) -> DiscoveredService | None:
    """Parse a port definition from docker-compose."""
    if isinstance(port_def, dict):
        published = port_def.get("published")
        target = port_def.get("target")

        if isinstance(published, str) and published.startswith("$"):
            env_var = published.lstrip("${").rstrip("}")
            if ":-" in env_var:
                env_var = env_var.split(":-")[0]
            return DiscoveredService(
                name=service_name,
                container_port=int(target) if target else 0,
                env_var=env_var,
                source="",
            )
        return None

    port_str = str(port_def)

    var_match = re.match(r"^\$\{?(\w+)(?::-[^}]+)?\}?:(\d+)(?:/\w+)?$", port_str)
    if var_match:
        return DiscoveredService(
            name=service_name,
            container_port=int(var_match.group(2)),
            env_var=var_match.group(1),
            source="",
        )

    bare_match = re.match(r"^(\d+)(?:/\w+)?$", port_str)
    if bare_match:
        return DiscoveredService(
            name=service_name,
            container_port=int(bare_match.group(1)),
            env_var=f"{service_name.upper()}_PORT",
            source="",
        )

    return None


def _parse_volume_definition(volume_def: Any) -> dict[str, Any] | None:
    """Parse a named volume mount from docker-compose."""
    if isinstance(volume_def, dict):
        if volume_def.get("type", "volume") != "volume":
            return None

        source = volume_def.get("source")
        target = volume_def.get("target")
        if not isinstance(source, str) or not source or _looks_like_bind_mount(source):
            return None

        return {
            "compose_volume_key": source,
            "mount_target": str(target) if target else None,
            "source_mount": f"{source}:{target}" if target else source,
        }

    if not isinstance(volume_def, str):
        return None

    parts = volume_def.split(":")
    if len(parts) < 2:
        return None

    source = parts[0]
    target = parts[1] if len(parts) >= 2 else None
    if not source or _looks_like_bind_mount(source):
        return None

    return {
        "compose_volume_key": source,
        "mount_target": target,
        "source_mount": volume_def,
    }


def _looks_like_bind_mount(source: str) -> bool:
    """Return True when the mount source looks like a bind mount path."""
    return (
        source.startswith(".")
        or source.startswith("/")
        or source.startswith("~")
        or source.startswith("${")
        or re.match(r"^[A-Za-z]:[\\/]", source) is not None
    )


def infer_service_type(service_name: str, image: str | None = None) -> str:
    """Infer service type from name or image for port range selection."""
    name_lower = service_name.lower()
    image_lower = (image or "").lower()

    mappings: dict[tuple[str, ...], str] = {
        ("postgres", "pg", "psql", "postgresql"): "postgres",
        ("mysql", "mariadb"): "mysql",
        ("redis",): "redis",
        ("mongo", "mongodb"): "mongodb",
        ("elastic", "elasticsearch"): "elasticsearch",
        ("meili", "meilisearch"): "meilisearch",
        ("rabbit", "rabbitmq"): "rabbitmq",
        ("kafka",): "kafka",
    }

    for keywords, service_type in mappings.items():
        for keyword in keywords:
            if keyword in name_lower or keyword in image_lower:
                return service_type

    return "default"
