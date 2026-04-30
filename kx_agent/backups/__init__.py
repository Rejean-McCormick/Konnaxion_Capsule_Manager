"""
Backup, restore, and rollback package for the Konnaxion Agent.

This package contains instance-scoped backup creation, backup verification,
restore flows, rollback flows, and retention policy enforcement.

Submodules are intentionally not imported eagerly here so the project can
be generated and tested file-by-file without circular imports or missing
module failures during early scaffolding.
"""

__all__ = [
    "backup",
    "restore",
    "rollback",
    "retention",
    "verify",
]
