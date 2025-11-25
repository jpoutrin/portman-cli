"""Test fixtures and configuration."""

import subprocess
import tempfile
from pathlib import Path

import pytest

from portman.db import Database


@pytest.fixture
def temp_dir():
    """Temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_db(temp_dir):
    """Database instance for tests."""
    db_path = temp_dir / "test.db"
    return Database(db_path)


@pytest.fixture
def mock_git_repo(temp_dir):
    """Create a mock git repository for testing."""
    repo_dir = temp_dir / "repo"
    repo_dir.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True, check=True)

    # Add remote
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:test/repo.git"],
        cwd=repo_dir,
        capture_output=True,
        check=True,
    )

    # Create and checkout branch
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_dir,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_dir,
        capture_output=True,
        check=True,
    )

    # Create initial commit
    (repo_dir / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_dir,
        capture_output=True,
        check=True,
    )

    # Create branch
    subprocess.run(
        ["git", "checkout", "-b", "main"],
        cwd=repo_dir,
        capture_output=True,
        check=False,  # May fail if already on main
    )

    return repo_dir
