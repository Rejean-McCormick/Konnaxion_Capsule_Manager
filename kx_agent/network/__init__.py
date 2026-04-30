"""
Network package for Konnaxion Agent.

This package contains the Agent-side network controls for canonical Konnaxion
network profiles and exposure modes.

Expected sibling modules:
- profiles.py  : profile definitions and validation
- exposure.py  : private/LAN/VPN/temporary/public exposure planning
- tunnels.py   : controlled tunnel provider adapters

Keep this package dependency-light. Import concrete implementations from their
modules directly to avoid import cycles during Agent bootstrap.
"""

from __future__ import annotations

from kx_shared.konnaxion_constants import (
    DEFAULT_EXPOSURE_MODE,
    DEFAULT_NETWORK_PROFILE,
    ExposureMode,
    NetworkProfile,
)


__all__ = [
    "DEFAULT_EXPOSURE_MODE",
    "DEFAULT_NETWORK_PROFILE",
    "ExposureMode",
    "NetworkProfile",
]
