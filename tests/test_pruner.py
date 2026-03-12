"""Tests for pruner module."""

from portman.pruner import Pruner


def test_prune_removes_orphaned(mock_db, temp_dir):
    """Test that orphaned allocations are removed."""
    # Create allocation for non-existent path
    mock_db.create_allocation(
        context_hash="orphan123",
        context_path="/nonexistent/path",
        context_label="orphan/test",
        service="postgres",
        port=5432,
    )

    pruner = Pruner(mock_db)
    result = pruner.prune()

    assert len(result.removed) == 1
    assert result.removed[0]["context_hash"] == "orphan123"
    assert len(result.errors) == 0


def test_prune_keeps_valid(mock_db, temp_dir):
    """Test that valid allocations are kept."""
    # Create allocation for existing path
    mock_db.create_allocation(
        context_hash="valid123",
        context_path=str(temp_dir),
        context_label="valid/test",
        service="postgres",
        port=5432,
    )

    pruner = Pruner(mock_db)
    result = pruner.prune()

    assert len(result.removed) == 0
    assert len(result.kept) == 1
    assert result.kept[0]["context_hash"] == "valid123"


def test_prune_dry_run(mock_db, temp_dir):
    """Test that dry run doesn't actually delete."""
    # Create orphaned allocation
    mock_db.create_allocation(
        context_hash="orphan123",
        context_path="/nonexistent/path",
        context_label="orphan/test",
        service="postgres",
        port=5432,
    )

    pruner = Pruner(mock_db)
    result = pruner.prune(dry_run=True)

    # Should report what would be removed
    assert len(result.removed) == 1

    # But allocation should still exist
    alloc = mock_db.get_allocation("orphan123", "postgres")
    assert alloc is not None


def test_prune_stale_allocations(mock_db, temp_dir):
    """Test pruning stale allocations."""
    # Create allocation
    alloc_id = mock_db.create_allocation(
        context_hash="stale123",
        context_path=str(temp_dir),
        context_label="stale/test",
        service="postgres",
        port=5432,
    )

    # Manually set last_accessed_at to old date
    conn = mock_db._get_connection()
    conn.execute(
        """
        UPDATE allocations
        SET last_accessed_at = datetime('now', '-40 days')
        WHERE id = ?
        """,
        (alloc_id,),
    )
    conn.commit()

    pruner = Pruner(mock_db)
    result = pruner.prune_stale(days=30)

    assert len(result.removed) == 1
    assert result.removed[0]["context_hash"] == "stale123"


def test_prune_stale_keeps_recent(mock_db, temp_dir):
    """Test that recent allocations are not pruned as stale."""
    # Create allocation (will have current timestamp)
    mock_db.create_allocation(
        context_hash="recent123",
        context_path=str(temp_dir),
        context_label="recent/test",
        service="postgres",
        port=5432,
    )

    pruner = Pruner(mock_db)
    result = pruner.prune_stale(days=30)

    assert len(result.removed) == 0


def test_prune_multiple_allocations(mock_db, temp_dir):
    """Test pruning with mix of orphaned and valid allocations."""
    # Valid allocation
    mock_db.create_allocation(
        context_hash="valid1",
        context_path=str(temp_dir),
        context_label="valid/test",
        service="postgres",
        port=5432,
    )

    # Orphaned allocations
    mock_db.create_allocation(
        context_hash="orphan1",
        context_path="/nonexistent/path1",
        context_label="orphan1/test",
        service="redis",
        port=6379,
    )
    mock_db.create_allocation(
        context_hash="orphan2",
        context_path="/nonexistent/path2",
        context_label="orphan2/test",
        service="postgres",
        port=5433,
    )

    pruner = Pruner(mock_db)
    result = pruner.prune()

    assert len(result.removed) == 2
    assert len(result.kept) == 1
    assert result.kept[0]["context_hash"] == "valid1"


class FakeDockerInspector:
    """Minimal Docker inspector stub for prune tests."""

    def __init__(self, *, available=True, existing=None, removable=None):
        self.available = available
        self.existing = set(existing or [])
        self.removable = set(removable or self.existing)
        self.removed: list[str] = []

    def is_docker_available(self) -> bool:
        return self.available

    def inspect_volume(self, name: str) -> dict | None:
        return {"Name": name} if name in self.existing else None

    def remove_volume(self, name: str) -> bool:
        if name in self.removable:
            self.existing.discard(name)
            self.removed.append(name)
            return True
        return False


def test_prune_removes_portman_owned_tracked_volume(mock_db):
    """Test prune removes Docker volume and registry row when safe."""
    docker_volume_name = "portman_abc123def456_postgres_data"
    mock_db.create_tracked_volume(
        context_hash="abc123def456",
        context_path="/nonexistent/path",
        context_label="orphan/test",
        service="postgres",
        compose_file="/tmp/docker-compose.yml",
        compose_volume_key="postgres_data",
        docker_volume_name=docker_volume_name,
        source_mount="postgres_data:/var/lib/postgresql/data",
        owner="portman",
        ownership_token="token123",
    )

    pruner = Pruner(
        mock_db,
        docker=FakeDockerInspector(existing={docker_volume_name}),
    )
    result = pruner.prune()

    assert result.removed_docker_volumes == [docker_volume_name]
    assert len(result.removed_tracked_volumes) == 1
    assert mock_db.get_all_tracked_volumes() == []


def test_prune_skips_tracked_volume_when_docker_unavailable(mock_db):
    """Test prune skips tracked volume deletion if Docker cannot be reached."""
    mock_db.create_tracked_volume(
        context_hash="abc123def456",
        context_path="/nonexistent/path",
        context_label="orphan/test",
        service="postgres",
        compose_file="/tmp/docker-compose.yml",
        compose_volume_key="postgres_data",
        docker_volume_name="portman_abc123def456_postgres_data",
        source_mount="postgres_data:/var/lib/postgresql/data",
        owner="portman",
        ownership_token="token123",
    )

    pruner = Pruner(mock_db, docker=FakeDockerInspector(available=False))
    result = pruner.prune()

    assert len(result.removed_tracked_volumes) == 0
    assert len(result.skipped_tracked_volumes) == 1
    assert len(mock_db.get_all_tracked_volumes()) == 1


def test_prune_skips_non_portman_volume_name(mock_db):
    """Test prune refuses ambiguous tracked volumes."""
    mock_db.create_tracked_volume(
        context_hash="abc123def456",
        context_path="/nonexistent/path",
        context_label="orphan/test",
        service="postgres",
        compose_file="/tmp/docker-compose.yml",
        compose_volume_key="postgres_data",
        docker_volume_name="shared_postgres_data",
        source_mount="postgres_data:/var/lib/postgresql/data",
        owner="portman",
        ownership_token="token123",
    )

    pruner = Pruner(mock_db, docker=FakeDockerInspector(existing={"shared_postgres_data"}))
    result = pruner.prune()

    assert len(result.removed_tracked_volumes) == 0
    assert len(result.skipped_tracked_volumes) == 1
