"""
Security package for the Konnaxion Agent.

This package contains the Security Gate, security checks, firewall helpers,
port exposure validation, and runtime policy enforcement used before a
Konnaxion Instance can start.

Submodules are intentionally not imported eagerly here so the project can
be generated and tested file-by-file without circular imports or missing
module failures during early scaffolding.
"""

__all__ = [
    "gate",
    "checks",
    "firewall",
    "ports",
    "policies",
]
