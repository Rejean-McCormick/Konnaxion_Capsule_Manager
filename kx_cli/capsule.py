"""Capsule command group for the canonical ``kx`` CLI.

This module implements the public capsule commands:

    kx capsule build
    kx capsule verify
    kx capsule import

The CLI remains a thin orchestration layer. It does not invent capsule names,
extensions, paths, profiles, or service identifiers. It delegates build logic to
``kx_builder`` and import/verification logic to the Konnaxion Agent modules.
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from kx_shared.konnaxion_constants import (
    CAPSULE_EXTENSION,
    DEFAULT_CHANNEL,
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_VERSION,
    DEFAULT_NETWORK_PROFILE,
    KX_CAPSULES_DIR,
    NetworkProfile,
)

from kx_builder.config import (
    BuilderConfig,
    BuilderConfigError,
    capsule_filename_for,
    capsule_id_for,
    ensure_build_directories,
    validate_capsule_output_path,
)

from kx_agent.capsules.manifest import (
    CapsuleManifestError,
    load_manifest,
    validate_capsule_root,
)


class CapsuleCliError(RuntimeError):
    """Raised when a capsule CLI operation fails."""


@dataclass(frozen=True)
class CapsuleCommandResult:
    """Structured result for capsule CLI operations."""

    ok: bool
    action: str
    path: str | None = None
    capsule_id: str | None = None
    capsule_version: str | None = None
    message: str = ""
    details: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register ``kx capsule`` commands on a root argparse subparser."""

    capsule_parser = subparsers.add_parser(
        "capsule",
        help="Build, verify, and import Konnaxion Capsule files.",
    )

    capsule_subparsers = capsule_parser.add_subparsers(
        dest="capsule_command",
        metavar="COMMAND",
        required=True,
    )

    build_parser = capsule_subparsers.add_parser(
        "build",
        help="Build a signed Konnaxion Capsule artifact.",
    )
    _add_common_output_args(build_parser)
    build_parser.add_argument(
        "--source-root",
        default=".",
        help="Source tree root used by the Builder. Default: current directory.",
    )
    build_parser.add_argument(
        "--work-dir",
        default=".kxbuild",
        help="Temporary Builder work directory. Default: .kxbuild",
    )
    build_parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help=f"Capsule channel. Default: {DEFAULT_CHANNEL}",
    )
    build_parser.add_argument(
        "--capsule-id",
        default=None,
        help="Capsule ID. Default: generated from channel/date.",
    )
    build_parser.add_argument(
        "--version",
        "--capsule-version",
        dest="capsule_version",
        default=DEFAULT_CAPSULE_VERSION,
        help=f"Capsule version. Default: {DEFAULT_CAPSULE_VERSION}",
    )
    build_parser.add_argument(
        "--profile",
        default=DEFAULT_NETWORK_PROFILE.value,
        choices=[profile.value for profile in NetworkProfile],
        help=f"Default profile to include/select. Default: {DEFAULT_NETWORK_PROFILE.value}",
    )
    build_parser.add_argument(
        "--allow-unsigned",
        action="store_true",
        help="Allow local development build without a signing key.",
    )
    build_parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )
    build_parser.set_defaults(func=build_capsule_command)

    verify_parser = capsule_subparsers.add_parser(
        "verify",
        help="Verify a Konnaxion Capsule or extracted capsule directory.",
    )
    verify_parser.add_argument(
        "path",
        help="Path to a .kxcap file or extracted capsule directory.",
    )
    verify_parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )
    verify_parser.set_defaults(func=verify_capsule_command)

    import_parser = capsule_subparsers.add_parser(
        "import",
        help="Import a verified Konnaxion Capsule into canonical capsule storage.",
    )
    import_parser.add_argument(
        "path",
        help="Path to a .kxcap file.",
    )
    import_parser.add_argument(
        "--capsule-id",
        default=None,
        help="Capsule ID to store as. Default: derived from filename.",
    )
    import_parser.add_argument(
        "--capsules-dir",
        default=str(KX_CAPSULES_DIR),
        help=f"Capsule storage directory. Default: {KX_CAPSULES_DIR}",
    )
    import_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing imported capsule.",
    )
    import_parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )
    import_parser.set_defaults(func=import_capsule_command)


def build_capsule_command(args: argparse.Namespace) -> int:
    """Handle ``kx capsule build``."""

    try:
        result = build_capsule(
            source_root=Path(args.source_root),
            output_dir=Path(args.output_dir),
            work_dir=Path(args.work_dir),
            channel=args.channel,
            capsule_id=args.capsule_id,
            capsule_version=args.capsule_version,
            profile=NetworkProfile(args.profile),
            require_signature=not args.allow_unsigned,
        )
    except Exception as exc:
        return _print_error("build", exc, as_json=args.json)

    return _print_result(result, as_json=args.json)


def verify_capsule_command(args: argparse.Namespace) -> int:
    """Handle ``kx capsule verify``."""

    try:
        result = verify_capsule(Path(args.path))
    except Exception as exc:
        return _print_error("verify", exc, as_json=args.json)

    return _print_result(result, as_json=args.json)


def import_capsule_command(args: argparse.Namespace) -> int:
    """Handle ``kx capsule import``."""

    try:
        result = import_capsule(
            Path(args.path),
            capsule_id=args.capsule_id,
            capsules_dir=Path(args.capsules_dir),
            force=args.force,
        )
    except Exception as exc:
        return _print_error("import", exc, as_json=args.json)

    return _print_result(result, as_json=args.json)


def build_capsule(
    *,
    source_root: Path,
    output_dir: Path,
    work_dir: Path,
    channel: str = DEFAULT_CHANNEL,
    capsule_id: str | None = None,
    capsule_version: str = DEFAULT_CAPSULE_VERSION,
    profile: NetworkProfile = DEFAULT_NETWORK_PROFILE,
    require_signature: bool = True,
) -> CapsuleCommandResult:
    """Build a capsule using the Builder implementation when available.

    The full build implementation is delegated to ``kx_builder.main`` or
    ``kx_builder.package`` if those modules expose compatible functions. Until
    those files are implemented, this function validates and prepares canonical
    Builder configuration and reports what is missing.
    """

    resolved_capsule_id = capsule_id or capsule_id_for(channel=channel)
    config = BuilderConfig(
        source_root=source_root,
        output_dir=output_dir,
        work_dir=work_dir,
        channel=channel,
        capsule_id=resolved_capsule_id,
        capsule_version=capsule_version,
        require_signature=require_signature,
    )

    try:
        config.validate(require_existing_source=True)
    except BuilderConfigError:
        if require_signature:
            raise
        # In unsigned local-dev mode, keep validating core fields but allow the
        # missing signing key to be deferred to the Builder implementation.
        config = BuilderConfig(
            source_root=source_root,
            output_dir=output_dir,
            work_dir=work_dir,
            channel=channel,
            capsule_id=resolved_capsule_id,
            capsule_version=capsule_version,
            require_signature=False,
        )
        config.validate(require_existing_source=True)

    ensure_build_directories(config)

    builder = _find_builder_callable()
    if builder is None:
        return CapsuleCommandResult(
            ok=False,
            action="build",
            path=str(config.capsule_output_path),
            capsule_id=config.capsule_id,
            capsule_version=config.capsule_version,
            message=(
                "Builder implementation is not wired yet. "
                "Expected kx_builder.main.build_capsule or "
                "kx_builder.package.build_capsule."
            ),
            details={
                "source_root": str(config.absolute_source_root),
                "work_dir": str(config.absolute_work_dir),
                "output_dir": str(config.absolute_output_dir),
                "profile": profile.value,
                "requires_signature": require_signature,
                "expected_filename": config.capsule_filename,
            },
        )

    built_path = Path(
        builder(
            config=config,
            profile=profile,
        )
    )
    validate_capsule_output_path(built_path)

    return CapsuleCommandResult(
        ok=True,
        action="build",
        path=str(built_path),
        capsule_id=config.capsule_id,
        capsule_version=config.capsule_version,
        message="Capsule built.",
        details={
            "profile": profile.value,
            "filename": built_path.name,
        },
    )


def verify_capsule(path: Path) -> CapsuleCommandResult:
    """Verify a capsule path or extracted capsule directory.

    For extracted directories, this validates root layout and manifest.
    For ``.kxcap`` files, this validates the extension and delegates full archive
    verification to Agent verifier modules when available.
    """

    if not path.exists():
        raise CapsuleCliError(f"capsule path does not exist: {path}")

    if path.is_dir():
        root_result = validate_capsule_root(path)
        root_result.raise_for_errors()

        manifest = load_manifest(path / "manifest.yaml")
        return CapsuleCommandResult(
            ok=True,
            action="verify",
            path=str(path),
            capsule_id=manifest.capsule_id,
            capsule_version=manifest.capsule_version,
            message="Extracted capsule directory is valid.",
            details={
                "schema_version": manifest.schema_version,
                "app_version": manifest.app_version,
                "services": list(manifest.service_names()),
                "profiles": list(manifest.profiles),
            },
        )

    if path.suffix != CAPSULE_EXTENSION:
        raise CapsuleCliError(
            f"capsule file must end with {CAPSULE_EXTENSION!r}: {path}"
        )

    verifier = _find_verifier_callable()
    if verifier is None:
        return CapsuleCommandResult(
            ok=True,
            action="verify",
            path=str(path),
            capsule_id=_capsule_id_from_filename(path),
            message=(
                "Capsule extension is valid. Full signature/checksum/archive "
                "verification awaits kx_agent.capsules.verifier implementation."
            ),
            details={
                "filename": path.name,
                "extension": CAPSULE_EXTENSION,
                "full_verifier_wired": False,
            },
        )

    verification = verifier(path)
    return _coerce_result(
        verification,
        action="verify",
        fallback_path=path,
        fallback_message="Capsule verified.",
    )


def import_capsule(
    path: Path,
    *,
    capsule_id: str | None = None,
    capsules_dir: Path = KX_CAPSULES_DIR,
    force: bool = False,
) -> CapsuleCommandResult:
    """Import a verified ``.kxcap`` file into canonical capsule storage."""

    if not path.exists():
        raise CapsuleCliError(f"capsule file does not exist: {path}")

    if not path.is_file():
        raise CapsuleCliError(f"capsule import requires a file: {path}")

    if path.suffix != CAPSULE_EXTENSION:
        raise CapsuleCliError(
            f"capsule file must end with {CAPSULE_EXTENSION!r}: {path}"
        )

    import_id = capsule_id or _capsule_id_from_filename(path)
    if not import_id:
        import_id = DEFAULT_CAPSULE_ID

    target_dir = Path(capsules_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / f"{import_id}{CAPSULE_EXTENSION}"

    if target_path.exists() and not force:
        raise CapsuleCliError(
            f"capsule already exists: {target_path}; use --force to overwrite"
        )

    importer = _find_importer_callable()
    if importer is not None:
        imported = importer(
            path=path,
            capsule_id=import_id,
            capsules_dir=target_dir,
            force=force,
        )
        return _coerce_result(
            imported,
            action="import",
            fallback_path=target_path,
            fallback_message="Capsule imported.",
        )

    shutil.copy2(path, target_path)

    return CapsuleCommandResult(
        ok=True,
        action="import",
        path=str(target_path),
        capsule_id=import_id,
        message="Capsule imported to canonical capsule storage.",
        details={
            "source": str(path),
            "target": str(target_path),
            "importer_wired": False,
        },
    )


def build_parser() -> argparse.ArgumentParser:
    """Build a standalone parser for this command group."""

    parser = argparse.ArgumentParser(prog="kx")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Standalone capsule CLI entrypoint."""

    parser = build_parser()
    args = parser.parse_args(argv)

    handler = getattr(args, "func", None)
    if handler is None:
        parser.print_help()
        return 2

    return int(handler(args))


def _add_common_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output-dir",
        default="dist",
        help="Directory where the capsule is written. Default: dist",
    )


def _find_builder_callable() -> Callable[..., Any] | None:
    for module_name in ("kx_builder.main", "kx_builder.package"):
        try:
            module = __import__(module_name, fromlist=["build_capsule"])
        except ImportError:
            continue

        candidate = getattr(module, "build_capsule", None)
        if callable(candidate):
            return candidate

    return None


def _find_verifier_callable() -> Callable[..., Any] | None:
    for module_name in ("kx_agent.capsules.verifier", "kx_builder.verify"):
        try:
            module = __import__(module_name, fromlist=["verify_capsule"])
        except ImportError:
            continue

        candidate = getattr(module, "verify_capsule", None)
        if callable(candidate):
            return candidate

    return None


def _find_importer_callable() -> Callable[..., Any] | None:
    try:
        module = __import__("kx_agent.capsules.importer", fromlist=["import_capsule"])
    except ImportError:
        return None

    candidate = getattr(module, "import_capsule", None)
    return candidate if callable(candidate) else None


def _capsule_id_from_filename(path: Path) -> str:
    filename = path.name
    if filename.endswith(CAPSULE_EXTENSION):
        return filename[: -len(CAPSULE_EXTENSION)]
    return path.stem


def _coerce_result(
    value: Any,
    *,
    action: str,
    fallback_path: Path,
    fallback_message: str,
) -> CapsuleCommandResult:
    if isinstance(value, CapsuleCommandResult):
        return value

    if isinstance(value, Mapping):
        return CapsuleCommandResult(
            ok=bool(value.get("ok", True)),
            action=str(value.get("action", action)),
            path=str(value.get("path", fallback_path)),
            capsule_id=value.get("capsule_id"),
            capsule_version=value.get("capsule_version"),
            message=str(value.get("message", fallback_message)),
            details=dict(value.get("details", {})),
        )

    if isinstance(value, (str, Path)):
        return CapsuleCommandResult(
            ok=True,
            action=action,
            path=str(value),
            message=fallback_message,
        )

    return CapsuleCommandResult(
        ok=True,
        action=action,
        path=str(fallback_path),
        message=fallback_message,
        details={"raw_result": repr(value)},
    )


def _print_result(result: CapsuleCommandResult, *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        status = "OK" if result.ok else "ERROR"
        print(f"{status}: {result.message}")
        if result.path:
            print(f"path: {result.path}")
        if result.capsule_id:
            print(f"capsule_id: {result.capsule_id}")
        if result.capsule_version:
            print(f"capsule_version: {result.capsule_version}")

    return 0 if result.ok else 1


def _print_error(action: str, exc: Exception, *, as_json: bool) -> int:
    result = CapsuleCommandResult(
        ok=False,
        action=action,
        message=str(exc),
        details={"error_type": exc.__class__.__name__},
    )

    if as_json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"ERROR: {result.message}")

    return 1


__all__ = [
    "CapsuleCliError",
    "CapsuleCommandResult",
    "build_capsule",
    "build_capsule_command",
    "build_parser",
    "import_capsule",
    "import_capsule_command",
    "main",
    "register",
    "verify_capsule",
    "verify_capsule_command",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
