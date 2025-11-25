"""Tests for discovery module."""

from portman.discovery import (
    _parse_port_definition,
    discover_services,
    infer_service_type,
)


def test_discover_services_with_compose_file(temp_dir):
    """Test discovering services from docker-compose.yml."""
    compose_content = """
version: '3.8'
services:
  postgres:
    image: postgres:14
    ports:
      - "${PG_PORT}:5432"

  redis:
    image: redis:7
    ports:
      - "6379"

  web:
    image: nginx
    ports:
      - "8080:80"
"""
    compose_path = temp_dir / "docker-compose.yml"
    compose_path.write_text(compose_content)

    services = discover_services(temp_dir)

    assert len(services) == 2

    # Check postgres
    postgres = next(s for s in services if s.name == "postgres")
    assert postgres.container_port == 5432
    assert postgres.env_var == "PG_PORT"

    # Check redis
    redis = next(s for s in services if s.name == "redis")
    assert redis.container_port == 6379
    assert redis.env_var == "REDIS_PORT"


def test_discover_services_no_compose_file(temp_dir):
    """Test discovery with no docker-compose file."""
    services = discover_services(temp_dir)
    assert len(services) == 0


def test_parse_port_definition_env_var_format():
    """Test parsing port definitions with environment variables."""
    # ${VAR}:port format
    result = _parse_port_definition("${PG_PORT}:5432", "postgres")
    assert result is not None
    assert result.name == "postgres"
    assert result.container_port == 5432
    assert result.env_var == "PG_PORT"

    # $VAR:port format
    result = _parse_port_definition("$REDIS_PORT:6379", "redis")
    assert result is not None
    assert result.name == "redis"
    assert result.container_port == 6379
    assert result.env_var == "REDIS_PORT"


def test_parse_port_definition_bare_port():
    """Test parsing bare port definitions."""
    result = _parse_port_definition("5432", "postgres")
    assert result is not None
    assert result.name == "postgres"
    assert result.container_port == 5432
    assert result.env_var == "POSTGRES_PORT"


def test_parse_port_definition_explicit_mapping():
    """Test that explicit port mappings are ignored."""
    result = _parse_port_definition("8080:80", "web")
    assert result is None


def test_parse_port_definition_long_format():
    """Test parsing long format port definitions."""
    port_def = {"published": "${PG_PORT}", "target": 5432}
    result = _parse_port_definition(port_def, "postgres")
    assert result is not None
    assert result.name == "postgres"
    assert result.container_port == 5432
    assert result.env_var == "PG_PORT"

    # Explicit published port should be ignored
    port_def = {"published": 8080, "target": 80}
    result = _parse_port_definition(port_def, "web")
    assert result is None


def test_infer_service_type():
    """Test service type inference."""
    # PostgreSQL
    assert infer_service_type("postgres") == "postgres"
    assert infer_service_type("pg") == "postgres"
    assert infer_service_type("my-postgres-db") == "postgres"
    assert infer_service_type("db", "postgres:14") == "postgres"

    # MySQL
    assert infer_service_type("mysql") == "mysql"
    assert infer_service_type("mariadb") == "mysql"

    # Redis
    assert infer_service_type("redis") == "redis"
    assert infer_service_type("cache", "redis:7") == "redis"

    # MongoDB
    assert infer_service_type("mongo") == "mongodb"
    assert infer_service_type("mongodb") == "mongodb"

    # Unknown
    assert infer_service_type("myapp") == "default"
    assert infer_service_type("unknown-service") == "default"


def test_discover_services_multiple_compose_files(temp_dir):
    """Test that all compose file variants are checked."""
    # Create compose.yml (alternative name)
    compose_content = """
version: '3.8'
services:
  postgres:
    image: postgres:14
    ports:
      - "${PG_PORT}:5432"
"""
    compose_path = temp_dir / "compose.yml"
    compose_path.write_text(compose_content)

    services = discover_services(temp_dir)

    assert len(services) == 1
    assert services[0].name == "postgres"


def test_discover_services_with_custom_compose_file(temp_dir):
    """Test discovering services from a custom compose file."""
    # Create a custom compose file
    compose_content = """
version: '3.8'
services:
  postgres:
    image: postgres:14
    ports:
      - "${PG_PORT}:5432"

  redis:
    image: redis:7
    ports:
      - "6379"
"""
    custom_path = temp_dir / "docker-compose.prod.yml"
    custom_path.write_text(compose_content)

    # Also create a standard compose file (should be ignored)
    standard_content = """
version: '3.8'
services:
  mongodb:
    image: mongo:5
    ports:
      - "27017"
"""
    standard_path = temp_dir / "docker-compose.yml"
    standard_path.write_text(standard_content)

    # Discover with custom file - should only find postgres and redis
    services = discover_services(temp_dir, compose_file="docker-compose.prod.yml")

    assert len(services) == 2
    service_names = {s.name for s in services}
    assert service_names == {"postgres", "redis"}

    # Verify standard file is ignored
    assert "mongodb" not in service_names


def test_discover_services_with_absolute_compose_file(temp_dir):
    """Test discovering services with an absolute path to compose file."""
    compose_content = """
version: '3.8'
services:
  postgres:
    image: postgres:14
    ports:
      - "${PG_PORT}:5432"
"""
    compose_path = temp_dir / "custom-compose.yml"
    compose_path.write_text(compose_content)

    # Use absolute path
    services = discover_services(compose_file=str(compose_path))

    assert len(services) == 1
    assert services[0].name == "postgres"


def test_discover_services_with_nonexistent_compose_file(temp_dir):
    """Test discovering services with nonexistent custom compose file."""
    services = discover_services(temp_dir, compose_file="nonexistent.yml")

    assert len(services) == 0
