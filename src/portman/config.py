"""Configuration management for Portman."""

from pathlib import Path

import platformdirs


def get_data_dir() -> Path:
    """Get the data directory for Portman.

    Returns:
        Path to data directory
    """
    data_dir = Path(platformdirs.user_data_dir("portman", "portman"))
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return data_dir


def get_db_path() -> Path:
    """Get the database file path.

    Returns:
        Path to database file
    """
    return get_data_dir() / "registry.db"


def get_log_path() -> Path:
    """Get the log file path.

    Returns:
        Path to log file
    """
    return get_data_dir() / "portman.log"
