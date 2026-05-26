"""Shared GUI action models for the Konnaxion Capsule Manager UI."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any


JsonDict = dict[str, Any]


@dataclass(slots=True)
class GuiActionResult:
    """Normalized result returned by all GUI action handlers."""

    ok: bool
    action: str
    message: str
    instance_id: str | None = None
    data: JsonDict = field(default_factory=dict)
    stdout: str | None = None
    stderr: str | None = None
    returncode: int | None = None

    def to_dict(self) -> JsonDict:
        """Return a JSON-safe dictionary representation."""

        return {
            "ok": self.ok,
            "action": self.action,
            "message": self.message,
            "instance_id": self.instance_id,
            "data": json_safe(self.data),
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
        }


GuiActionHandler = Callable[[str, Mapping[str, Any]], Awaitable[GuiActionResult]]


def json_safe(value: Any) -> Any:
    """Convert common Python values into JSON-safe values."""

    if isinstance(value, Path):
        return str(value)

    if hasattr(value, "value"):
        return value.value

    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}

    if isinstance(value, tuple):
        return [json_safe(item) for item in value]

    if isinstance(value, list):
        return [json_safe(item) for item in value]

    if isinstance(value, set):
        return sorted(json_safe(item) for item in value)

    if is_dataclass(value):
        return json_safe(asdict(value))

    return value


__all__ = [
    "GuiActionHandler",
    "GuiActionResult",
    "JsonDict",
    "json_safe",
]