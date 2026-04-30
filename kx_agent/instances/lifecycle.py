"""
Konnaxion Instance lifecycle state machine.

This module owns the valid high-level lifecycle transitions for a
Konnaxion Instance. It does not run Docker, mutate firewall rules, create
backups, or write runtime files directly. Those operations belong to the
Agent action layer and runtime modules.

The purpose of this module is to keep every coded file aligned on the
same canonical instance states and transition rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Iterable

from kx_shared.konnaxion_constants import InstanceState, SecurityGateStatus


class LifecycleError(RuntimeError):
    """Base error for lifecycle state-machine failures."""


class InvalidLifecycleTransition(LifecycleError):
    """Raised when a requested state transition is not allowed."""

    def __init__(
        self,
        *,
        current_state: InstanceState,
        requested_state: InstanceState,
        reason: str | None = None,
    ) -> None:
        self.current_state = current_state
        self.requested_state = requested_state
        self.reason = reason or (
            f"Cannot transition Konnaxion Instance from "
            f"{current_state.value!r} to {requested_state.value!r}."
        )
        super().__init__(self.reason)


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    """A single state transition event."""

    instance_id: str
    from_state: InstanceState
    to_state: InstanceState
    reason: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class LifecycleResult:
    """Result returned after a lifecycle transition."""

    instance_id: str
    previous_state: InstanceState
    current_state: InstanceState
    changed: bool
    reason: str
    event: LifecycleEvent | None = None


# Canonical allowed state transitions.
#
# Terminal or intervention states such as FAILED, DEGRADED, and
# SECURITY_BLOCKED may move back into a recovery path only through
# explicit Agent actions.
ALLOWED_TRANSITIONS: dict[InstanceState, frozenset[InstanceState]] = {
    InstanceState.CREATED: frozenset({
        InstanceState.IMPORTING,
        InstanceState.VERIFYING,
        InstanceState.READY,
        InstanceState.FAILED,
    }),
    InstanceState.IMPORTING: frozenset({
        InstanceState.VERIFYING,
        InstanceState.READY,
        InstanceState.FAILED,
    }),
    InstanceState.VERIFYING: frozenset({
        InstanceState.READY,
        InstanceState.SECURITY_BLOCKED,
        InstanceState.FAILED,
    }),
    InstanceState.READY: frozenset({
        InstanceState.STARTING,
        InstanceState.UPDATING,
        InstanceState.STOPPED,
        InstanceState.FAILED,
        InstanceState.SECURITY_BLOCKED,
    }),
    InstanceState.STARTING: frozenset({
        InstanceState.RUNNING,
        InstanceState.DEGRADED,
        InstanceState.FAILED,
        InstanceState.SECURITY_BLOCKED,
    }),
    InstanceState.RUNNING: frozenset({
        InstanceState.STOPPING,
        InstanceState.UPDATING,
        InstanceState.DEGRADED,
        InstanceState.FAILED,
        InstanceState.ROLLING_BACK,
    }),
    InstanceState.STOPPING: frozenset({
        InstanceState.STOPPED,
        InstanceState.FAILED,
    }),
    InstanceState.STOPPED: frozenset({
        InstanceState.STARTING,
        InstanceState.UPDATING,
        InstanceState.ROLLING_BACK,
        InstanceState.FAILED,
        InstanceState.SECURITY_BLOCKED,
    }),
    InstanceState.UPDATING: frozenset({
        InstanceState.RUNNING,
        InstanceState.STOPPED,
        InstanceState.DEGRADED,
        InstanceState.ROLLING_BACK,
        InstanceState.FAILED,
        InstanceState.SECURITY_BLOCKED,
    }),
    InstanceState.ROLLING_BACK: frozenset({
        InstanceState.RUNNING,
        InstanceState.STOPPED,
        InstanceState.DEGRADED,
        InstanceState.FAILED,
        InstanceState.SECURITY_BLOCKED,
    }),
    InstanceState.DEGRADED: frozenset({
        InstanceState.RUNNING,
        InstanceState.STOPPING,
        InstanceState.UPDATING,
        InstanceState.ROLLING_BACK,
        InstanceState.FAILED,
        InstanceState.SECURITY_BLOCKED,
    }),
    InstanceState.FAILED: frozenset({
        InstanceState.STOPPED,
        InstanceState.UPDATING,
        InstanceState.ROLLING_BACK,
        InstanceState.VERIFYING,
    }),
    InstanceState.SECURITY_BLOCKED: frozenset({
        InstanceState.VERIFYING,
        InstanceState.STOPPED,
        InstanceState.FAILED,
    }),
}


STARTABLE_STATES = frozenset({
    InstanceState.READY,
    InstanceState.STOPPED,
})

STOPPABLE_STATES = frozenset({
    InstanceState.RUNNING,
    InstanceState.DEGRADED,
    InstanceState.STARTING,
})

UPDATABLE_STATES = frozenset({
    InstanceState.READY,
    InstanceState.RUNNING,
    InstanceState.STOPPED,
    InstanceState.DEGRADED,
    InstanceState.FAILED,
})

ROLLBACKABLE_STATES = frozenset({
    InstanceState.RUNNING,
    InstanceState.STOPPED,
    InstanceState.DEGRADED,
    InstanceState.FAILED,
    InstanceState.UPDATING,
})

RECOVERABLE_STATES = frozenset({
    InstanceState.DEGRADED,
    InstanceState.FAILED,
    InstanceState.SECURITY_BLOCKED,
})


def normalize_state(value: InstanceState | str) -> InstanceState:
    """Normalize a raw value into a canonical InstanceState."""

    if isinstance(value, InstanceState):
        return value

    try:
        return InstanceState(value)
    except ValueError as exc:
        raise LifecycleError(f"Unknown Konnaxion Instance state: {value!r}") from exc


def allowed_next_states(state: InstanceState | str) -> frozenset[InstanceState]:
    """Return valid next states for a canonical state."""

    return ALLOWED_TRANSITIONS[normalize_state(state)]


def can_transition(
    current_state: InstanceState | str,
    requested_state: InstanceState | str,
) -> bool:
    """Return whether the requested transition is valid."""

    current = normalize_state(current_state)
    requested = normalize_state(requested_state)
    return requested == current or requested in ALLOWED_TRANSITIONS[current]


def require_transition(
    current_state: InstanceState | str,
    requested_state: InstanceState | str,
    *,
    reason: str | None = None,
) -> tuple[InstanceState, InstanceState]:
    """Validate and return normalized transition states."""

    current = normalize_state(current_state)
    requested = normalize_state(requested_state)

    if requested == current:
        return current, requested

    if requested not in ALLOWED_TRANSITIONS[current]:
        raise InvalidLifecycleTransition(
            current_state=current,
            requested_state=requested,
            reason=reason,
        )

    return current, requested


def require_state_in(
    current_state: InstanceState | str,
    allowed_states: Iterable[InstanceState],
    *,
    operation: str,
) -> InstanceState:
    """Validate that an operation is allowed from the current state."""

    current = normalize_state(current_state)
    allowed = frozenset(allowed_states)

    if current not in allowed:
        allowed_values = ", ".join(sorted(state.value for state in allowed))
        raise LifecycleError(
            f"Cannot run {operation!r} while Konnaxion Instance is "
            f"{current.value!r}. Allowed states: {allowed_values}."
        )

    return current


def state_after_security_gate(
    *,
    current_state: InstanceState | str,
    security_status: SecurityGateStatus | str,
) -> InstanceState:
    """Return the next state after a Security Gate result."""

    current = normalize_state(current_state)
    status = (
        security_status
        if isinstance(security_status, SecurityGateStatus)
        else SecurityGateStatus(security_status)
    )

    if status == SecurityGateStatus.FAIL_BLOCKING:
        require_transition(current, InstanceState.SECURITY_BLOCKED)
        return InstanceState.SECURITY_BLOCKED

    if status in {SecurityGateStatus.PASS, SecurityGateStatus.WARN}:
        if can_transition(current, InstanceState.READY):
            return InstanceState.READY
        return current

    if status in {SecurityGateStatus.SKIPPED, SecurityGateStatus.UNKNOWN}:
        if can_transition(current, InstanceState.DEGRADED):
            return InstanceState.DEGRADED
        return current

    return current


class InstanceLifecycle:
    """Mutable lifecycle state helper for a single Konnaxion Instance."""

    def __init__(
        self,
        *,
        instance_id: str,
        state: InstanceState | str = InstanceState.CREATED,
        events: Iterable[LifecycleEvent] | None = None,
    ) -> None:
        if not instance_id.strip():
            raise LifecycleError("instance_id is required.")

        self.instance_id = instance_id.strip()
        self.state = normalize_state(state)
        self.events: list[LifecycleEvent] = list(events or [])

    def transition_to(
        self,
        requested_state: InstanceState | str,
        *,
        reason: str,
    ) -> LifecycleResult:
        """Transition to a new state if allowed."""

        previous, requested = require_transition(self.state, requested_state)

        if previous == requested:
            return LifecycleResult(
                instance_id=self.instance_id,
                previous_state=previous,
                current_state=requested,
                changed=False,
                reason=reason,
                event=None,
            )

        event = LifecycleEvent(
            instance_id=self.instance_id,
            from_state=previous,
            to_state=requested,
            reason=reason,
        )

        self.state = requested
        self.events.append(event)

        return LifecycleResult(
            instance_id=self.instance_id,
            previous_state=previous,
            current_state=requested,
            changed=True,
            reason=reason,
            event=event,
        )

    def mark_importing(self) -> LifecycleResult:
        return self.transition_to(
            InstanceState.IMPORTING,
            reason="Capsule import started.",
        )

    def mark_verifying(self) -> LifecycleResult:
        return self.transition_to(
            InstanceState.VERIFYING,
            reason="Capsule and runtime verification started.",
        )

    def mark_ready(self) -> LifecycleResult:
        return self.transition_to(
            InstanceState.READY,
            reason="Instance is ready to start.",
        )

    def mark_starting(self) -> LifecycleResult:
        require_state_in(self.state, STARTABLE_STATES, operation="instance_start")
        return self.transition_to(
            InstanceState.STARTING,
            reason="Instance startup started.",
        )

    def mark_running(self) -> LifecycleResult:
        return self.transition_to(
            InstanceState.RUNNING,
            reason="Instance is running.",
        )

    def mark_stopping(self) -> LifecycleResult:
        require_state_in(self.state, STOPPABLE_STATES, operation="instance_stop")
        return self.transition_to(
            InstanceState.STOPPING,
            reason="Instance shutdown started.",
        )

    def mark_stopped(self) -> LifecycleResult:
        return self.transition_to(
            InstanceState.STOPPED,
            reason="Instance is stopped.",
        )

    def mark_updating(self) -> LifecycleResult:
        require_state_in(self.state, UPDATABLE_STATES, operation="instance_update")
        return self.transition_to(
            InstanceState.UPDATING,
            reason="Instance update started.",
        )

    def mark_rolling_back(self) -> LifecycleResult:
        require_state_in(self.state, ROLLBACKABLE_STATES, operation="instance_rollback")
        return self.transition_to(
            InstanceState.ROLLING_BACK,
            reason="Instance rollback started.",
        )

    def mark_degraded(self, *, reason: str = "Instance is degraded.") -> LifecycleResult:
        return self.transition_to(InstanceState.DEGRADED, reason=reason)

    def mark_failed(self, *, reason: str = "Instance failed.") -> LifecycleResult:
        return self.transition_to(InstanceState.FAILED, reason=reason)

    def mark_security_blocked(
        self,
        *,
        reason: str = "Instance blocked by Security Gate.",
    ) -> LifecycleResult:
        return self.transition_to(InstanceState.SECURITY_BLOCKED, reason=reason)

    def apply_security_gate_result(
        self,
        security_status: SecurityGateStatus | str,
    ) -> LifecycleResult:
        """Apply a Security Gate result to the lifecycle."""

        next_state = state_after_security_gate(
            current_state=self.state,
            security_status=security_status,
        )

        return self.transition_to(
            next_state,
            reason=f"Security Gate result: {next_state.value}.",
        )

    def to_dict(self) -> dict[str, object]:
        """Serialize lifecycle state for API responses or state files."""

        return {
            "instance_id": self.instance_id,
            "state": self.state.value,
            "events": [
                {
                    "instance_id": event.instance_id,
                    "from_state": event.from_state.value,
                    "to_state": event.to_state.value,
                    "reason": event.reason,
                    "created_at": event.created_at.isoformat(),
                }
                for event in self.events
            ],
        }


__all__ = [
    "ALLOWED_TRANSITIONS",
    "RECOVERABLE_STATES",
    "ROLLBACKABLE_STATES",
    "STARTABLE_STATES",
    "STOPPABLE_STATES",
    "UPDATABLE_STATES",
    "InstanceLifecycle",
    "InvalidLifecycleTransition",
    "LifecycleError",
    "LifecycleEvent",
    "LifecycleResult",
    "allowed_next_states",
    "can_transition",
    "normalize_state",
    "require_state_in",
    "require_transition",
    "state_after_security_gate",
]
