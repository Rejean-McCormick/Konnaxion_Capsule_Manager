"""
Firewall policy and command planning for the Konnaxion Agent.

The Konnaxion Agent owns firewall changes because firewall state affects host
security. This module keeps the firewall model profile-driven, deny-by-default,
and aligned with canonical Konnaxion ports and exposure modes.

Design goals:

- Never expose internal application ports.
- Allow only canonical entry ports for approved profiles.
- Keep public exposure explicit.
- Build auditable command plans before applying changes.
- Avoid arbitrary shell execution.
"""

from __future__ import annotations

import ipaddress
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from kx_shared.konnaxion_constants import (
    ALLOWED_ENTRY_PORTS,
    FORBIDDEN_PUBLIC_PORTS,
    ExposureMode,
    NetworkProfile,
    SecurityGateStatus,
)
from kx_shared.types import InstanceID


DEFAULT_LAN_CIDRS = (
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "fd00::/8",
    "fe80::/10",
)

DEFAULT_LOOPBACK_CIDRS = (
    "127.0.0.0/8",
    "::1/128",
)

UFW_BINARY = "ufw"
IPTABLES_BINARY = "iptables"
NFT_BINARY = "nft"

DEFAULT_COMMAND_TIMEOUT_SECONDS = 30


class FirewallBackend(StrEnum):
    """Supported firewall backends."""

    UFW = "ufw"
    IPTABLES = "iptables"
    NFTABLES = "nftables"
    NONE = "none"


class FirewallRuleAction(StrEnum):
    """Firewall rule action."""

    ALLOW = "allow"
    DENY = "deny"
    REJECT = "reject"
    LIMIT = "limit"


class FirewallProtocol(StrEnum):
    """Firewall protocol."""

    TCP = "tcp"
    UDP = "udp"
    ANY = "any"


@dataclass(frozen=True, slots=True)
class FirewallRule:
    """Declarative firewall rule."""

    action: FirewallRuleAction
    port: int
    protocol: FirewallProtocol = FirewallProtocol.TCP
    source: str | None = None
    comment: str | None = None


@dataclass(frozen=True, slots=True)
class FirewallPolicy:
    """Full firewall policy for one network profile."""

    profile: NetworkProfile
    exposure_mode: ExposureMode
    default_incoming: FirewallRuleAction = FirewallRuleAction.DENY
    default_outgoing: FirewallRuleAction = FirewallRuleAction.ALLOW
    rules: tuple[FirewallRule, ...] = ()
    public_mode_enabled: bool = False
    public_mode_expires_at: str | None = None


@dataclass(frozen=True, slots=True)
class FirewallCommand:
    """One safe firewall command represented as argv, never shell text."""

    argv: tuple[str, ...]
    description: str


@dataclass(frozen=True, slots=True)
class FirewallPlan:
    """Auditable firewall plan before application."""

    backend: FirewallBackend
    policy: FirewallPolicy
    commands: tuple[FirewallCommand, ...]
    warnings: tuple[str, ...] = ()
    blocking_errors: tuple[str, ...] = ()

    @property
    def status(self) -> SecurityGateStatus:
        if self.blocking_errors:
            return SecurityGateStatus.FAIL_BLOCKING
        if self.warnings:
            return SecurityGateStatus.WARN
        return SecurityGateStatus.PASS

    @property
    def can_apply(self) -> bool:
        return not self.blocking_errors and self.backend != FirewallBackend.NONE


@dataclass(frozen=True, slots=True)
class FirewallCommandResult:
    """Result of running one firewall command."""

    command: FirewallCommand
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True, slots=True)
class FirewallApplyResult:
    """Result of applying a firewall plan."""

    plan: FirewallPlan
    results: tuple[FirewallCommandResult, ...]
    applied: bool

    @property
    def ok(self) -> bool:
        return self.applied and all(result.ok for result in self.results)


def detect_firewall_backend() -> FirewallBackend:
    """Detect the preferred host firewall backend."""

    if shutil.which(UFW_BINARY):
        return FirewallBackend.UFW
    if shutil.which(NFT_BINARY):
        return FirewallBackend.NFTABLES
    if shutil.which(IPTABLES_BINARY):
        return FirewallBackend.IPTABLES
    return FirewallBackend.NONE


def validate_port(port: int) -> int:
    """Validate and return a TCP/UDP port."""

    if not isinstance(port, int):
        raise TypeError(f"port must be int, got {type(port).__name__}")
    if port < 1 or port > 65535:
        raise ValueError(f"invalid port: {port}")
    return port


def validate_cidr(cidr: str) -> str:
    """Validate CIDR notation and return normalized string."""

    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError as exc:
        raise ValueError(f"invalid CIDR: {cidr}") from exc
    return str(network)


def validate_rule(rule: FirewallRule) -> None:
    """Validate one firewall rule."""

    validate_port(rule.port)

    if rule.source:
        validate_cidr(rule.source)

    if rule.action == FirewallRuleAction.ALLOW and rule.port in FORBIDDEN_PUBLIC_PORTS:
        raise ValueError(f"forbidden public port cannot be allowed: {rule.port}")


def validate_policy(policy: FirewallPolicy) -> None:
    """Validate a firewall policy before planning or application."""

    if policy.public_mode_enabled and not policy.public_mode_expires_at:
        raise ValueError("public firewall mode requires an expiration timestamp")

    for rule in policy.rules:
        validate_rule(rule)


def is_forbidden_public_port(port: int) -> bool:
    """Return true when a port must never be exposed directly."""

    return validate_port(port) in FORBIDDEN_PUBLIC_PORTS


def assert_no_forbidden_public_ports(rules: Iterable[FirewallRule]) -> None:
    """Raise if any rule allows a forbidden public port."""

    forbidden = sorted(
        {
            rule.port
            for rule in rules
            if rule.action == FirewallRuleAction.ALLOW and is_forbidden_public_port(rule.port)
        }
    )
    if forbidden:
        raise ValueError(f"forbidden public ports in firewall policy: {forbidden}")


def _https_rule(source: str | None = None, comment: str | None = None) -> FirewallRule:
    return FirewallRule(
        action=FirewallRuleAction.ALLOW,
        port=ALLOWED_ENTRY_PORTS["https"],
        protocol=FirewallProtocol.TCP,
        source=source,
        comment=comment,
    )


def _http_redirect_rule(source: str | None = None, comment: str | None = None) -> FirewallRule:
    return FirewallRule(
        action=FirewallRuleAction.ALLOW,
        port=ALLOWED_ENTRY_PORTS["http_redirect"],
        protocol=FirewallProtocol.TCP,
        source=source,
        comment=comment,
    )


def _ssh_restricted_rule(source: str, comment: str | None = None) -> FirewallRule:
    return FirewallRule(
        action=FirewallRuleAction.LIMIT,
        port=ALLOWED_ENTRY_PORTS["ssh_admin_restricted"],
        protocol=FirewallProtocol.TCP,
        source=source,
        comment=comment,
    )


def build_profile_policy(
    profile: NetworkProfile,
    exposure_mode: ExposureMode,
    *,
    public_mode_enabled: bool = False,
    public_mode_expires_at: str | None = None,
    lan_cidrs: Sequence[str] = DEFAULT_LAN_CIDRS,
    admin_cidrs: Sequence[str] = (),
    allow_http_redirect: bool = True,
    allow_restricted_ssh: bool = False,
) -> FirewallPolicy:
    """Build a canonical firewall policy for a Konnaxion network profile."""

    normalized_lan = tuple(validate_cidr(cidr) for cidr in lan_cidrs)
    normalized_admin = tuple(validate_cidr(cidr) for cidr in admin_cidrs)

    rules: list[FirewallRule] = []

    if profile == NetworkProfile.OFFLINE:
        rules = []

    elif profile == NetworkProfile.LOCAL_ONLY:
        # No external entry ports. The app should bind to loopback only.
        rules = []

    elif profile in (NetworkProfile.INTRANET_PRIVATE, NetworkProfile.PRIVATE_TUNNEL):
        for cidr in normalized_lan:
            if allow_http_redirect:
                rules.append(_http_redirect_rule(cidr, "Konnaxion LAN HTTP redirect"))
            rules.append(_https_rule(cidr, "Konnaxion LAN HTTPS"))

    elif profile == NetworkProfile.PUBLIC_TEMPORARY:
        if not public_mode_enabled:
            raise ValueError("public_temporary profile requires public_mode_enabled=true")
        if not public_mode_expires_at:
            raise ValueError("public_temporary profile requires public_mode_expires_at")
        if allow_http_redirect:
            rules.append(_http_redirect_rule(None, "Konnaxion temporary public HTTP redirect"))
        rules.append(_https_rule(None, "Konnaxion temporary public HTTPS"))

    elif profile == NetworkProfile.PUBLIC_VPS:
        if allow_http_redirect:
            rules.append(_http_redirect_rule(None, "Konnaxion public HTTP redirect"))
        rules.append(_https_rule(None, "Konnaxion public HTTPS"))

    else:
        raise ValueError(f"unsupported network profile: {profile}")

    if allow_restricted_ssh:
        if not normalized_admin:
            raise ValueError("restricted SSH requires at least one admin CIDR")
        for cidr in normalized_admin:
            rules.append(_ssh_restricted_rule(cidr, "Konnaxion restricted SSH admin"))

    policy = FirewallPolicy(
        profile=profile,
        exposure_mode=exposure_mode,
        rules=tuple(rules),
        public_mode_enabled=public_mode_enabled,
        public_mode_expires_at=public_mode_expires_at,
    )
    validate_policy(policy)
    assert_no_forbidden_public_ports(policy.rules)
    return policy


def _ufw_rule_to_command(rule: FirewallRule) -> FirewallCommand:
    action = rule.action.value
    protocol = rule.protocol.value

    argv: list[str] = [UFW_BINARY]

    if rule.source:
        argv.extend([action, "from", rule.source, "to", "any", "port", str(rule.port)])
    else:
        argv.extend([action, str(rule.port)])

    if protocol != FirewallProtocol.ANY.value:
        argv.extend(["proto", protocol])

    return FirewallCommand(
        argv=tuple(argv),
        description=rule.comment or f"{action} {rule.port}/{protocol}",
    )


def build_ufw_plan(policy: FirewallPolicy) -> FirewallPlan:
    """Build a UFW command plan from a firewall policy."""

    warnings: list[str] = []
    blocking_errors: list[str] = []

    try:
        validate_policy(policy)
        assert_no_forbidden_public_ports(policy.rules)
    except ValueError as exc:
        blocking_errors.append(str(exc))

    commands: list[FirewallCommand] = [
        FirewallCommand((UFW_BINARY, "--force", "reset"), "Reset UFW rules"),
        FirewallCommand((UFW_BINARY, "default", policy.default_incoming.value, "incoming"), "Set default incoming policy"),
        FirewallCommand((UFW_BINARY, "default", policy.default_outgoing.value, "outgoing"), "Set default outgoing policy"),
    ]

    for rule in policy.rules:
        commands.append(_ufw_rule_to_command(rule))

    commands.append(FirewallCommand((UFW_BINARY, "--force", "enable"), "Enable UFW"))

    return FirewallPlan(
        backend=FirewallBackend.UFW,
        policy=policy,
        commands=tuple(commands),
        warnings=tuple(warnings),
        blocking_errors=tuple(blocking_errors),
    )


def build_firewall_plan(
    policy: FirewallPolicy,
    *,
    backend: FirewallBackend | None = None,
) -> FirewallPlan:
    """Build an auditable firewall command plan."""

    selected_backend = backend or detect_firewall_backend()

    if selected_backend == FirewallBackend.NONE:
        return FirewallPlan(
            backend=FirewallBackend.NONE,
            policy=policy,
            commands=(),
            blocking_errors=("no supported firewall backend found",),
        )

    if selected_backend == FirewallBackend.UFW:
        return build_ufw_plan(policy)

    return FirewallPlan(
        backend=selected_backend,
        policy=policy,
        commands=(),
        blocking_errors=(f"firewall backend not implemented: {selected_backend.value}",),
    )


def run_firewall_command(
    command: FirewallCommand,
    *,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    dry_run: bool = False,
) -> FirewallCommandResult:
    """Run one firewall command without shell expansion."""

    if dry_run:
        return FirewallCommandResult(
            command=command,
            returncode=0,
            stdout="dry-run",
            stderr="",
        )

    completed = subprocess.run(
        command.argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )

    return FirewallCommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def apply_firewall_plan(
    plan: FirewallPlan,
    *,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    dry_run: bool = False,
) -> FirewallApplyResult:
    """Apply a firewall plan command by command.

    The caller should audit the plan and result.
    """

    if not plan.can_apply:
        return FirewallApplyResult(plan=plan, results=(), applied=False)

    results: list[FirewallCommandResult] = []

    for command in plan.commands:
        result = run_firewall_command(
            command,
            timeout_seconds=timeout_seconds,
            dry_run=dry_run,
        )
        results.append(result)
        if not result.ok:
            break

    return FirewallApplyResult(
        plan=plan,
        results=tuple(results),
        applied=bool(results) and all(result.ok for result in results),
    )


def check_firewall_policy(policy: FirewallPolicy) -> tuple[SecurityGateStatus, tuple[str, ...]]:
    """Return Security Gate status and messages for a policy."""

    messages: list[str] = []

    try:
        validate_policy(policy)
        assert_no_forbidden_public_ports(policy.rules)
    except ValueError as exc:
        return SecurityGateStatus.FAIL_BLOCKING, (str(exc),)

    if policy.profile in (NetworkProfile.PUBLIC_TEMPORARY, NetworkProfile.PUBLIC_VPS):
        if policy.exposure_mode not in (ExposureMode.TEMPORARY_TUNNEL, ExposureMode.PUBLIC):
            messages.append(
                f"profile {policy.profile.value} should use public exposure mode, got {policy.exposure_mode.value}"
            )

    if policy.profile in (NetworkProfile.LOCAL_ONLY, NetworkProfile.OFFLINE) and policy.rules:
        return SecurityGateStatus.FAIL_BLOCKING, (
            f"profile {policy.profile.value} must not expose entry ports",
        )

    if messages:
        return SecurityGateStatus.WARN, tuple(messages)

    return SecurityGateStatus.PASS, ()


def summarize_plan(plan: FirewallPlan) -> Mapping[str, object]:
    """Return a JSON-serializable summary of a firewall plan."""

    return {
        "backend": plan.backend.value,
        "profile": plan.policy.profile.value,
        "exposure_mode": plan.policy.exposure_mode.value,
        "public_mode_enabled": plan.policy.public_mode_enabled,
        "public_mode_expires_at": plan.policy.public_mode_expires_at,
        "status": plan.status.value,
        "warnings": list(plan.warnings),
        "blocking_errors": list(plan.blocking_errors),
        "commands": [
            {
                "argv": list(command.argv),
                "description": command.description,
            }
            for command in plan.commands
        ],
        "rules": [
            {
                "action": rule.action.value,
                "port": rule.port,
                "protocol": rule.protocol.value,
                "source": rule.source,
                "comment": rule.comment,
            }
            for rule in plan.policy.rules
        ],
    }


def plan_profile_firewall(
    *,
    profile: NetworkProfile,
    exposure_mode: ExposureMode,
    public_mode_enabled: bool = False,
    public_mode_expires_at: str | None = None,
    lan_cidrs: Sequence[str] = DEFAULT_LAN_CIDRS,
    admin_cidrs: Sequence[str] = (),
    allow_http_redirect: bool = True,
    allow_restricted_ssh: bool = False,
    backend: FirewallBackend | None = None,
) -> FirewallPlan:
    """Build a complete firewall plan directly from profile inputs."""

    policy = build_profile_policy(
        profile,
        exposure_mode,
        public_mode_enabled=public_mode_enabled,
        public_mode_expires_at=public_mode_expires_at,
        lan_cidrs=lan_cidrs,
        admin_cidrs=admin_cidrs,
        allow_http_redirect=allow_http_redirect,
        allow_restricted_ssh=allow_restricted_ssh,
    )
    return build_firewall_plan(policy, backend=backend)


def plan_instance_firewall(
    *,
    instance_id: InstanceID | str,
    profile: NetworkProfile,
    exposure_mode: ExposureMode,
    public_mode_enabled: bool = False,
    public_mode_expires_at: str | None = None,
    lan_cidrs: Sequence[str] = DEFAULT_LAN_CIDRS,
    admin_cidrs: Sequence[str] = (),
    backend: FirewallBackend | None = None,
) -> FirewallPlan:
    """Build a firewall plan for an instance.

    The instance id is included in comments for audit visibility, but firewall
    rules remain host-level because the Agent controls host ingress.
    """

    plan = plan_profile_firewall(
        profile=profile,
        exposure_mode=exposure_mode,
        public_mode_enabled=public_mode_enabled,
        public_mode_expires_at=public_mode_expires_at,
        lan_cidrs=lan_cidrs,
        admin_cidrs=admin_cidrs,
        backend=backend,
    )

    comment_suffix = f" instance={instance_id}"
    updated_rules = tuple(
        FirewallRule(
            action=rule.action,
            port=rule.port,
            protocol=rule.protocol,
            source=rule.source,
            comment=(rule.comment or "Konnaxion rule") + comment_suffix,
        )
        for rule in plan.policy.rules
    )
    updated_policy = FirewallPolicy(
        profile=plan.policy.profile,
        exposure_mode=plan.policy.exposure_mode,
        default_incoming=plan.policy.default_incoming,
        default_outgoing=plan.policy.default_outgoing,
        rules=updated_rules,
        public_mode_enabled=plan.policy.public_mode_enabled,
        public_mode_expires_at=plan.policy.public_mode_expires_at,
    )
    return build_firewall_plan(updated_policy, backend=plan.backend)


__all__ = [
    "DEFAULT_COMMAND_TIMEOUT_SECONDS",
    "DEFAULT_LAN_CIDRS",
    "DEFAULT_LOOPBACK_CIDRS",
    "FirewallApplyResult",
    "FirewallBackend",
    "FirewallCommand",
    "FirewallCommandResult",
    "FirewallPlan",
    "FirewallPolicy",
    "FirewallProtocol",
    "FirewallRule",
    "FirewallRuleAction",
    "IPTABLES_BINARY",
    "NFT_BINARY",
    "UFW_BINARY",
    "apply_firewall_plan",
    "build_firewall_plan",
    "build_profile_policy",
    "build_ufw_plan",
    "check_firewall_policy",
    "detect_firewall_backend",
    "is_forbidden_public_port",
    "plan_instance_firewall",
    "plan_profile_firewall",
    "run_firewall_command",
    "summarize_plan",
    "validate_cidr",
    "validate_policy",
    "validate_port",
    "validate_rule",
]
