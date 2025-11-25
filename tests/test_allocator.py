"""Tests for allocator module."""

import pytest

from portman.allocator import PortAllocationError, PortAllocator


def test_allocate_new_port(mock_db):
    """Test allocating a new port."""
    allocator = PortAllocator(mock_db)

    port = allocator.allocate("postgres", "test-context")

    # Should be in postgres range
    assert 5432 <= port <= 5499


def test_allocate_returns_existing(mock_db):
    """Test that allocating same service twice returns existing port."""
    allocator = PortAllocator(mock_db)

    # First allocation
    port1 = allocator.allocate("postgres", "test-context")
    mock_db.create_allocation(
        context_hash="test-context",
        context_path="/test/path",
        context_label="test",
        service="postgres",
        port=port1,
    )

    # Second allocation should return same port
    port2 = allocator.allocate("postgres", "test-context")

    assert port1 == port2


def test_allocate_different_contexts(mock_db):
    """Test that different contexts get different ports."""
    allocator = PortAllocator(mock_db)

    port1 = allocator.allocate("postgres", "context-1")
    mock_db.create_allocation(
        context_hash="context-1",
        context_path="/path1",
        context_label="test1",
        service="postgres",
        port=port1,
    )

    port2 = allocator.allocate("postgres", "context-2")

    assert port1 != port2


def test_allocate_with_preferred_port(mock_db):
    """Test allocating with a preferred port."""
    allocator = PortAllocator(mock_db)

    port = allocator.allocate("postgres", "test-context", preferred_port=5450)

    assert port == 5450


def test_allocate_preferred_port_unavailable(mock_db):
    """Test that unavailable preferred port is skipped."""
    allocator = PortAllocator(mock_db)

    # Allocate a port first
    mock_db.create_allocation(
        context_hash="other-context",
        context_path="/other",
        context_label="other",
        service="redis",
        port=5450,
    )

    # Try to use 5450 as preferred (should skip it)
    port = allocator.allocate("postgres", "test-context", preferred_port=5450)

    # Should allocate different port
    assert port != 5450
    assert 5432 <= port <= 5499


def test_allocate_fallback_to_default_range(mock_db):
    """Test allocation falls back to default range when service range exhausted."""
    allocator = PortAllocator(mock_db)

    # Fill up a small custom range
    mock_db.set_port_range("test-service", 7000, 7002)

    # Allocate all ports in range
    for i, ctx in enumerate(["ctx1", "ctx2", "ctx3"]):
        port = allocator.allocate("test-service", ctx)
        mock_db.create_allocation(
            context_hash=ctx,
            context_path=f"/path{i}",
            context_label=f"test{i}",
            service="test-service",
            port=port,
        )

    # Next allocation should use default range
    port = allocator.allocate("test-service", "ctx4")
    assert 10000 <= port <= 19999


def test_allocate_skips_system_ports(mock_db):
    """Test that allocator skips ports in use by system."""
    allocator = PortAllocator(mock_db)

    # Mock system scanner to return specific ports
    class MockScanner:
        def get_listening_ports(self):
            return {5432, 5433, 5434}

        def is_port_bindable(self, port):
            return port not in {5432, 5433, 5434}

    allocator.system = MockScanner()

    # Should skip 5432-5434 and allocate 5435
    port = allocator.allocate("postgres", "test-context")
    assert port == 5435


def test_allocate_no_available_ports_raises_error(mock_db):
    """Test that allocation fails when no ports available."""
    allocator = PortAllocator(mock_db)

    # Create a very small range
    mock_db.set_port_range("test-service", 7000, 7001)

    # Fill it up
    mock_db.create_allocation(
        context_hash="ctx1",
        context_path="/path1",
        context_label="test1",
        service="test-service",
        port=7000,
    )
    mock_db.create_allocation(
        context_hash="ctx2",
        context_path="/path2",
        context_label="test2",
        service="test-service",
        port=7001,
    )

    # Mock system to make all default range ports unavailable too
    class MockScanner:
        def get_listening_ports(self):
            return set(range(10000, 20000))

        def is_port_bindable(self, port):
            return False

    allocator.system = MockScanner()

    # Should raise error
    with pytest.raises(PortAllocationError):
        allocator.allocate("test-service", "ctx3")
