"""Direnv integration helpers for Portman."""

DIRENV_HELPER = """# Portman helper function for direnv
# Add to ~/.config/direnv/direnvrc

use_portman() {
    eval "$(portman export --auto)"
}
"""

ENVRC_TEMPLATE = """# Portman integration
eval "$(portman export --auto)"
"""


def generate_envrc_content() -> str:
    """Generate recommended .envrc content.

    Returns:
        String content for .envrc file
    """
    return 'eval "$(portman export --auto)"\n'


def generate_direnvrc_helper() -> str:
    """Generate direnvrc helper function.

    Returns:
        String content for direnvrc helper
    """
    return DIRENV_HELPER
