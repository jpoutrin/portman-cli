"""Tests for context module."""

from pathlib import Path

from portman.context import _extract_repo_name, get_context


def test_context_from_git_repo(mock_git_repo):
    """Test context generation from git repository."""
    ctx = get_context(mock_git_repo)

    assert ctx.hash is not None
    assert len(ctx.hash) == 12
    assert ctx.remote == "git@github.com:test/repo.git"
    assert ctx.branch == "main"
    assert "repo" in ctx.label
    # Use resolve() to handle symlinks on macOS (/var vs /private/var)
    assert Path(ctx.path).resolve() == mock_git_repo.resolve()


def test_context_from_plain_directory(temp_dir):
    """Test context generation from non-git directory."""
    ctx = get_context(temp_dir)

    assert ctx.hash is not None
    assert len(ctx.hash) == 12
    assert ctx.remote is None
    assert ctx.branch is None
    # Use resolve() to handle symlinks on macOS (/var vs /private/var)
    assert Path(ctx.path).resolve() == temp_dir.resolve()


def test_context_hash_stability(mock_git_repo):
    """Test that context hash is stable across calls."""
    ctx1 = get_context(mock_git_repo)
    ctx2 = get_context(mock_git_repo)

    assert ctx1.hash == ctx2.hash


def test_context_different_paths_different_hashes(temp_dir):
    """Test that different paths produce different hashes."""
    dir1 = temp_dir / "dir1"
    dir2 = temp_dir / "dir2"
    dir1.mkdir()
    dir2.mkdir()

    ctx1 = get_context(dir1)
    ctx2 = get_context(dir2)

    assert ctx1.hash != ctx2.hash


def test_extract_repo_name():
    """Test extracting repository name from various URL formats."""
    # SSH format
    assert _extract_repo_name("git@github.com:user/repo.git") == "repo"
    assert _extract_repo_name("git@github.com:user/my-project.git") == "my-project"

    # HTTPS format
    assert _extract_repo_name("https://github.com/user/repo.git") == "repo"
    assert _extract_repo_name("https://github.com/user/repo") == "repo"

    # With trailing slash
    assert _extract_repo_name("https://github.com/user/repo/") == "repo"
