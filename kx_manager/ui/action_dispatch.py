# kx_manager/ui/action_dispatch.py

"""GUI action dispatch orchestration.

This module owns only the public dispatch flow:

- resolve action aliases
- normalize submitted payloads
- reject unknown actions
- select the registered backend handler
- convert expected failures into GuiActionResult

Concrete action handlers live in kx_manager.ui.action_backends.
Shared result models live in kx_manager.ui.action_models.
Utility helpers live in kx_manager.ui.action_helpers.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from kx_manager.client import KonnaxionAgentClientError
from kx_manager.ui.action_backends import ACTION_HANDLERS
from kx_manager.ui.action_helpers import _normalize_payload, _payload_instance_id
from kx_manager.ui.action_models import GuiActionResult, JsonDict
from kx_manager.ui.static import (
    ACTION_ALIASES,
    CONTRACT_ACTIONS,
    KNOWN_ACTIONS,
    normalize_payload_aliases,
)

try:
    from .pages import UiAction
except Exception:  # pragma: no cover - staged build compatibility
    from typing import Any as UiAction  # type: ignore


async def dispatch_gui_action(
    action: UiAction,
    payload: Mapping[str, Any] | None = None,
) -> GuiActionResult:
    """Dispatch one GUI action to its approved backend handler.

    Unknown actions are rejected before any backend call. This keeps the GUI
    layer allowlist-based and prevents arbitrary operation dispatch.
    """

    action_value = _action_value(action)
    canonical_action = ACTION_ALIASES.get(action_value, action_value)
    safe_payload = _prepare_payload(payload)

    if canonical_action not in CONTRACT_ACTIONS:
        return GuiActionResult(
            ok=False,
            action=action_value,
            message=f"Unknown GUI action rejected: {action_value}",
            instance_id=_payload_instance_id(safe_payload),
            data={"known_actions": sorted(CONTRACT_ACTIONS)},
        )

    handler = ACTION_HANDLERS.get(canonical_action)
    if handler is None:
        return GuiActionResult(
            ok=False,
            action=action_value,
            message=f"Known GUI action has no handler: {canonical_action}",
            instance_id=_payload_instance_id(safe_payload),
            data={"known_actions": sorted(CONTRACT_ACTIONS)},
        )

    try:
        result = await handler(canonical_action, safe_payload)
    except ValueError as exc:
        return GuiActionResult(
            ok=False,
            action=action_value,
            message=str(exc),
            instance_id=_payload_instance_id(safe_payload),
        )
    except KonnaxionAgentClientError as exc:
        return GuiActionResult(
            ok=False,
            action=action_value,
            message=str(exc),
            instance_id=_payload_instance_id(safe_payload),
            data={
                "status_code": getattr(exc, "status_code", None),
                "details": getattr(exc, "details", None),
            },
            stderr=str(exc),
            returncode=getattr(exc, "status_code", None),
        )
    except Exception as exc:
        return GuiActionResult(
            ok=False,
            action=action_value,
            message=f"Action failed: {exc}",
            instance_id=_payload_instance_id(safe_payload),
            stderr=str(exc),
        )

    if not isinstance(result, GuiActionResult):
        result = _coerce_handler_result(canonical_action, safe_payload, result)

    if action_value != canonical_action:
        result.action = action_value

    return result


def is_known_gui_action(action: Any) -> bool:
    """Return whether an action is known to the GUI dispatcher."""

    action_value = _action_value(action)

    if action_value in KNOWN_ACTIONS:
        return True

    return ACTION_ALIASES.get(action_value, action_value) in CONTRACT_ACTIONS


def _prepare_payload(payload: Mapping[str, Any] | None) -> JsonDict:
    """Apply static aliases, then dispatcher-level normalization."""

    aliased = normalize_payload_aliases(payload)
    return _normalize_payload(aliased)


def _action_value(action: Any) -> str:
    value = getattr(action, "value", action)
    return str(value).strip()


def _coerce_handler_result(
    action: str,
    payload: Mapping[str, Any],
    result: Any,
) -> GuiActionResult:
    """Defensive adapter for staged branches that return dict-like results."""

    if isinstance(result, Mapping):
        data = dict(result)
        ok = bool(data.pop("ok", True))
        result_action = str(data.pop("action", action))
        message = str(data.pop("message", "Action completed."))
        instance_id = data.pop("instance_id", None) or _payload_instance_id(payload)
        stdout = data.pop("stdout", None)
        stderr = data.pop("stderr", None)
        returncode = data.pop("returncode", None)

        return GuiActionResult(
            ok=ok,
            action=result_action,
            message=message,
            instance_id=str(instance_id) if instance_id not in (None, "") else None,
            data=dict(data.pop("data", data)),
            stdout=None if stdout is None else str(stdout),
            stderr=None if stderr is None else str(stderr),
            returncode=_optional_int(returncode),
        )

    return GuiActionResult(
        ok=True,
        action=action,
        message="Action completed.",
        instance_id=_payload_instance_id(payload),
        data={"result": result},
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "dispatch_gui_action",
    "is_known_gui_action",
]