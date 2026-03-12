"""Tests for database module."""

import sqlite3

import pytest

from portman.db import Database


def test_db_initialization(mock_db):
    """Test database is properly initialized."""
    # Check schema version table exists
    conn = mock_db._get_connection()
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    )
    assert cursor.fetchone() is not None

    # Check allocations table exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='allocations'"
    )
    assert cursor.fetchone() is not None

    # Check port_ranges table exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='port_ranges'"
    )
    assert cursor.fetchone() is not None

    # Check tracked_volumes table exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tracked_volumes'"
    )
    assert cursor.fetchone() is not None


def test_create_allocation(mock_db):
    """Test creating a port allocation."""
    alloc_id = mock_db.create_allocation(
        context_hash="test123",
        context_path="/test/path",
        context_label="test/main",
        service="postgres",
        port=5432,
        container_port=5432,
        env_var="PG_PORT",
        source="docker-compose.yml",
    )

    assert alloc_id > 0

    # Verify allocation exists
    alloc = mock_db.get_allocation("test123", "postgres")
    assert alloc is not None
    assert alloc["port"] == 5432
    assert alloc["service"] == "postgres"


def test_unique_port_constraint(mock_db):
    """Test that ports must be unique."""
    mock_db.create_allocation(
        context_hash="ctx1",
        context_path="/path1",
        context_label="test1",
        service="postgres",
        port=5432,
    )

    # Try to allocate same port to different context
    with pytest.raises(sqlite3.IntegrityError):
        mock_db.create_allocation(
            context_hash="ctx2",
            context_path="/path2",
            context_label="test2",
            service="redis",
            port=5432,  # Same port
        )


def test_unique_context_service_constraint(mock_db):
    """Test that context+service must be unique."""
    mock_db.create_allocation(
        context_hash="ctx1",
        context_path="/path1",
        context_label="test1",
        service="postgres",
        port=5432,
    )

    # Try to allocate same service in same context
    with pytest.raises(sqlite3.IntegrityError):
        mock_db.create_allocation(
            context_hash="ctx1",
            context_path="/path1",
            context_label="test1",
            service="postgres",
            port=5433,  # Different port
        )


def test_get_allocations_by_context(mock_db):
    """Test retrieving all allocations for a context."""
    mock_db.create_allocation(
        context_hash="ctx1",
        context_path="/path1",
        context_label="test1",
        service="postgres",
        port=5432,
    )
    mock_db.create_allocation(
        context_hash="ctx1",
        context_path="/path1",
        context_label="test1",
        service="redis",
        port=6379,
    )
    mock_db.create_allocation(
        context_hash="ctx2",
        context_path="/path2",
        context_label="test2",
        service="postgres",
        port=5433,
    )

    allocs = mock_db.get_allocations_by_context("ctx1")
    assert len(allocs) == 2
    assert {a["service"] for a in allocs} == {"postgres", "redis"}


def test_get_all_allocated_ports(mock_db):
    """Test getting all allocated port numbers."""
    mock_db.create_allocation(
        context_hash="ctx1",
        context_path="/path1",
        context_label="test1",
        service="postgres",
        port=5432,
    )
    mock_db.create_allocation(
        context_hash="ctx2",
        context_path="/path2",
        context_label="test2",
        service="redis",
        port=6379,
    )

    ports = mock_db.get_all_allocated_ports()
    assert ports == {5432, 6379}


def test_delete_allocation(mock_db):
    """Test deleting an allocation."""
    alloc_id = mock_db.create_allocation(
        context_hash="ctx1",
        context_path="/path1",
        context_label="test1",
        service="postgres",
        port=5432,
    )

    mock_db.delete_allocation(alloc_id)

    alloc = mock_db.get_allocation("ctx1", "postgres")
    assert alloc is None


def test_delete_allocations_by_context(mock_db):
    """Test deleting all allocations for a context."""
    mock_db.create_allocation(
        context_hash="ctx1",
        context_path="/path1",
        context_label="test1",
        service="postgres",
        port=5432,
    )
    mock_db.create_allocation(
        context_hash="ctx1",
        context_path="/path1",
        context_label="test1",
        service="redis",
        port=6379,
    )

    count = mock_db.delete_allocations_by_context("ctx1")
    assert count == 2

    allocs = mock_db.get_allocations_by_context("ctx1")
    assert len(allocs) == 0


def test_get_port_range(mock_db):
    """Test getting port ranges."""
    # Test default postgres range
    port_range = mock_db.get_port_range("postgres")
    assert port_range.service == "postgres"
    assert port_range.start == 5432
    assert port_range.end == 5499

    # Test non-existent service falls back to default
    port_range = mock_db.get_port_range("unknown")
    assert port_range.service == "default"
    assert port_range.start == 10000
    assert port_range.end == 19999


def test_set_port_range(mock_db):
    """Test setting custom port range."""
    mock_db.set_port_range("custom", 8000, 8099)

    port_range = mock_db.get_port_range("custom")
    assert port_range.service == "custom"
    assert port_range.start == 8000
    assert port_range.end == 8099

    # Test updating existing range
    mock_db.set_port_range("custom", 9000, 9099)
    port_range = mock_db.get_port_range("custom")
    assert port_range.start == 9000
    assert port_range.end == 9099


def test_db_migrates_v1_to_v2(temp_dir):
    """Test schema migration preserves existing allocations."""
    db_path = temp_dir / "migration.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
        INSERT INTO schema_version VALUES (1);

        CREATE TABLE allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            context_hash TEXT NOT NULL,
            context_path TEXT NOT NULL,
            context_label TEXT,
            service TEXT NOT NULL,
            port INTEGER NOT NULL UNIQUE,
            container_port INTEGER,
            env_var TEXT,
            source TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            last_accessed_at TEXT DEFAULT (datetime('now')),
            UNIQUE(context_hash, service)
        );

        CREATE TABLE port_ranges (
            service TEXT PRIMARY KEY,
            range_start INTEGER NOT NULL,
            range_end INTEGER NOT NULL
        );
        INSERT INTO port_ranges VALUES ('default', 10000, 19999);
        INSERT INTO allocations (context_hash, context_path, context_label, service, port)
        VALUES ('ctx1', '/tmp/test', 'test/main', 'postgres', 5432);
        """
    )
    conn.commit()
    conn.close()

    migrated = Database(db_path)
    allocation = migrated.get_allocation("ctx1", "postgres")
    assert allocation is not None
    assert allocation["port"] == 5432

    conn = migrated._get_connection()
    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == 2
    tracked_volumes = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tracked_volumes'"
    ).fetchone()
    assert tracked_volumes is not None


def test_create_tracked_volume(mock_db):
    """Test creating a tracked volume record."""
    volume_id = mock_db.create_tracked_volume(
        context_hash="ctx1",
        context_path="/path1",
        context_label="test1",
        service="postgres",
        compose_file="/tmp/docker-compose.yml",
        compose_volume_key="postgres_data",
        docker_volume_name="portman_ctx1_postgres_data",
        source_mount="postgres_data:/var/lib/postgresql/data",
        owner="portman",
        ownership_token="token123",
    )

    assert volume_id > 0
    volumes = mock_db.get_tracked_volumes_by_context("ctx1")
    assert len(volumes) == 1
    assert volumes[0]["compose_volume_key"] == "postgres_data"


def test_upsert_tracked_volume_updates_existing_row(mock_db):
    """Test tracked volume upsert refreshes an existing row."""
    first_id = mock_db.upsert_tracked_volume(
        context_hash="ctx1",
        context_path="/path1",
        context_label="test1",
        service="postgres",
        compose_file="/tmp/docker-compose.yml",
        compose_volume_key="postgres_data",
        docker_volume_name="portman_ctx1_postgres_data",
        source_mount="postgres_data:/var/lib/postgresql/data",
        owner="portman",
        ownership_token="token123",
    )

    second_id = mock_db.upsert_tracked_volume(
        context_hash="ctx1",
        context_path="/path2",
        context_label="test2",
        service="postgres",
        compose_file="/tmp/docker-compose.yml",
        compose_volume_key="postgres_data",
        docker_volume_name="portman_ctx1_postgres_data",
        source_mount="postgres_data:/data",
        owner="portman",
        ownership_token="token456",
    )

    assert first_id == second_id
    volume = mock_db.get_tracked_volumes_by_context("ctx1")[0]
    assert volume["context_path"] == "/path2"
    assert volume["source_mount"] == "postgres_data:/data"
    assert volume["ownership_token"] == "token456"


def test_get_stale_tracked_volumes(mock_db, temp_dir):
    """Test stale tracked volume lookup."""
    volume_id = mock_db.create_tracked_volume(
        context_hash="ctx1",
        context_path=str(temp_dir),
        context_label="test1",
        service="postgres",
        compose_file="/tmp/docker-compose.yml",
        compose_volume_key="postgres_data",
        docker_volume_name="portman_ctx1_postgres_data",
        source_mount="postgres_data:/var/lib/postgresql/data",
        owner="portman",
        ownership_token="token123",
    )

    conn = mock_db._get_connection()
    conn.execute(
        """
        UPDATE tracked_volumes
        SET last_accessed_at = datetime('now', '-40 days')
        WHERE id = ?
        """,
        (volume_id,),
    )
    conn.commit()

    stale = mock_db.get_stale_tracked_volumes(days=30)
    assert len(stale) == 1
    assert stale[0]["compose_volume_key"] == "postgres_data"
