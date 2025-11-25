"""Service discovery from docker-compose files."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DiscoveredService:
    """A service discovered from docker-compose."""

    name: str  # Service name from docker-compose
    container_port: int  # Internal container port
    env_var: str | None  # Environment variable name (if dynamic)
    source: str  # Source file path


def discover_services(
    path: Path | None = None, compose_file: str | None = None
) -> list[DiscoveredService]:
    """Discover services requiring port allocation from docker-compose files.

    Scans for docker-compose.yml files and extracts services that need
    dynamic port allocation (using environment variables or bare ports).

    Port formats parsed:
    - "8080:80"           → explicit host port, skip
    - "${PG_PORT}:5432"   → environment variable → allocate
    - "$PG_PORT:5432"     → environment variable → allocate
    - "5432"              → bare port → allocate
    - {published: "${PG_PORT}", target: 5432}  → long format with env var

    Args:
        path: Path to search for docker-compose files. Defaults to cwd.
        compose_file: Specific compose file to use. If provided, only this file
                      will be parsed. If not provided, searches for standard names.

    Returns:
        List of discovered services
    """
    path = path or Path.cwd()
    services: list[DiscoveredService] = []

    # If specific compose file provided, use it
    if compose_file:
        compose_path = Path(compose_file)
        if not compose_path.is_absolute():
            compose_path = path / compose_path
        if compose_path.exists():
            services.extend(_parse_compose_file(compose_path))
        return services

    # Otherwise, search for compose files with standard names
    compose_files = [
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    ]

    for filename in compose_files:
        compose_path = path / filename
        if compose_path.exists():
            services.extend(_parse_compose_file(compose_path))

    return services


def _parse_compose_file(file_path: Path) -> list[DiscoveredService]:
    """Parse a docker-compose file for services.

    Args:
        file_path: Path to docker-compose file

    Returns:
        List of discovered services
    """
    services: list[DiscoveredService] = []

    try:
        with open(file_path) as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return services

    if not data or "services" not in data:
        return services

    for svc_name, svc_config in data.get("services", {}).items():
        if not isinstance(svc_config, dict):
            continue

        # Get image for service type inference
        image = svc_config.get("image", "")

        for port_def in svc_config.get("ports", []):
            parsed = _parse_port_definition(port_def, svc_name, image)
            if parsed:
                parsed.source = str(file_path)
                services.append(parsed)

    return services


def _parse_port_definition(
    port_def: Any, service_name: str, image: str = ""
) -> DiscoveredService | None:
    """Parse a port definition from docker-compose.

    Args:
        port_def: Port definition (string or dict)
        service_name: Name of the service
        image: Docker image name (for service type inference)

    Returns:
        DiscoveredService if needs allocation, None otherwise
    """
    if isinstance(port_def, dict):
        # Long format: {published: ..., target: ...}
        published = port_def.get("published")
        target = port_def.get("target")

        if isinstance(published, str) and published.startswith("$"):
            # Environment variable
            env_var = published.lstrip("${").rstrip("}")
            return DiscoveredService(
                name=service_name,
                container_port=int(target) if target else 0,
                env_var=env_var,
                source="",
            )
        # Explicit port, skip
        return None

    # String format
    port_str = str(port_def)

    # Variable format: ${VAR}:5432 or $VAR:5432
    var_match = re.match(r"^\$\{?(\w+)\}?:(\d+)(?:/\w+)?$", port_str)
    if var_match:
        return DiscoveredService(
            name=service_name,
            container_port=int(var_match.group(2)),
            env_var=var_match.group(1),
            source="",
        )

    # Bare port: "5432" or "5432/tcp"
    bare_match = re.match(r"^(\d+)(?:/\w+)?$", port_str)
    if bare_match:
        return DiscoveredService(
            name=service_name,
            container_port=int(bare_match.group(1)),
            env_var=f"{service_name.upper()}_PORT",
            source="",
        )

    # Explicit mapping like "8080:80", skip
    return None


def infer_service_type(service_name: str, image: str | None = None) -> str:
    """Infer service type from name or image for port range selection.

    Args:
        service_name: Name of the service
        image: Docker image name (optional)

    Returns:
        Service type identifier (e.g., "postgres", "redis", "default")
    """
    name_lower = service_name.lower()
    image_lower = (image or "").lower()

    # Service type mappings
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
