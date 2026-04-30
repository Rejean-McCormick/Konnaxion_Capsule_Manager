"""
Konnaxion Capsule Builder package.

The Builder is responsible for producing signed `.kxcap` artifacts from the
Konnaxion source tree and build outputs.

Builder responsibilities:
- validate source tree
- build/export runtime images
- generate manifest metadata
- calculate checksums
- sign capsules
- verify generated capsules
- produce canonical `.kxcap` files

The Builder must not:
- include real production secrets in a capsule
- mutate local Konnaxion Instance state
- start runtime services
- bypass capsule verification or signing policy
"""

from __future__ import annotations

try:
    from kx_shared.konnaxion_constants import (
        APP_VERSION,
        BUILDER_NAME,
        CAPSULE_EXTENSION,
        DEFAULT_CHANNEL,
        PARAM_VERSION,
    )
except ImportError:  # pragma: no cover - early scaffolding fallback
    APP_VERSION = "v14"
    BUILDER_NAME = "Konnaxion Capsule Builder"
    CAPSULE_EXTENSION = ".kxcap"
    DEFAULT_CHANNEL = "demo"
    PARAM_VERSION = "kx-param-2026.04.30"


__app_name__ = BUILDER_NAME
__app_version__ = APP_VERSION
__param_version__ = PARAM_VERSION
__default_channel__ = DEFAULT_CHANNEL
__capsule_extension__ = CAPSULE_EXTENSION

__all__ = [
    "__app_name__",
    "__app_version__",
    "__param_version__",
    "__default_channel__",
    "__capsule_extension__",
]
