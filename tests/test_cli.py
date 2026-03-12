"""CLI integration tests for volume tracking."""

from importlib import import_module

from typer.testing import CliRunner

from portman.cli import app
from portman.context import Context


runner = CliRunner()


class DockerUnavailable:
    """Stub Docker inspector used by status tests."""

    def is_docker_available(self) -> bool:
        return False


def test_book_auto_tracks_ports_and_volumes(temp_dir, mock_db, monkeypatch):
    """Test auto-booking persists tracked volumes alongside ports."""
    compose_path = temp_dir / "docker-compose.yml"
    compose_path.write_text(
        """
services:
  postgres:
    image: postgres:15
    ports:
      - "${POSTGRES_PORT}:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
volumes:
  postgres_data:
"""
    )

    context = Context(
        hash="abc123def456",
        path=str(temp_dir),
        label="repo/main",
        remote=None,
        branch=None,
    )

    book_module = import_module("portman.commands.book")
    discovery_module = import_module("portman.discovery")

    monkeypatch.setattr(book_module, "get_db", lambda: mock_db)
    monkeypatch.setattr(book_module, "get_context", lambda: context)
    monkeypatch.setattr(discovery_module, "get_context", lambda path=None: context)
    monkeypatch.chdir(temp_dir)

    result = runner.invoke(app, ["book", "--auto"])

    assert result.exit_code == 0
    assert mock_db.get_allocation("abc123def456", "postgres") is not None
    tracked_volumes = mock_db.get_tracked_volumes_by_context("abc123def456")
    assert len(tracked_volumes) == 1
    assert tracked_volumes[0]["docker_volume_name"] == "portman_abc123def456_postgres_data"


def test_export_auto_keeps_shell_output_and_tracks_volumes(temp_dir, mock_db, monkeypatch):
    """Test export still emits shell env vars while tracking volumes."""
    compose_path = temp_dir / "docker-compose.yml"
    compose_path.write_text(
        """
services:
  redis:
    image: redis:7
    ports:
      - "6379"
    volumes:
      - redis_data:/data
volumes:
  redis_data:
"""
    )

    context = Context(
        hash="abc123def456",
        path=str(temp_dir),
        label="repo/main",
        remote=None,
        branch=None,
    )

    export_module = import_module("portman.commands.export")
    discovery_module = import_module("portman.discovery")

    monkeypatch.setattr(export_module, "get_db", lambda: mock_db)
    monkeypatch.setattr(export_module, "get_context", lambda: context)
    monkeypatch.setattr(discovery_module, "get_context", lambda path=None: context)
    monkeypatch.chdir(temp_dir)

    result = runner.invoke(app, ["export", "--auto"])

    assert result.exit_code == 0
    assert "export REDIS_PORT=" in result.stdout
    assert "COMPOSE_PROJECT_NAME=repo-main" in result.stdout
    assert len(mock_db.get_tracked_volumes_by_context("abc123def456")) == 1


def test_status_shows_tracked_volumes(temp_dir, mock_db, monkeypatch):
    """Test status renders the tracked volume table."""
    mock_db.create_tracked_volume(
        context_hash="abc123def456",
        context_path=str(temp_dir),
        context_label="repo/main",
        service="postgres",
        compose_file=str(temp_dir / "docker-compose.yml"),
        compose_volume_key="postgres_data",
        docker_volume_name="portman_abc123def456_postgres_data",
        source_mount="postgres_data:/var/lib/postgresql/data",
        owner="portman",
        ownership_token="token123",
    )

    context = Context(
        hash="abc123def456",
        path=str(temp_dir),
        label="repo/main",
        remote=None,
        branch=None,
    )

    status_module = import_module("portman.commands.status")

    monkeypatch.setattr(status_module, "get_db", lambda: mock_db)
    monkeypatch.setattr(status_module, "get_context", lambda: context)
    monkeypatch.setattr(status_module, "DockerInspector", DockerUnavailable)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "Tracked Volumes" in result.stdout
    assert "postgres_data" in result.stdout
    assert "unknown" in result.stdout
