"""Context detection and hash generation for Portman."""

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Context:
    """Development context information."""

    hash: str  # 12-char MD5 hash
    path: str  # Absolute path
    label: str  # Human-readable label
    remote: str | None  # Git remote URL
    branch: str | None  # Git branch name


def get_context(path: Path | None = None) -> Context:
    """Generate a unique context for the current directory.

    The context hash is based on:
    1. Git remote origin + current branch (if git repo)
    2. Absolute path (fallback)

    This ensures that the same project on different branches gets
    different port allocations, while being stable if the project
    is moved (for git-based contexts).

    Args:
        path: Path to analyze. Defaults to current working directory.

    Returns:
        Context object with hash and metadata
    """
    path = (path or Path.cwd()).resolve()

    remote = _get_git_remote(path)
    branch = _get_git_branch(path)

    if remote and branch:
        # Hash based on Git identity (stable across moves)
        identity = f"{remote}:{branch}"
        label = f"{_extract_repo_name(remote)}/{branch}"
    else:
        # Fallback: absolute path
        identity = str(path)
        label = path.name

    hash_value = hashlib.md5(identity.encode()).hexdigest()[:12]

    return Context(
        hash=hash_value, path=str(path), label=label, remote=remote, branch=branch
    )


def _get_git_remote(path: Path) -> str | None:
    """Get the URL of the origin remote.

    Args:
        path: Path to git repository

    Returns:
        Remote URL or None if not a git repo or no origin
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None


def _get_git_branch(path: Path) -> str | None:
    """Get the current git branch.

    Args:
        path: Path to git repository

    Returns:
        Branch name or None if not a git repo
    """
    try:
        # Try to get current branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()

        # Fallback for detached HEAD: use worktree directory name
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip()).name
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None


def _extract_repo_name(remote_url: str) -> str:
    """Extract repository name from remote URL.

    Args:
        remote_url: Git remote URL

    Returns:
        Repository name

    Examples:
        git@github.com:user/repo.git -> repo
        https://github.com/user/repo.git -> repo
        https://github.com/user/repo -> repo
    """
    # Get the last part of the URL
    name = remote_url.rstrip("/").split("/")[-1]
    # Remove .git extension if present
    if name.endswith(".git"):
        name = name[:-4]
    return name
