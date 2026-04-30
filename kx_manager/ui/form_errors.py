# kx_manager/ui/form_errors.py

"""Form validation errors for the Konnaxion Capsule Manager GUI."""

from __future__ import annotations


class FormValidationError(ValueError):
    """Raised when a GUI form payload is invalid."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        self.field = field
        super().__init__(message)


__all__ = [
    "FormValidationError",
]