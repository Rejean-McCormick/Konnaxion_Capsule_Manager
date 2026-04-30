"""
User interface package for Konnaxion Capsule Manager.

This package contains the Manager UI application, pages, reusable
components, action dispatching, form validation, rendering helpers, and UI
state helpers.

UI code must display human-readable labels while storing canonical
Konnaxion enum values from kx_shared.

Submodules are intentionally not imported eagerly here so the project can
be generated and tested file-by-file without circular imports or missing
module failures during early scaffolding.
"""

__all__ = [
    "app",
    "actions",
    "forms",
    "render",
    "pages",
    "state",
    "components",
    "streamlit_app",
]