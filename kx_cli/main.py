"""
Canonical Konnaxion CLI entrypoint.

The public operator command is:

    kx

Canonical command groups:
- kx capsule build
- kx capsule verify
- kx capsule import
- kx instance create
- kx instance start
- kx instance stop
- kx instance status
- kx instance logs
- kx instance backup
- kx instance restore
- kx instance restore-new
- kx instance update
- kx instance rollback
- kx instance health
- kx backup list
- kx backup verify
- kx backup test-restore
- kx security check
- kx network set-profile

This module is intentionally dependency-light. It uses argparse and delegates
actual work to focused modules:
- kx_cli.capsule
- kx_cli.instance
- kx_cli.backup
- kx_cli.security
- kx_cli.network
- kx_builder.main for developer-side capsule build/verify fallback

The CLI must not perform privileged Docker/firewall/host operations directly.
Those actions belong to Konnaxion Agent.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
import argparse
import importlib
import json
import sys
from typing import Any, Callable, Mapping, Sequence

from kx_shared.konnaxion_constants import (
    APP_VERSION,
    CAPSULE_EXTENSION,
    CLI_NAME,
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_VERSION,
    DEFAULT_CHANNEL,
    DEFAULT_INSTANCE_ID,
    DEFAULT_NETWORK_PROFILE,
    DEFAULT_EXPOSURE_MODE,
    MANAGER_NAME,
    PARAM_VERSION,
    PUBLIC_CLI_COMMANDS,
    NetworkProfile,
    ExposureMode,
)
from kx_shared.validation import (
    ValidationIssue,
    ValidationFailed,
    raise_if_issues,
    validate_capsule_filename,
    validate_capsule_id,
    validate_capsule_version,
    validate_exposure_mode,
    validate_identifier,
    validate_network_profile,
)


DEFAULT_AGENT_URL = "http://127.0.0.1:8765"


@dataclass(frozen=True)
class CliContext:
    """Global CLI context passed to command handlers."""

    json_output: bool = False
    verbose: bool = False
    agent_url: str = DEFAULT_AGENT_URL


@dataclass(frozen=True)
class CliResult:
    """Structured CLI result for human or JSON output."""

    ok: bool
    command: str
    message: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)
    issues: tuple[Mapping[str, Any], ...] = ()

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 1


class CliError(RuntimeError):
    """User-facing CLI error with a stable exit code."""

    def __init__(
        self,
        message: str,
        *,
        exit_code: int = 2,
        issues: Sequence[ValidationIssue] = (),
    ) -> None:
        self.exit_code = exit_code
        self.issues = tuple(issues)
        super().__init__(message)


def create_parser() -> argparse.ArgumentParser:
    """Create the canonical kx parser."""

    parser = argparse.ArgumentParser(
        prog=CLI_NAME,
        description=f"{MANAGER_NAME} command-line interface.",
    )
    parser.add_argument("--version", action="store_true", help="Show Konnaxion CLI version.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    parser.add_argument("--verbose", action="store_true", help="Print more diagnostic information.")
    parser.add_argument(
        "--agent-url",
        default=DEFAULT_AGENT_URL,
        help=f"Konnaxion Agent URL. Default: {DEFAULT_AGENT_URL}",
    )

    subparsers = parser.add_subparsers(dest="group")

    _add_capsule_commands(subparsers)
    _add_instance_commands(subparsers)
    _add_backup_commands(subparsers)
    _add_security_commands(subparsers)
    _add_network_commands(subparsers)

    return parser


def run(argv: Sequence[str] | None = None) -> int:
    """Run the kx CLI and return a process exit code."""

    parser = create_parser()
    args = parser.parse_args(argv)

    context = CliContext(
        json_output=bool(getattr(args, "json", False)),
        verbose=bool(getattr(args, "verbose", False)),
        agent_url=str(getattr(args, "agent_url", DEFAULT_AGENT_URL)),
    )

    if getattr(args, "version", False):
        result = CliResult(
            ok=True,
            command="version",
            message=f"Konnaxion CLI {APP_VERSION}",
            data={
                "app_version": APP_VERSION,
                "param_version": PARAM_VERSION,
                "cli": CLI_NAME,
            },
        )
        _print_result(result, context)
        return result.exit_code

    if not getattr(args, "group", None):
        parser.print_help()
        return 2

    try:
        result = dispatch(args, context)
        _print_result(result, context)
        return result.exit_code

    except ValidationFailed as exc:
        _print_error("Validation failed.", context, exit_code=2, issues=exc.issues)
        return 2
    except CliError as exc:
        _print_error(str(exc), context, exit_code=exc.exit_code, issues=exc.issues)
        return exc.exit_code
    except KeyboardInterrupt:
        _print_error("Interrupted.", context, exit_code=130)
        return 130


def main() -> None:
    """Console-script entrypoint."""

    raise SystemExit(run())


def dispatch(args: argparse.Namespace, context: CliContext) -> CliResult:
    """Dispatch parsed args to the selected command."""

    group = str(args.group)
    command = str(getattr(args, f"{group}_command", ""))

    if group == "capsule":
        return _dispatch_capsule(command, args, context)
    if group == "instance":
        return _dispatch_instance(command, args, context)
    if group == "backup":
        return _dispatch_backup(command, args, context)
    if group == "security":
        return _dispatch_security(command, args, context)
    if group == "network":
        return _dispatch_network(command, args, context)

    raise CliError(f"Unsupported command group: {group}", exit_code=2)


def _add_capsule_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    capsule = subparsers.add_parser("capsule", help="Build, verify, and import Konnaxion Capsules.")
    capsule_sub = capsule.add_subparsers(dest="capsule_command", required=True)

    build = capsule_sub.add_parser("build", help="Build a signed .kxcap capsule.")
    build.add_argument("--source-dir", type=Path, default=Path("."), help="Source tree to package.")
    build.add_argument("--output", type=Path, default=None, help="Output .kxcap file.")
    build.add_argument("--channel", default=DEFAULT_CHANNEL, help="Capsule channel.")
    build.add_argument("--capsule-id", default=DEFAULT_CAPSULE_ID, help="Canonical capsule id.")
    build.add_argument("--version", dest="capsule_version", default=DEFAULT_CAPSULE_VERSION, help="Capsule version.")
    build.add_argument("--profile", default=DEFAULT_NETWORK_PROFILE.value, help="Default network profile.")
    build.add_argument("--unsigned", action="store_true", help="Build unsigned capsule for local development only.")
    build.add_argument("--no-verify", action="store_true", help="Skip post-build verification.")
    build.add_argument("--force", action="store_true", help="Overwrite existing output.")

    verify = capsule_sub.add_parser("verify", help="Verify a .kxcap capsule.")
    verify.add_argument("capsule", type=Path, help="Path to .kxcap file.")
    verify.add_argument("--strict", action="store_true", help="Fail on blocking verification issues.")

    import_cmd = capsule_sub.add_parser("import", help="Import a verified capsule through the Agent.")
    import_cmd.add_argument("capsule", type=Path, help="Path to .kxcap file.")
    import_cmd.add_argument("--instance-id", default=DEFAULT_INSTANCE_ID, help="Target or generated instance id.")
    import_cmd.add_argument("--profile", default=DEFAULT_NETWORK_PROFILE.value, help="Network profile for import.")
    import_cmd.add_argument("--force", action="store_true", help="Allow replacing imported capsule metadata.")


def _add_instance_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    instance = subparsers.add_parser("instance", help="Manage Konnaxion Instances.")
    instance_sub = instance.add_subparsers(dest="instance_command", required=True)

    create = instance_sub.add_parser("create", help="Create an instance from an imported capsule.")
    create.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    create.add_argument("--capsule-id", default=DEFAULT_CAPSULE_ID)
    create.add_argument("--network", dest="profile", default=DEFAULT_NETWORK_PROFILE.value)
    create.add_argument("--exposure", default=DEFAULT_EXPOSURE_MODE.value)

    start = instance_sub.add_parser("start", help="Start an instance.")
    start.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    start.add_argument("--network", dest="profile", default=None)
    start.add_argument("--force-security-check", action="store_true")

    stop = instance_sub.add_parser("stop", help="Stop an instance.")
    stop.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    stop.add_argument("--timeout", type=int, default=None)

    status_cmd = instance_sub.add_parser("status", help="Show instance status.")
    status_cmd.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)

    logs = instance_sub.add_parser("logs", help="Show instance logs.")
    logs.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    logs.add_argument("--service", action="append", default=None, help="Canonical service name. Repeatable.")
    logs.add_argument("--lines", type=int, default=300)
    logs.add_argument("--no-timestamps", action="store_true")

    backup = instance_sub.add_parser("backup", help="Create an instance backup.")
    backup.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    backup.add_argument("--class", dest="backup_class", default="manual", choices=("manual", "scheduled", "pre_update", "pre_restore"))
    backup.add_argument("--note", default="")

    restore = instance_sub.add_parser("restore", help="Restore an instance from a backup.")
    restore.add_argument("instance_id")
    restore.add_argument("--from", dest="backup_id", required=True)
    restore.add_argument("--force", action="store_true")

    restore_new = instance_sub.add_parser("restore-new", help="Restore a backup into a new instance.")
    restore_new.add_argument("--from", dest="backup_id", required=True)
    restore_new.add_argument("--new-instance-id", required=True)

    update = instance_sub.add_parser("update", help="Update an instance to a new capsule.")
    update.add_argument("instance_id")
    update.add_argument("--capsule", type=Path, required=True)
    update.add_argument("--skip-backup", action="store_true")

    rollback = instance_sub.add_parser("rollback", help="Rollback an instance.")
    rollback.add_argument("instance_id")
    rollback.add_argument("--to-capsule-id", default=None)
    rollback.add_argument("--force", action="store_true")

    health = instance_sub.add_parser("health", help="Show instance health.")
    health.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)


def _add_backup_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    backup = subparsers.add_parser("backup", help="List, verify, and test-restore backups.")
    backup_sub = backup.add_subparsers(dest="backup_command", required=True)

    list_cmd = backup_sub.add_parser("list", help="List backups.")
    list_cmd.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    list_cmd.add_argument("--class", dest="backup_class", default=None)

    verify = backup_sub.add_parser("verify", help="Verify a backup artifact.")
    verify.add_argument("backup_id")

    test_restore = backup_sub.add_parser("test-restore", help="Run a test restore of a backup.")
    test_restore.add_argument("backup_id")
    test_restore.add_argument("--new-instance-id", default=None)


def _add_security_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    security = subparsers.add_parser("security", help="Run Security Gate checks.")
    security_sub = security.add_subparsers(dest="security_command", required=True)

    check = security_sub.add_parser("check", help="Run the Security Gate for an instance.")
    check.add_argument("instance_id", nargs="?", default=DEFAULT_INSTANCE_ID)
    check.add_argument("--force", action="store_true")
    check.add_argument("--no-warnings", action="store_true")


def _add_network_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    network = subparsers.add_parser("network", help="Manage instance network profile.")
    network_sub = network.add_subparsers(dest="network_command", required=True)

    set_profile = network_sub.add_parser("set-profile", help="Set a canonical network profile.")
    set_profile.add_argument("instance_id")
    set_profile.add_argument("profile", choices=[profile.value for profile in NetworkProfile])
    set_profile.add_argument("--exposure", choices=[mode.value for mode in ExposureMode], default=None)
    set_profile.add_argument("--public-expires-at", default=None)


def _dispatch_capsule(command: str, args: argparse.Namespace, context: CliContext) -> CliResult:
    if command == "build":
        output = args.output
        if output is not None:
            _validate_or_raise(validate_capsule_filename(Path(output).name))
        _validate_or_raise(validate_capsule_id(args.capsule_id))
        _validate_or_raise(validate_capsule_version(args.capsule_version))
        _validate_or_raise(validate_network_profile(args.profile))

        result = _call_handler(
            "kx_cli.capsule",
            "build",
            args,
            context,
            fallback=lambda: _call_builder_main(
                [
                    "capsule",
                    "build",
                    "--source-dir",
                    str(args.source_dir),
                    "--channel",
                    args.channel,
                    "--capsule-id",
                    args.capsule_id,
                    "--version",
                    args.capsule_version,
                    "--profile",
                    args.profile,
                    *(["--output", str(args.output)] if args.output else []),
                    *(["--unsigned"] if args.unsigned else []),
                    *(["--no-verify"] if args.no_verify else []),
                    *(["--force"] if args.force else []),
                ],
                context,
            ),
        )
        return _normalize_cli_result(result, command="capsule build")

    if command == "verify":
        _validate_or_raise(validate_capsule_filename(args.capsule.name))
        result = _call_handler(
            "kx_cli.capsule",
            "verify",
            args,
            context,
            fallback=lambda: _call_builder_main(
                [
                    "capsule",
                    "verify",
                    str(args.capsule),
                    *(["--strict"] if args.strict else []),
                ],
                context,
            ),
        )
        return _normalize_cli_result(result, command="capsule verify")

    if command == "import":
        _validate_or_raise(validate_capsule_filename(args.capsule.name))
        _validate_or_raise(validate_identifier(args.instance_id, field="instance_id"))
        _validate_or_raise(validate_network_profile(args.profile))
        result = _call_handler("kx_cli.capsule", "import_capsule", args, context)
        return _normalize_cli_result(result, command="capsule import")

    raise CliError(f"Unsupported capsule command: {command}", exit_code=2)


def _dispatch_instance(command: str, args: argparse.Namespace, context: CliContext) -> CliResult:
    if hasattr(args, "instance_id"):
        _validate_or_raise(validate_identifier(args.instance_id, field="instance_id"))

    if command == "create":
        _validate_or_raise(validate_capsule_id(args.capsule_id))
        _validate_or_raise(validate_network_profile(args.profile))
        _validate_or_raise(validate_exposure_mode(args.exposure))
        handler_name = "create_instance"
    elif command == "start":
        if args.profile:
            _validate_or_raise(validate_network_profile(args.profile))
        handler_name = "start_instance"
    elif command == "stop":
        handler_name = "stop_instance"
    elif command == "status":
        handler_name = "instance_status"
    elif command == "logs":
        if args.lines < 1:
            raise CliError("--lines must be >= 1", exit_code=2)
        handler_name = "instance_logs"
    elif command == "backup":
        handler_name = "backup_instance"
    elif command == "restore":
        _validate_or_raise(validate_identifier(args.instance_id, field="instance_id"))
        handler_name = "restore_instance"
    elif command == "restore-new":
        _validate_or_raise(validate_identifier(args.new_instance_id, field="new_instance_id"))
        handler_name = "restore_new_instance"
    elif command == "update":
        _validate_or_raise(validate_capsule_filename(args.capsule.name))
        handler_name = "update_instance"
    elif command == "rollback":
        handler_name = "rollback_instance"
    elif command == "health":
        handler_name = "instance_health"
    else:
        raise CliError(f"Unsupported instance command: {command}", exit_code=2)

    result = _call_handler("kx_cli.instance", handler_name, args, context)
    return _normalize_cli_result(result, command=f"instance {command}")


def _dispatch_backup(command: str, args: argparse.Namespace, context: CliContext) -> CliResult:
    if command == "list":
        _validate_or_raise(validate_identifier(args.instance_id, field="instance_id"))
        handler_name = "list_backups"
    elif command == "verify":
        handler_name = "verify_backup"
    elif command == "test-restore":
        if args.new_instance_id:
            _validate_or_raise(validate_identifier(args.new_instance_id, field="new_instance_id"))
        handler_name = "test_restore_backup"
    else:
        raise CliError(f"Unsupported backup command: {command}", exit_code=2)

    result = _call_handler("kx_cli.backup", handler_name, args, context)
    return _normalize_cli_result(result, command=f"backup {command}")


def _dispatch_security(command: str, args: argparse.Namespace, context: CliContext) -> CliResult:
    if command != "check":
        raise CliError(f"Unsupported security command: {command}", exit_code=2)

    _validate_or_raise(validate_identifier(args.instance_id, field="instance_id"))
    result = _call_handler("kx_cli.security", "check_security", args, context)
    return _normalize_cli_result(result, command="security check")


def _dispatch_network(command: str, args: argparse.Namespace, context: CliContext) -> CliResult:
    if command != "set-profile":
        raise CliError(f"Unsupported network command: {command}", exit_code=2)

    _validate_or_raise(validate_identifier(args.instance_id, field="instance_id"))
    _validate_or_raise(validate_network_profile(args.profile))
    if args.exposure:
        _validate_or_raise(validate_exposure_mode(args.exposure))

    result = _call_handler("kx_cli.network", "set_profile", args, context)
    return _normalize_cli_result(result, command="network set-profile")


def _call_handler(
    module_name: str,
    function_name: str,
    args: argparse.Namespace,
    context: CliContext,
    *,
    fallback: Callable[[], Any] | None = None,
) -> Any:
    """Call a handler from a command module, or fail with a useful bootstrap message."""

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if fallback is not None:
            return fallback()
        raise CliError(
            f"{module_name}.py is not implemented yet; required for this command.",
            exit_code=3,
        ) from exc

    handler = getattr(module, function_name, None)
    if handler is None:
        if fallback is not None:
            return fallback()
        raise CliError(
            f"{module_name}.{function_name} is not implemented yet.",
            exit_code=3,
        )

    return handler(args=args, context=context)


def _call_builder_main(builder_args: list[str], context: CliContext) -> CliResult:
    """Delegate capsule build/verify to kx_builder.main."""

    try:
        from kx_builder.main import run as builder_run
    except ModuleNotFoundError as exc:
        raise CliError("kx_builder.main is not available.", exit_code=3) from exc

    # Avoid nested JSON noise. The builder will print its own detailed output
    # when called directly; from the canonical CLI we return a clean status.
    exit_code = builder_run(builder_args)
    return CliResult(
        ok=exit_code == 0,
        command=" ".join(["capsule", *builder_args[1:2]]),
        message="Builder command completed." if exit_code == 0 else "Builder command failed.",
        data={"exit_code": exit_code},
    )


def _normalize_cli_result(result: Any, *, command: str) -> CliResult:
    if isinstance(result, CliResult):
        return result

    if isinstance(result, Mapping):
        return CliResult(
            ok=bool(result.get("ok", True)),
            command=str(result.get("command", command)),
            message=str(result.get("message", "")),
            data=_mapping_or_empty(result.get("data", result)),
            issues=_normalize_issues(result.get("issues", ())),
        )

    if is_dataclass(result):
        data = asdict(result)
        return CliResult(
            ok=bool(data.get("ok", True)),
            command=str(data.get("command", command)),
            message=str(data.get("message", "")),
            data=data,
            issues=_normalize_issues(data.get("issues", ())),
        )

    if isinstance(result, bool):
        return CliResult(
            ok=result,
            command=command,
            message="Command completed." if result else "Command failed.",
        )

    if result is None:
        return CliResult(
            ok=True,
            command=command,
            message="Command completed.",
        )

    return CliResult(
        ok=True,
        command=command,
        message=str(result),
    )


def _validate_or_raise(issues: Sequence[ValidationIssue]) -> None:
    raise_if_issues(issues)


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _normalize_issues(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not value:
        return ()

    normalized: list[Mapping[str, Any]] = []
    for item in value:
        if isinstance(item, Mapping):
            normalized.append(item)
        elif isinstance(item, ValidationIssue):
            normalized.append(asdict(item))
        elif is_dataclass(item):
            normalized.append(asdict(item))
        else:
            normalized.append({"code": "issue", "message": str(item)})
    return tuple(normalized)


def _print_result(result: CliResult, context: CliContext) -> None:
    if context.json_output:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
        return

    status = "OK" if result.ok else "FAILED"
    print(f"{status}: {result.command}")
    if result.message:
        print(result.message)

    if result.data:
        for key, value in result.data.items():
            if key in {"ok", "command", "message", "issues"}:
                continue
            if isinstance(value, (dict, list, tuple)):
                print(f"{key}={json.dumps(value, sort_keys=True)}")
            else:
                print(f"{key}={value}")

    if result.issues:
        print("issues:")
        for issue in result.issues:
            print(f"- {issue.get('code')}: {issue.get('message')}")

    if context.verbose:
        print(f"agent_url={context.agent_url}")


def _print_error(
    message: str,
    context: CliContext,
    *,
    exit_code: int,
    issues: Sequence[ValidationIssue] = (),
) -> None:
    if context.json_output:
        payload = {
            "ok": False,
            "exit_code": exit_code,
            "message": message,
            "issues": [asdict(issue) for issue in issues],
        }
        print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stderr)
        return

    print(f"ERROR: {message}", file=sys.stderr)
    for issue in issues:
        print(f"- {issue.code}: {issue.message}", file=sys.stderr)


def list_public_commands() -> tuple[str, ...]:
    """Return canonical public commands for docs/tests/completion generation."""

    return tuple(PUBLIC_CLI_COMMANDS)


if __name__ == "__main__":
    main()
