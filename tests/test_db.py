"""Tests for database module."""

import sqlite3

import pytest


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
