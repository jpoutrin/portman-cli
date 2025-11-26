"""Context command - show current context information."""

from ..context import get_context
from .common import console


def context() -> None:
    """Show current context information.

    Displays:
        - Context hash
        - Context path
        - Context label
        - Git remote (if applicable)
        - Git branch (if applicable)
    """
    ctx = get_context()

    console.print(f"[bold]Context:[/bold] {ctx.hash}")
    console.print(f"  [dim]Path:[/dim]   {ctx.path}")
    console.print(f"  [dim]Label:[/dim]  {ctx.label}")
    if ctx.remote:
        console.print(f"  [dim]Remote:[/dim] {ctx.remote}")
    if ctx.branch:
        console.print(f"  [dim]Branch:[/dim] {ctx.branch}")
