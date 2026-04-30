"""
Konnaxion Capsule Builder CLI entrypoint.

This module owns developer-side capsule commands. It should not perform Agent
runtime actions such as starting instances, changing firewall rules, or running
Docker Compose stacks. Its job is to build and verify signed .kxcap artifacts.

Canonical public commands implemented here:
- kx capsule build
- kx capsule verify

The implementation is dependency-light and uses argparse so it can run during
bootstrap before optional CLI frameworks are installed.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import argparse
import json
import sys
from typing import Any, Mapping, Sequence

from kx_shared.konnaxion_constants import (
    APP_VERSION,
    BUILDER_NAME,
    CAPSULE_EXTENSION,
    CAPSULE_FILENAME_PATTERN,
    DEFAULT_CHANNEL,
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_VERSION,
    DEFAULT_NETWORK_PROFILE,
    PARAM_VERSION,
)
from kx_shared.validation import (
    ValidationIssue,
    ValidationFailed,
    raise_if_issues,
    validate_capsule_filename,
    validate_capsule_id,
    validate_capsule_version,
    validate_network_profile,
)


@dataclass(frozen=True)
class BuildRequest:
    """Normalized build request from CLI args."""

    source_dir: Path
    output: Path
    channel: str
    capsule_id: str
    capsule_version: str
    profile: str
    sign: bool
    verify: bool
    force: bool


@dataclass(frozen=True)
class BuildResult:
    """Structured build result suitable for JSON output."""

    ok: bool
    output: str
    capsule_id: str
    capsule_version: str
    app_version: str
    param_version: str
    message: str = ""


@dataclass(frozen=True)
class VerifyResult:
    """Structured verify result suitable for JSON output."""

    ok: bool
    capsule_path: str
    message: str = ""
    issues: tuple[Mapping[str, Any], ...] = ()


class BuilderCliError(RuntimeError):
    """User-facing CLI error."""

    def __init__(self, message: str, *, exit_code: int = 2) -> None:
        self.exit_code = exit_code
        super().__init__(message)


def build_capsule(request: BuildRequest) -> BuildResult:
    """Build a Konnaxion Capsule.

    This function delegates to optional builder modules when available. In early
    bootstrap mode, it performs validation and fails with a precise message
    instead of silently creating an invalid capsule.
    """

    _validate_build_request(request)

    try:
        from kx_builder.package import build_package  # type: ignore
    except ModuleNotFoundError as exc:
        raise BuilderCliError(
            "kx_builder.package.build_package is not implemented yet; "
            "create kx_builder/package.py before running capsule builds.",
            exit_code=3,
        ) from exc

    result = build_package(
        source_dir=request.source_dir,
        output=request.output,
        channel=request.channel,
        capsule_id=request.capsule_id,
        capsule_version=request.capsule_version,
        profile=request.profile,
        sign=request.sign,
        verify=request.verify,
        force=request.force,
    )

    if isinstance(result, BuildResult):
        return result

    if isinstance(result, Mapping):
        return BuildResult(
            ok=bool(result.get("ok", True)),
            output=str(result.get("output", request.output)),
            capsule_id=str(result.get("capsule_id", request.capsule_id)),
            capsule_version=str(result.get("capsule_version", request.capsule_version)),
            app_version=str(result.get("app_version", APP_VERSION)),
            param_version=str(result.get("param_version", PARAM_VERSION)),
            message=str(result.get("message", "")),
        )

    return BuildResult(
        ok=True,
        output=str(request.output),
        capsule_id=request.capsule_id,
        capsule_version=request.capsule_version,
        app_version=APP_VERSION,
        param_version=PARAM_VERSION,
        message="Capsule build completed.",
    )


def verify_capsule(capsule_path: Path, *, strict: bool = False) -> VerifyResult:
    """Verify a Konnaxion Capsule using Builder verifier first, Agent verifier second."""

    issues = validate_capsule_filename(capsule_path.name)
    if issues:
        if strict:
            raise ValidationFailed(issues)
        return VerifyResult(
            ok=False,
            capsule_path=str(capsule_path),
            message="Invalid capsule filename.",
            issues=tuple(asdict(issue) for issue in issues),
        )

    if not capsule_path.exists():
        issue = ValidationIssue(
            code="capsule_not_found",
            message=f"Capsule file does not exist: {capsule_path}",
            field="capsule_path",
        )
        if strict:
            raise ValidationFailed((issue,))
        return VerifyResult(
            ok=False,
            capsule_path=str(capsule_path),
            message=issue.message,
            issues=(asdict(issue),),
        )

    try:
        from kx_builder.verify import verify_capsule_file  # type: ignore
    except ModuleNotFoundError:
        verify_capsule_file = None

    if verify_capsule_file is not None:
        result = verify_capsule_file(capsule_path, strict=strict)
        return _normalize_verify_result(capsule_path, result)

    try:
        from kx_agent.capsules.verifier import verify_capsule as agent_verify_capsule
    except ModuleNotFoundError as exc:
        raise BuilderCliError(
            "No capsule verifier is available. Implement kx_builder/verify.py "
            "or provide kx_agent/capsules/verifier.py.",
            exit_code=3,
        ) from exc

    result = agent_verify_capsule(capsule_path, strict=strict)
    return VerifyResult(
        ok=bool(getattr(result, "passed", False)),
        capsule_path=str(capsule_path),
        message="Capsule verification passed." if getattr(result, "passed", False) else "Capsule verification failed.",
        issues=tuple(asdict(issue) for issue in getattr(result, "issues", ())),
    )


def create_parser() -> argparse.ArgumentParser:
    """Create the argparse CLI parser."""

    parser = argparse.ArgumentParser(
        prog="kx-builder",
        description=f"{BUILDER_NAME} command-line entrypoint.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")

    subparsers = parser.add_subparsers(dest="command_group", required=True)

    capsule = subparsers.add_parser("capsule", help="Build or verify Konnaxion Capsule artifacts.")
    capsule_sub = capsule.add_subparsers(dest="capsule_command", required=True)

    build = capsule_sub.add_parser("build", help="Build a signed Konnaxion Capsule.")
    build.add_argument(
        "--source-dir",
        default=".",
        type=Path,
        help="Source tree to package.",
    )
    build.add_argument(
        "--output",
        type=Path,
        default=None,
        help=f"Output .kxcap path. Defaults to {CAPSULE_FILENAME_PATTERN}.",
    )
    build.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Capsule channel, for example demo, intranet, release.",
    )
    build.add_argument(
        "--capsule-id",
        default=DEFAULT_CAPSULE_ID,
        help="Canonical capsule id.",
    )
    build.add_argument(
        "--version",
        dest="capsule_version",
        default=DEFAULT_CAPSULE_VERSION,
        help="Canonical capsule version.",
    )
    build.add_argument(
        "--profile",
        default=DEFAULT_NETWORK_PROFILE.value,
        help="Default network profile to include/target.",
    )
    build.add_argument(
        "--unsigned",
        action="store_true",
        help="Build without signing. For local development only.",
    )
    build.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip post-build verification.",
    )
    build.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output file.",
    )

    verify = capsule_sub.add_parser("verify", help="Verify a Konnaxion Capsule.")
    verify.add_argument("capsule", type=Path, help="Path to .kxcap file.")
    verify.add_argument("--strict", action="store_true", help="Raise/fail on blocking issues.")

    return parser


def run(argv: Sequence[str] | None = None) -> int:
    """Run the Builder CLI and return a process exit code."""

    parser = create_parser()
    args = parser.parse_args(argv)

    try:
        if args.command_group == "capsule" and args.capsule_command == "build":
            request = _build_request_from_args(args)
            result = build_capsule(request)
            _print_result(result, json_output=args.json)
            return 0 if result.ok else 1

        if args.command_group == "capsule" and args.capsule_command == "verify":
            result = verify_capsule(args.capsule, strict=args.strict)
            _print_result(result, json_output=args.json)
            return 0 if result.ok else 1

        parser.error("Unsupported command.")
        return 2

    except ValidationFailed as exc:
        _print_error("Validation failed.", issues=exc.issues, json_output=args.json)
        return 2
    except BuilderCliError as exc:
        _print_error(str(exc), json_output=args.json)
        return exc.exit_code
    except KeyboardInterrupt:
        _print_error("Interrupted.", json_output=args.json)
        return 130


def main() -> None:
    """Console-script entrypoint."""

    raise SystemExit(run())


def _build_request_from_args(args: argparse.Namespace) -> BuildRequest:
    output = args.output
    if output is None:
        filename = CAPSULE_FILENAME_PATTERN.format(
            channel=args.channel,
            date=_date_from_capsule_id(args.capsule_id),
        )
        output = Path(filename)

    return BuildRequest(
        source_dir=Path(args.source_dir),
        output=Path(output),
        channel=str(args.channel),
        capsule_id=str(args.capsule_id),
        capsule_version=str(args.capsule_version),
        profile=str(args.profile),
        sign=not bool(args.unsigned),
        verify=not bool(args.no_verify),
        force=bool(args.force),
    )


def _validate_build_request(request: BuildRequest) -> None:
    issues: list[ValidationIssue] = []

    if not request.source_dir.exists() or not request.source_dir.is_dir():
        issues.append(
            ValidationIssue(
                code="source_dir_missing",
                message=f"Source directory does not exist: {request.source_dir}",
                field="source_dir",
            )
        )

    if request.output.suffix != CAPSULE_EXTENSION:
        issues.extend(validate_capsule_filename(request.output.name))

    if request.output.exists() and not request.force:
        issues.append(
            ValidationIssue(
                code="output_exists",
                message=f"Output file already exists. Use --force to overwrite: {request.output}",
                field="output",
            )
        )

    issues.extend(validate_capsule_id(request.capsule_id))
    issues.extend(validate_capsule_version(request.capsule_version))
    issues.extend(validate_network_profile(request.profile))

    if not request.sign:
        issues.append(
            ValidationIssue(
                code="unsigned_capsule",
                message="Unsigned capsule build requested. This is allowed only for local development.",
                field="unsigned",
                blocking=False,
            )
        )

    raise_if_issues(issues)


def _normalize_verify_result(capsule_path: Path, result: Any) -> VerifyResult:
    if isinstance(result, VerifyResult):
        return result

    if isinstance(result, Mapping):
        raw_issues = result.get("issues", ())
        issues = tuple(
            item if isinstance(item, Mapping) else asdict(item)
            for item in raw_issues
        )
        return VerifyResult(
            ok=bool(result.get("ok", result.get("passed", False))),
            capsule_path=str(result.get("capsule_path", capsule_path)),
            message=str(result.get("message", "")),
            issues=issues,
        )

    passed = bool(getattr(result, "passed", False))
    raw_issues = getattr(result, "issues", ())
    return VerifyResult(
        ok=passed,
        capsule_path=str(capsule_path),
        message="Capsule verification passed." if passed else "Capsule verification failed.",
        issues=tuple(asdict(issue) for issue in raw_issues),
    )


def _print_result(result: BuildResult | VerifyResult, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
        return

    if isinstance(result, BuildResult):
        status = "OK" if result.ok else "FAILED"
        print(f"{status}: {result.message or 'Capsule build finished.'}")
        print(f"output={result.output}")
        print(f"capsule_id={result.capsule_id}")
        print(f"capsule_version={result.capsule_version}")
        print(f"app_version={result.app_version}")
        print(f"param_version={result.param_version}")
        return

    status = "OK" if result.ok else "FAILED"
    print(f"{status}: {result.message or 'Capsule verification finished.'}")
    print(f"capsule={result.capsule_path}")
    if result.issues:
        print("issues:")
        for issue in result.issues:
            print(f"- {issue.get('code')}: {issue.get('message')}")


def _print_error(
    message: str,
    *,
    issues: Sequence[ValidationIssue] = (),
    json_output: bool = False,
) -> None:
    if json_output:
        print(
            json.dumps(
                {
                    "ok": False,
                    "message": message,
                    "issues": [asdict(issue) for issue in issues],
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return

    print(f"ERROR: {message}", file=sys.stderr)
    for issue in issues:
        print(f"- {issue.code}: {issue.message}", file=sys.stderr)


def _date_from_capsule_id(capsule_id: str) -> str:
    parts = capsule_id.rsplit("-", maxsplit=1)
    if len(parts) == 2 and parts[1]:
        return parts[1]
    return "2026.04.30"


if __name__ == "__main__":
    main()
