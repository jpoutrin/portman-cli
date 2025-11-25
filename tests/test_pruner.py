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
    alloc_id = mock_db.create_allocation(
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
