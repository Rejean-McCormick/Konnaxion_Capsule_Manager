"""Instance state helpers for Konnaxion Agent.

All Konnaxion Instance lifecycle values are imported from the canonical
``InstanceState`` enum. This module owns transition validation and small
state-machine helpers used by lifecycle, API, Manager, and CLI code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from kx_shared.errors import InstanceStateError
from kx_shared.konnaxion_constants import InstanceState


TERMINAL_STATES: Final[frozenset[InstanceState]] = frozenset(
    {
        InstanceState.FAILED,
        InstanceState.SECURITY_BLOCKED,
    }
)

ACTIVE_STATES: Final[frozenset[InstanceState]] = frozenset(
    {
        InstanceState.IMPORTING,
        InstanceState.VERIFYING,
        InstanceState.STARTING,
        InstanceState.RUNNING,
        InstanceState.STOPPING,
        InstanceState.UPDATING,
        InstanceState.ROLLING_BACK,
    }
)

USER_STARTABLE_STATES: Final[frozenset[InstanceState]] = frozenset(
    {
        InstanceState.CREATED,
        InstanceState.READY,
        InstanceState.STOPPED,
        InstanceState.DEGRADED,
    }
)

USER_STOPPABLE_STATES: Final[frozenset[InstanceState]] = frozenset(
    {
        InstanceState.RUNNING,
        InstanceState.DEGRADED,
    }
)

RECOVERABLE_STATES: Final[frozenset[InstanceState]] = frozenset(
    {
        InstanceState.DEGRADED,
        InstanceState.FAILED,
        InstanceState.SECURITY_BLOCKED,
    }
)

ALLOWED_TRANSITIONS: Final[dict[InstanceState, frozenset[InstanceState]]] = {
    InstanceState.CREATED: frozenset(
        {
            InstanceState.IMPORTING,
            InstanceState.VERIFYING,
            InstanceState.READY,
            InstanceState.FAILED,
        }
    ),
    InstanceState.IMPORTING: frozenset(
        {
            InstanceState.VERIFYING,
            InstanceState.READY,
            InstanceState.FAILED,
        }
    ),
    InstanceState.VERIFYING: frozenset(
        {
            InstanceState.READY,
            InstanceState.SECURITY_BLOCKED,
            InstanceState.FAILED,
        }
    ),
    InstanceState.READY: frozenset(
        {
            InstanceState.STARTING,
            InstanceState.UPDATING,
            InstanceState.ROLLING_BACK,
            InstanceState.FAILED,
        }
    ),
    InstanceState.STARTING: frozenset(
        {
            InstanceState.RUNNING,
            InstanceState.DEGRADED,
            InstanceState.SECURITY_BLOCKED,
            InstanceState.FAILED,
        }
    ),
    InstanceState.RUNNING: frozenset(
        {
            InstanceState.STOPPING,
            InstanceState.UPDATING,
            InstanceState.DEGRADED,
            InstanceState.FAILED,
        }
    ),
    InstanceState.STOPPING: frozenset(
        {
            InstanceState.STOPPED,
            InstanceState.DEGRADED,
            InstanceState.FAILED,
        }
    ),
    InstanceState.STOPPED: frozenset(
        {
            InstanceState.STARTING,
            InstanceState.UPDATING,
            InstanceState.ROLLING_BACK,
            InstanceState.READY,
            InstanceState.FAILED,
        }
    ),
    InstanceState.UPDATING: frozenset(
        {
            InstanceState.RUNNING,
            InstanceState.DEGRADED,
            InstanceState.ROLLING_BACK,
            InstanceState.FAILED,
        }
    ),
    InstanceState.ROLLING_BACK: frozenset(
        {
            InstanceState.RUNNING,
            InstanceState.STOPPED,
            InstanceState.DEGRADED,
            InstanceState.FAILED,
        }
    ),
    InstanceState.DEGRADED: frozenset(
        {
            InstanceState.STARTING,
            InstanceState.STOPPING,
            InstanceState.UPDATING,
            InstanceState.ROLLING_BACK,
            InstanceState.RUNNING,
            InstanceState.STOPPED,
            InstanceState.FAILED,
        }
    ),
    InstanceState.FAILED: frozenset(
        {
            InstanceState.VERIFYING,
            InstanceState.ROLLING_BACK,
            InstanceState.STOPPED,
            InstanceState.DEGRADED,
        }
    ),
    InstanceState.SECURITY_BLOCKED: frozenset(
        {
            InstanceState.VERIFYING,
            InstanceState.STOPPED,
            InstanceState.FAILED,
        }
    ),
}


@dataclass(frozen=True)
class InstanceStateSnapshot:
    """Immutable state snapshot suitable for persistence or API responses."""

    instance_id: str
    state: InstanceState
    previous_state: InstanceState | None = None
    reason: str = ""
    updated_at: datetime | None = None

    def as_dict(self) -> dict[str, str | None]:
        """Return a JSON-serializable representation."""

        return {
            "instance_id": self.instance_id,
            "state": self.state.value,
            "previous_state": self.previous_state.value if self.previous_state else None,
            "reason": self.reason,
            "updated_at": self.timestamp.isoformat(),
        }

    @property
    def timestamp(self) -> datetime:
        """Return the snapshot timestamp, generating one if absent."""

        return self.updated_at or datetime.now(UTC)


def parse_instance_state(value: str | InstanceState) -> InstanceState:
    """Parse and validate a canonical Konnaxion Instance state."""

    if isinstance(value, InstanceState):
        return value

    try:
        return InstanceState(value)
    except ValueError as exc:
        valid = ", ".join(state.value for state in InstanceState)
        raise InstanceStateError(
            f"Unknown Konnaxion Instance state: {value!r}. Valid states: {valid}"
        ) from exc


def can_transition(from_state: str | InstanceState, to_state: str | InstanceState) -> bool:
    """Return whether a state transition is allowed."""

    source = parse_instance_state(from_state)
    target = parse_instance_state(to_state)

    if source == target:
        return True

    return target in ALLOWED_TRANSITIONS[source]


def assert_can_transition(
    from_state: str | InstanceState,
    to_state: str | InstanceState,
) -> None:
    """Raise if a state transition is not allowed."""

    source = parse_instance_state(from_state)
    target = parse_instance_state(to_state)

    if not can_transition(source, target):
        allowed = ", ".join(state.value for state in sorted(
            ALLOWED_TRANSITIONS[source],
            key=lambda item: item.value,
        ))
        raise InstanceStateError(
            f"Invalid Konnaxion Instance transition: "
            f"{source.value} -> {target.value}. Allowed: {allowed}"
        )


def transition_instance_state(
    instance_id: str,
    current_state: str | InstanceState,
    next_state: str | InstanceState,
    *,
    reason: str = "",
) -> InstanceStateSnapshot:
    """Validate and build the next state snapshot."""

    source = parse_instance_state(current_state)
    target = parse_instance_state(next_state)
    assert_can_transition(source, target)

    return InstanceStateSnapshot(
        instance_id=instance_id,
        state=target,
        previous_state=source,
        reason=reason,
        updated_at=datetime.now(UTC),
    )


def is_active_state(state: str | InstanceState) -> bool:
    """Return whether the instance is in an active lifecycle state."""

    return parse_instance_state(state) in ACTIVE_STATES


def is_terminal_state(state: str | InstanceState) -> bool:
    """Return whether the instance is in a terminal blocking state."""

    return parse_instance_state(state) in TERMINAL_STATES


def is_user_startable_state(state: str | InstanceState) -> bool:
    """Return whether an operator may request start from this state."""

    return parse_instance_state(state) in USER_STARTABLE_STATES


def is_user_stoppable_state(state: str | InstanceState) -> bool:
    """Return whether an operator may request stop from this state."""

    return parse_instance_state(state) in USER_STOPPABLE_STATES


def is_recoverable_state(state: str | InstanceState) -> bool:
    """Return whether recovery, verification, or rollback may be attempted."""

    return parse_instance_state(state) in RECOVERABLE_STATES


def require_user_startable(state: str | InstanceState) -> None:
    """Raise unless an operator may start from this state."""

    parsed = parse_instance_state(state)
    if parsed not in USER_STARTABLE_STATES:
        allowed = ", ".join(sorted(item.value for item in USER_STARTABLE_STATES))
        raise InstanceStateError(
            f"Cannot start Konnaxion Instance from state {parsed.value}. "
            f"Allowed states: {allowed}"
        )


def require_user_stoppable(state: str | InstanceState) -> None:
    """Raise unless an operator may stop from this state."""

    parsed = parse_instance_state(state)
    if parsed not in USER_STOPPABLE_STATES:
        allowed = ", ".join(sorted(item.value for item in USER_STOPPABLE_STATES))
        raise InstanceStateError(
            f"Cannot stop Konnaxion Instance from state {parsed.value}. "
            f"Allowed states: {allowed}"
        )


def initial_instance_state() -> InstanceState:
    """Return the canonical initial Konnaxion Instance state."""

    return InstanceState.CREATED
