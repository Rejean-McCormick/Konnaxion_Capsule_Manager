"""
Allowlisted Konnaxion Agent actions.

The Konnaxion Capsule Manager must not execute privileged system operations
directly. It sends a constrained action request to the Konnaxion Agent, and the
Agent dispatches only explicitly registered handlers.

This module intentionally contains the action contract and dispatcher only.
Implementation modules such as runtime.compose, runtime.docker, backups.backup,
network.profiles, and security.gate should register concrete handlers here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Mapping, MutableMapping, Protocol
from uuid import uuid4

from kx_shared.errors import (
    AgentActionNotAllowedError,
    AgentError,
    InvalidVariableError,
    KonnaxionError,
    SecurityGateBlockingError,
    as_error_payload,
)


# ---------------------------------------------------------------------
# Canonical action names
# ---------------------------------------------------------------------


class AgentActionName(StrEnum):
    """Canonical allowlisted Agent actions.

    Public/operator-facing CLI commands may call these indirectly, but these
    are the internal Manager -> Agent action names.
    """

    CAPSULE_VERIFY = "capsule.verify"
    CAPSULE_IMPORT = "capsule.import"

    INSTANCE_CREATE = "instance.create"
    INSTANCE_START = "instance.start"
    INSTANCE_STOP = "instance.stop"
    INSTANCE_STATUS = "instance.status"
    INSTANCE_LOGS = "instance.logs"
    INSTANCE_BACKUP = "instance.backup"
    INSTANCE_RESTORE = "instance.restore"
    INSTANCE_RESTORE_NEW = "instance.restore_new"
    INSTANCE_UPDATE = "instance.update"
    INSTANCE_ROLLBACK = "instance.rollback"
    INSTANCE_HEALTH = "instance.health"

    BACKUP_LIST = "backup.list"
    BACKUP_VERIFY = "backup.verify"
    BACKUP_TEST_RESTORE = "backup.test_restore"

    SECURITY_CHECK = "security.check"

    NETWORK_SET_PROFILE = "network.set_profile"
    NETWORK_DISABLE_PUBLIC = "network.disable_public"
    NETWORK_EXPIRE_TEMPORARY_PUBLIC = "network.expire_temporary_public"


ALLOWLISTED_ACTIONS: frozenset[str] = frozenset(action.value for action in AgentActionName)


# Actions that may mutate runtime state, filesystem state, firewall state, or Docker state.
MUTATING_ACTIONS: frozenset[str] = frozenset(
    {
        AgentActionName.CAPSULE_IMPORT.value,
        AgentActionName.INSTANCE_CREATE.value,
        AgentActionName.INSTANCE_START.value,
        AgentActionName.INSTANCE_STOP.value,
        AgentActionName.INSTANCE_BACKUP.value,
        AgentActionName.INSTANCE_RESTORE.value,
        AgentActionName.INSTANCE_RESTORE_NEW.value,
        AgentActionName.INSTANCE_UPDATE.value,
        AgentActionName.INSTANCE_ROLLBACK.value,
        AgentActionName.NETWORK_SET_PROFILE.value,
        AgentActionName.NETWORK_DISABLE_PUBLIC.value,
        AgentActionName.NETWORK_EXPIRE_TEMPORARY_PUBLIC.value,
    }
)


# Actions that must run, or confirm, Security Gate compliance before completion.
SECURITY_GATED_ACTIONS: frozenset[str] = frozenset(
    {
        AgentActionName.CAPSULE_IMPORT.value,
        AgentActionName.INSTANCE_CREATE.value,
        AgentActionName.INSTANCE_START.value,
        AgentActionName.INSTANCE_UPDATE.value,
        AgentActionName.INSTANCE_RESTORE.value,
        AgentActionName.INSTANCE_RESTORE_NEW.value,
        AgentActionName.INSTANCE_ROLLBACK.value,
        AgentActionName.NETWORK_SET_PROFILE.value,
    }
)


# ---------------------------------------------------------------------
# Action DTOs
# ---------------------------------------------------------------------


class ActionStatus(StrEnum):
    """Stable action lifecycle result values."""

    ACCEPTED = "accepted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    NOT_ALLOWED = "not_allowed"


@dataclass(slots=True, frozen=True)
class ActionRequest:
    """Manager -> Agent action request.

    Attributes:
        action:
            Canonical action name, for example ``instance.start``.
        params:
            Structured action parameters. This must never contain raw shell
            commands from the UI.
        request_id:
            Stable correlation ID for audit logs and client responses.
        actor:
            Authenticated Manager/operator identity, if available.
        dry_run:
            Validate and plan the action without mutating runtime state.
        require_security_gate:
            Whether the dispatcher must enforce Security Gate semantics for
            gated actions.
    """

    action: str
    params: Mapping[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid4()))
    actor: str | None = None
    dry_run: bool = False
    require_security_gate: bool = True

    def normalized_action(self) -> str:
        return self.action.strip().lower().replace("_", ".")

    def is_mutating(self) -> bool:
        return self.normalized_action() in MUTATING_ACTIONS

    def is_security_gated(self) -> bool:
        return self.normalized_action() in SECURITY_GATED_ACTIONS


@dataclass(slots=True, frozen=True)
class ActionResult:
    """Agent -> Manager action result."""

    action: str
    status: ActionStatus
    request_id: str
    message: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)
    error: Mapping[str, Any] | None = None

    @classmethod
    def succeeded(
        cls,
        request: ActionRequest,
        *,
        message: str = "",
        data: Mapping[str, Any] | None = None,
    ) -> "ActionResult":
        return cls(
            action=request.normalized_action(),
            status=ActionStatus.SUCCEEDED,
            request_id=request.request_id,
            message=message,
            data=data or {},
        )

    @classmethod
    def accepted(
        cls,
        request: ActionRequest,
        *,
        message: str = "",
        data: Mapping[str, Any] | None = None,
    ) -> "ActionResult":
        return cls(
            action=request.normalized_action(),
            status=ActionStatus.ACCEPTED,
            request_id=request.request_id,
            message=message,
            data=data or {},
        )

    @classmethod
    def failed(cls, request: ActionRequest, error: BaseException) -> "ActionResult":
        status = ActionStatus.FAILED
        if isinstance(error, AgentActionNotAllowedError):
            status = ActionStatus.NOT_ALLOWED
        elif isinstance(error, SecurityGateBlockingError):
            status = ActionStatus.BLOCKED

        payload = as_error_payload(error)
        return cls(
            action=request.normalized_action(),
            status=status,
            request_id=request.request_id,
            message=payload["message"],
            error=payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "status": self.status.value,
            "request_id": self.request_id,
            "message": self.message,
            "data": dict(self.data),
            "error": dict(self.error) if self.error is not None else None,
        }


# ---------------------------------------------------------------------
# Handler protocol
# ---------------------------------------------------------------------


class AgentActionHandler(Protocol):
    """Callable contract for concrete Agent action handlers."""

    def __call__(self, request: ActionRequest) -> ActionResult:
        ...


PreDispatchHook = Callable[[ActionRequest], None]
PostDispatchHook = Callable[[ActionRequest, ActionResult], None]


# ---------------------------------------------------------------------
# Registry and dispatcher
# ---------------------------------------------------------------------


class AgentActionRegistry:
    """Registry of allowlisted action handlers."""

    def __init__(self) -> None:
        self._handlers: MutableMapping[str, AgentActionHandler] = {}

    def register(self, action: AgentActionName | str, handler: AgentActionHandler) -> None:
        normalized = normalize_action_name(action)

        if normalized not in ALLOWLISTED_ACTIONS:
            raise AgentActionNotAllowedError(
                f"Agent action is not allowlisted: {normalized}",
                {"action": normalized},
            )

        if not callable(handler):
            raise InvalidVariableError(
                "Agent action handler must be callable.",
                {"action": normalized, "handler": repr(handler)},
            )

        self._handlers[normalized] = handler

    def unregister(self, action: AgentActionName | str) -> None:
        self._handlers.pop(normalize_action_name(action), None)

    def get(self, action: AgentActionName | str) -> AgentActionHandler:
        normalized = normalize_action_name(action)

        if normalized not in ALLOWLISTED_ACTIONS:
            raise AgentActionNotAllowedError(
                f"Agent action is not allowlisted: {normalized}",
                {"action": normalized},
            )

        try:
            return self._handlers[normalized]
        except KeyError as exc:
            raise AgentActionNotAllowedError(
                f"Agent action has no registered handler: {normalized}",
                {"action": normalized},
            ) from exc

    def registered_actions(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    def allowlisted_actions(self) -> tuple[str, ...]:
        return tuple(sorted(ALLOWLISTED_ACTIONS))


class ActionDispatcher:
    """Safe dispatcher for Manager -> Agent requests.

    The dispatcher enforces:
    - canonical action names only
    - registered handler only
    - pre-dispatch validation hooks
    - post-dispatch audit hooks
    - structured error payloads

    It does not execute shell commands. Concrete handlers must use controlled
    runtime modules and continue to reject raw UI-provided command strings.
    """

    def __init__(
        self,
        registry: AgentActionRegistry | None = None,
        *,
        pre_hooks: list[PreDispatchHook] | None = None,
        post_hooks: list[PostDispatchHook] | None = None,
        raise_errors: bool = False,
    ) -> None:
        self.registry = registry or AgentActionRegistry()
        self.pre_hooks = pre_hooks or []
        self.post_hooks = post_hooks or []
        self.raise_errors = raise_errors

    def dispatch(self, request: ActionRequest) -> ActionResult:
        normalized_request = normalize_request(request)

        try:
            validate_request(normalized_request)

            for hook in self.pre_hooks:
                hook(normalized_request)

            handler = self.registry.get(normalized_request.action)
            result = handler(normalized_request)

            if result.action != normalized_request.action:
                raise AgentError(
                    "Agent action handler returned mismatched action.",
                    {
                        "requested_action": normalized_request.action,
                        "returned_action": result.action,
                    },
                )

            for hook in self.post_hooks:
                hook(normalized_request, result)

            return result

        except BaseException as exc:
            if self.raise_errors:
                raise

            failed = ActionResult.failed(normalized_request, exc)

            for hook in self.post_hooks:
                try:
                    hook(normalized_request, failed)
                except Exception:
                    # Audit hooks must not mask the original action failure.
                    pass

            return failed


# ---------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------


def normalize_action_name(action: AgentActionName | str) -> str:
    if isinstance(action, AgentActionName):
        return action.value

    if not isinstance(action, str):
        raise InvalidVariableError(
            "Agent action name must be a string.",
            {"action": repr(action), "type": type(action).__name__},
        )

    normalized = action.strip().lower().replace("_", ".")

    if not normalized:
        raise InvalidVariableError("Agent action name is required.", {"action": action})

    return normalized


def normalize_request(request: ActionRequest) -> ActionRequest:
    return ActionRequest(
        action=request.normalized_action(),
        params=dict(request.params),
        request_id=request.request_id,
        actor=request.actor,
        dry_run=request.dry_run,
        require_security_gate=request.require_security_gate,
    )


def validate_request(request: ActionRequest) -> None:
    action = request.normalized_action()

    if action not in ALLOWLISTED_ACTIONS:
        raise AgentActionNotAllowedError(
            f"Agent action is not allowlisted: {action}",
            {"action": action, "allowlisted_actions": sorted(ALLOWLISTED_ACTIONS)},
        )

    if not isinstance(request.params, Mapping):
        raise InvalidVariableError(
            "Agent action params must be a mapping.",
            {"action": action, "params_type": type(request.params).__name__},
        )

    _reject_raw_command_params(action, request.params)


def _reject_raw_command_params(action: str, params: Mapping[str, Any]) -> None:
    """Reject obvious attempts to smuggle shell commands through the API."""

    forbidden_keys = {
        "cmd",
        "command",
        "shell",
        "shell_command",
        "exec",
        "subprocess",
        "script",
        "bash",
        "sh",
        "powershell",
    }

    present = sorted(key for key in params if key.lower() in forbidden_keys)
    if present:
        raise AgentActionNotAllowedError(
            "Raw command parameters are not allowed in Agent action requests.",
            {"action": action, "forbidden_params": present},
        )


# ---------------------------------------------------------------------
# Convenience decorators and default registry
# ---------------------------------------------------------------------


default_registry = AgentActionRegistry()


def register_action(action: AgentActionName | str) -> Callable[[AgentActionHandler], AgentActionHandler]:
    """Register an action handler in the process default registry.

    Example:
        @register_action(AgentActionName.INSTANCE_STATUS)
        def status_handler(request: ActionRequest) -> ActionResult:
            ...
    """

    def decorator(handler: AgentActionHandler) -> AgentActionHandler:
        default_registry.register(action, handler)
        return handler

    return decorator


def make_dispatcher(*, raise_errors: bool = False) -> ActionDispatcher:
    return ActionDispatcher(default_registry, raise_errors=raise_errors)


# ---------------------------------------------------------------------
# Minimal placeholder handlers
# ---------------------------------------------------------------------


def not_implemented_handler(request: ActionRequest) -> ActionResult:
    """Placeholder used until concrete modules register real handlers."""

    raise AgentError(
        "Agent action handler is not implemented yet.",
        {"action": request.normalized_action(), "request_id": request.request_id},
    )


def register_placeholder_handlers(registry: AgentActionRegistry | None = None) -> AgentActionRegistry:
    """Register placeholder handlers for every allowlisted action.

    This is useful during early file-level scaffolding and tests. Production
    startup should replace these handlers with concrete implementations.
    """

    target = registry or default_registry
    for action in AgentActionName:
        target.register(action, not_implemented_handler)
    return target


__all__ = [
    "ALLOWLISTED_ACTIONS",
    "MUTATING_ACTIONS",
    "SECURITY_GATED_ACTIONS",
    "ActionDispatcher",
    "ActionRequest",
    "ActionResult",
    "ActionStatus",
    "AgentActionHandler",
    "AgentActionName",
    "AgentActionRegistry",
    "PostDispatchHook",
    "PreDispatchHook",
    "default_registry",
    "make_dispatcher",
    "normalize_action_name",
    "normalize_request",
    "not_implemented_handler",
    "register_action",
    "register_placeholder_handlers",
    "validate_request",
]
