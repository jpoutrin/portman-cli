"""GC command - alias for prune."""

from .prune import prune


def gc() -> None:
    """Alias for `portman prune`. Garbage collect orphaned allocations."""
    prune()
