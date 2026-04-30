"""Constants and canonical enum aliases for Konnaxion Manager UI forms."""

from __future__ import annotations

import os
from pathlib import Path

from kx_shared import konnaxion_constants as kx_constants


NetworkProfile = kx_constants.NetworkProfile
ExposureMode = kx_constants.ExposureMode
DockerService = kx_constants.DockerService

CAPSULE_EXTENSION = getattr(kx_constants, "CAPSULE_EXTENSION", ".kxcap")

DEFAULT_INSTANCE_ID = getattr(
    kx_constants,
    "DEFAULT_INSTANCE_ID",
    "demo-001",
)

DEFAULT_CAPSULE_ID = getattr(
    kx_constants,
    "DEFAULT_CAPSULE_ID",
    "konnaxion-v14-demo-2026.04.30",
)

DEFAULT_CAPSULE_VERSION = getattr(
    kx_constants,
    "DEFAULT_CAPSULE_VERSION",
    "2026.04.30-demo.1",
)

DEFAULT_CHANNEL = getattr(
    kx_constants,
    "DEFAULT_CHANNEL",
    "demo",
)

DEFAULT_RUNTIME_ROOT = os.getenv(
    "KX_ROOT",
    r"C:\mycode\Konnaxion\runtime" if os.name == "nt" else "/opt/konnaxion",
)

DEFAULT_SOURCE_DIR = os.getenv(
    "KX_SOURCE_DIR",
    r"C:\mycode\Konnaxion\Konnaxion" if os.name == "nt" else "",
)

DEFAULT_CAPSULE_OUTPUT_DIR = os.getenv(
    "KX_CAPSULE_OUTPUT_DIR",
    str(Path(DEFAULT_RUNTIME_ROOT) / "capsules"),
)

SAFE_ID_CHARS = set(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "._-"
)

TRUE_VALUES = {
    "1",
    "true",
    "yes",
    "y",
    "on",
    "checked",
}

FALSE_VALUES = {
    "0",
    "false",
    "no",
    "n",
    "off",
    "",
}


__all__ = [
    "CAPSULE_EXTENSION",
    "DEFAULT_CAPSULE_ID",
    "DEFAULT_CAPSULE_OUTPUT_DIR",
    "DEFAULT_CAPSULE_VERSION",
    "DEFAULT_CHANNEL",
    "DEFAULT_INSTANCE_ID",
    "DEFAULT_RUNTIME_ROOT",
    "DEFAULT_SOURCE_DIR",
    "DockerService",
    "ExposureMode",
    "FALSE_VALUES",
    "NetworkProfile",
    "SAFE_ID_CHARS",
    "TRUE_VALUES",
]