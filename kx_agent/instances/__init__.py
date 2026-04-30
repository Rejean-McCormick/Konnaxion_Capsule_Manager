"""
Instance management package for the Konnaxion Agent.

This package contains the canonical Konnaxion Instance model, lifecycle
state machine, generated secret handling, and runtime environment file
writing.

Submodules are intentionally not imported eagerly here so the project can
be generated and tested file-by-file without circular imports or missing
module failures during early scaffolding.
"""

__all__ = [
    "model",
    "state",
    "lifecycle",
    "secrets",
    "env_writer",
]
