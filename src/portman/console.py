"""Console utilities for portman CLI."""

import os
from typing import Any

from rich.console import Console

# Shared console instances
console = Console()
error_console = Console(stderr=True)

# Debug mode - enabled by PORTMAN_DEBUG environment variable
DEBUG = os.getenv("PORTMAN_DEBUG", "").lower() in ("1", "true", "yes")


def debug(message: str, **kwargs: Any) -> None:
    """Print debug message if DEBUG mode is enabled.

    Args:
        message: Message to print
        **kwargs: Additional arguments for console.print
    """
    if DEBUG:
        error_console.print(f"[dim][DEBUG][/dim] {message}", **kwargs)


def info(message: str, **kwargs: Any) -> None:
    """Print info message.

    Args:
        message: Message to print
        **kwargs: Additional arguments for console.print
    """
    console.print(message, **kwargs)


def success(message: str, **kwargs: Any) -> None:
    """Print success message in green.

    Args:
        message: Message to print
        **kwargs: Additional arguments for console.print
    """
    console.print(f"[green]{message}[/green]", **kwargs)


def warning(message: str, **kwargs: Any) -> None:
    """Print warning message in yellow.

    Args:
        message: Message to print
        **kwargs: Additional arguments for console.print
    """
    console.print(f"[yellow]{message}[/yellow]", **kwargs)


def error(message: str, **kwargs: Any) -> None:
    """Print error message in red to stderr.

    Args:
        message: Message to print
        **kwargs: Additional arguments for console.print
    """
    error_console.print(f"[red]Error:[/red] {message}", **kwargs)
