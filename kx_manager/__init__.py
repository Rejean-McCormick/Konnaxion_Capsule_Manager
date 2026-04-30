"""
Konnaxion Capsule Manager package.

The Manager is the user-facing control layer. It must not execute privileged
Docker, firewall, host-network, or backup operations directly. Those actions
belong to Konnaxion Agent allowlisted APIs.

Manager modules should import canonical product/version/profile values from
this package or from kx_shared.konnaxion_constants.
"""

from __future__ import annotations

from kx_shared.konnaxion_constants import (
    APP_VERSION,
    MANAGER_NAME,
    PARAM_VERSION,
    PRODUCT_NAME,
)


__version__ = APP_VERSION
__param_version__ = PARAM_VERSION
__product_name__ = PRODUCT_NAME
__manager_name__ = MANAGER_NAME


__all__ = [
    "__version__",
    "__param_version__",
    "__product_name__",
    "__manager_name__",
    "APP_VERSION",
    "MANAGER_NAME",
    "PARAM_VERSION",
    "PRODUCT_NAME",
]
