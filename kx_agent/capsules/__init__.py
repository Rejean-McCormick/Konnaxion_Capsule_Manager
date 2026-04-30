"""
Capsule handling package for Konnaxion Agent.

The capsule layer is responsible for importing, validating, and preparing
signed ``.kxcap`` artifacts before they become Konnaxion Instances.

Canonical responsibilities:
- import a Konnaxion Capsule
- read and validate ``manifest.yaml``
- verify checksums
- verify the capsule signature
- reject capsules that contain forbidden secrets or unsafe runtime definitions
"""

from __future__ import annotations

__all__ = [
    "checksums",
    "importer",
    "manifest",
    "signature",
    "verifier",
]
