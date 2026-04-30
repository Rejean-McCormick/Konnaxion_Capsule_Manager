"""
Konnaxion canonical CLI package.

The public operator/developer command root is:

    kx

Canonical command groups:
- kx capsule ...
- kx instance ...
- kx backup ...
- kx security ...
- kx network ...

This package should only expose CLI metadata and shared command constants.
Command implementations belong in:
- kx_cli.main
- kx_cli.capsule
- kx_cli.instance
- kx_cli.backup
- kx_cli.security
- kx_cli.network
"""

from __future__ import annotations

try:
    from kx_shared.konnaxion_constants import (
        APP_VERSION,
        CLI_NAME,
        PARAM_VERSION,
        PUBLIC_CLI_COMMANDS,
    )
except ImportError:  # pragma: no cover - early scaffolding fallback
    APP_VERSION = "v14"
    CLI_NAME = "kx"
    PARAM_VERSION = "kx-param-2026.04.30"
    PUBLIC_CLI_COMMANDS = (
        "kx capsule build",
        "kx capsule verify",
        "kx capsule import",
        "kx instance create",
        "kx instance start",
        "kx instance stop",
        "kx instance status",
        "kx instance logs",
        "kx instance backup",
        "kx instance restore",
        "kx instance restore-new",
        "kx instance update",
        "kx instance rollback",
        "kx instance health",
        "kx backup list",
        "kx backup verify",
        "kx backup test-restore",
        "kx security check",
        "kx network set-profile",
    )


__cli_name__ = CLI_NAME
__app_version__ = APP_VERSION
__param_version__ = PARAM_VERSION
__public_commands__ = tuple(PUBLIC_CLI_COMMANDS)


def get_cli_metadata() -> dict[str, object]:
    """Return serializable CLI metadata for version/help output."""
    return {
        "cli_name": __cli_name__,
        "app_version": __app_version__,
        "param_version": __param_version__,
        "public_commands": list(__public_commands__),
    }


__all__ = [
    "__cli_name__",
    "__app_version__",
    "__param_version__",
    "__public_commands__",
    "get_cli_metadata",
]
