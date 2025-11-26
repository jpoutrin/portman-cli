"""Init command - setup instructions for portman."""

import typer

from ..direnv import generate_direnvrc_helper, generate_envrc_content
from .common import console


def init(
    shell: bool = typer.Option(False, "--shell", help="Output shell integration snippet"),
    direnv: bool = typer.Option(False, "--direnv", help="Output direnv integration snippet"),
) -> None:
    """Initialize portman and show setup instructions.

    Examples:
        portman init
        portman init --direnv
    """
    if direnv:
        console.print("[bold]Add to your .envrc:[/bold]")
        console.print(f"[green]{generate_envrc_content()}[/green]")
        return

    if shell:
        console.print("[bold]Direnv helper function:[/bold]")
        console.print(generate_direnvrc_helper())
        return

    # Default: show setup instructions
    console.print("[bold]Portman Setup[/bold]\n")
    console.print("1. Install direnv if not already installed:")
    console.print("   [dim]brew install direnv  # macOS[/dim]")
    console.print("   [dim]apt install direnv   # Debian/Ubuntu[/dim]\n")
    console.print("2. Add to your project's .envrc:")
    console.print(f"   [green]{generate_envrc_content().strip()}[/green]\n")
    console.print("3. Allow direnv:")
    console.print("   [dim]direnv allow[/dim]\n")
    console.print("4. Done! Ports will be allocated automatically.\n")
    console.print("[dim]Tip: Run 'portman status' to see your allocations[/dim]")
