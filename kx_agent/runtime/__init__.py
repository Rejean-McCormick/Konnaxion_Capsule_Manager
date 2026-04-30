"""
Runtime control package for Konnaxion Agent.

The runtime layer owns the Docker Compose execution boundary for a
Konnaxion Instance. It must use canonical Konnaxion service names, paths,
ports, routes, profiles, and environment values from ``kx_shared``.

Canonical responsibilities:
- render the runtime Docker Compose file
- start and stop approved Compose services
- run Django migrations as a controlled lifecycle step
- execute healthchecks
- collect runtime logs
- prevent direct exposure of internal services
"""

from __future__ import annotations

__all__ = [
    "compose",
    "docker",
    "healthchecks",
    "logs",
    "migrations",
]
