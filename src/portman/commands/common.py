"""Common utilities for CLI commands."""

from ..console import console, debug, error, error_console, info, success, warning
from ..db import Database

# Re-export console utilities
__all__ = ["console", "error_console", "debug", "info", "success", "warning", "error", "get_db"]


def get_db() -> Database:
    """Get database instance."""
    return Database()
