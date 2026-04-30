"""
Checksum utilities for Konnaxion Capsules.

Responsibilities:
- read and write `checksums.txt`
- calculate SHA-256 digests for capsule files
- verify extracted capsule contents before import/startup
- reject unsafe checksum paths

`signature.sig` is intentionally excluded from checksum generation because it signs
the manifest/checksum set. `checksums.txt` is excluded to avoid self-reference.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator, Mapping


CHECKSUM_FILENAME = "checksums.txt"
SIGNATURE_FILENAME = "signature.sig"
DEFAULT_HASH_ALGORITHM = "sha256"
SHA256_HEX_RE = re.compile(r"^[a-fA-F0-9]{64}$")

DEFAULT_EXCLUDED_CHECKSUM_PATHS = frozenset(
    {
        CHECKSUM_FILENAME,
        SIGNATURE_FILENAME,
    }
)


class ChecksumError(ValueError):
    """Base checksum validation error."""


class UnsafeChecksumPathError(ChecksumError):
    """Raised when a checksum entry attempts path traversal or absolute paths."""


class InvalidChecksumFileError(ChecksumError):
    """Raised when `checksums.txt` is malformed."""


@dataclass(frozen=True)
class ChecksumEntry:
    """One expected digest entry from `checksums.txt`."""

    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        if not SHA256_HEX_RE.fullmatch(self.sha256):
            raise InvalidChecksumFileError(
                f"Invalid SHA-256 digest for {self.relative_path!r}: {self.sha256!r}"
            )

        validate_relative_path(self.relative_path)


@dataclass(frozen=True)
class ChecksumMismatch:
    """A digest mismatch for one capsule file."""

    relative_path: str
    expected_sha256: str
    actual_sha256: str


@dataclass(frozen=True)
class ChecksumReport:
    """Structured result for checksum verification."""

    ok: bool
    checked: int = 0
    missing: tuple[str, ...] = ()
    extra: tuple[str, ...] = ()
    mismatched: tuple[ChecksumMismatch, ...] = ()
    malformed: tuple[str, ...] = ()

    @property
    def failure_count(self) -> int:
        return (
            len(self.missing)
            + len(self.extra)
            + len(self.mismatched)
            + len(self.malformed)
        )

    def raise_for_failure(self) -> None:
        """Raise a detailed error if verification failed."""

        if self.ok:
            return

        parts: list[str] = []

        if self.missing:
            parts.append(f"missing={list(self.missing)!r}")

        if self.extra:
            parts.append(f"extra={list(self.extra)!r}")

        if self.mismatched:
            parts.append(
                "mismatched="
                + repr(
                    [
                        {
                            "path": item.relative_path,
                            "expected": item.expected_sha256,
                            "actual": item.actual_sha256,
                        }
                        for item in self.mismatched
                    ]
                )
            )

        if self.malformed:
            parts.append(f"malformed={list(self.malformed)!r}")

        raise ChecksumError("Checksum verification failed: " + "; ".join(parts))


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 hex digest for a file."""

    if not path.is_file():
        raise FileNotFoundError(path)

    digest = hashlib.sha256()

    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(chunk_size), b""):
            digest.update(chunk)

    return digest.hexdigest()


def parse_checksums_text(text: str) -> tuple[ChecksumEntry, ...]:
    """
    Parse `checksums.txt`.

    Accepted line formats:
    - `<sha256>  <relative/path>`
    - `<sha256> *<relative/path>`

    Empty lines and lines beginning with `#` are ignored.
    """

    entries: list[ChecksumEntry] = []
    seen_paths: set[str] = set()
    malformed: list[str] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        try:
            digest, raw_path = _split_checksum_line(line)
            relative_path = normalize_relative_path(raw_path)

            if relative_path in seen_paths:
                malformed.append(
                    f"line {line_number}: duplicate path {relative_path!r}"
                )
                continue

            entries.append(ChecksumEntry(relative_path=relative_path, sha256=digest))
            seen_paths.add(relative_path)

        except ChecksumError as exc:
            malformed.append(f"line {line_number}: {exc}")

    if malformed:
        raise InvalidChecksumFileError("; ".join(malformed))

    return tuple(entries)


def read_checksums_file(path: Path) -> tuple[ChecksumEntry, ...]:
    """Read and parse a `checksums.txt` file."""

    if not path.is_file():
        raise FileNotFoundError(path)

    return parse_checksums_text(path.read_text(encoding="utf-8"))


def format_checksums(entries: Iterable[ChecksumEntry]) -> str:
    """Return deterministic sha256sum-style text."""

    sorted_entries = sorted(entries, key=lambda item: item.relative_path)
    lines = [f"{entry.sha256}  {entry.relative_path}" for entry in sorted_entries]
    return "\n".join(lines) + ("\n" if lines else "")


def write_checksums_file(
    capsule_root: Path,
    output_path: Path | None = None,
    *,
    exclude_paths: Iterable[str] = DEFAULT_EXCLUDED_CHECKSUM_PATHS,
) -> Path:
    """
    Generate and write `checksums.txt` for an extracted capsule directory.

    Returns the written file path.
    """

    root = capsule_root.resolve()
    output = output_path or root / CHECKSUM_FILENAME
    entries = build_checksum_entries(root, exclude_paths=exclude_paths)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(format_checksums(entries), encoding="utf-8")
    return output


def build_checksum_entries(
    capsule_root: Path,
    *,
    exclude_paths: Iterable[str] = DEFAULT_EXCLUDED_CHECKSUM_PATHS,
) -> tuple[ChecksumEntry, ...]:
    """Build checksum entries for all regular files below `capsule_root`."""

    root = capsule_root.resolve()

    if not root.is_dir():
        raise NotADirectoryError(root)

    excluded = {normalize_relative_path(path) for path in exclude_paths}
    entries: list[ChecksumEntry] = []

    for file_path in iter_capsule_files(root, exclude_paths=excluded):
        relative_path = to_safe_relative_path(root, file_path)
        entries.append(
            ChecksumEntry(
                relative_path=relative_path,
                sha256=sha256_file(file_path),
            )
        )

    return tuple(sorted(entries, key=lambda item: item.relative_path))


def verify_capsule_checksums(
    capsule_root: Path,
    *,
    checksums_path: Path | None = None,
    allow_extra_files: bool = False,
    exclude_paths: Iterable[str] = DEFAULT_EXCLUDED_CHECKSUM_PATHS,
) -> ChecksumReport:
    """
    Verify extracted capsule contents against `checksums.txt`.

    This function performs no signature verification. Signature checks belong in
    `kx_agent.capsules.signature`.
    """

    root = capsule_root.resolve()

    if not root.is_dir():
        raise NotADirectoryError(root)

    checksum_file = checksums_path or root / CHECKSUM_FILENAME

    try:
        expected_entries = read_checksums_file(checksum_file)
    except InvalidChecksumFileError as exc:
        return ChecksumReport(ok=False, malformed=(str(exc),))

    expected_by_path: dict[str, str] = {
        entry.relative_path: entry.sha256.lower()
        for entry in expected_entries
    }

    excluded = {normalize_relative_path(path) for path in exclude_paths}
    actual_paths = {
        to_safe_relative_path(root, file_path)
        for file_path in iter_capsule_files(root, exclude_paths=excluded)
    }

    expected_paths = set(expected_by_path)

    missing = tuple(sorted(expected_paths - actual_paths))
    extra = tuple(sorted(actual_paths - expected_paths)) if not allow_extra_files else ()

    mismatched: list[ChecksumMismatch] = []

    for relative_path in sorted(expected_paths & actual_paths):
        file_path = safe_join(root, relative_path)
        actual_sha256 = sha256_file(file_path).lower()
        expected_sha256 = expected_by_path[relative_path]

        if actual_sha256 != expected_sha256:
            mismatched.append(
                ChecksumMismatch(
                    relative_path=relative_path,
                    expected_sha256=expected_sha256,
                    actual_sha256=actual_sha256,
                )
            )

    ok = not missing and not extra and not mismatched

    return ChecksumReport(
        ok=ok,
        checked=len(expected_paths & actual_paths),
        missing=missing,
        extra=extra,
        mismatched=tuple(mismatched),
    )


def verify_entries(
    capsule_root: Path,
    expected_entries: Iterable[ChecksumEntry],
) -> ChecksumReport:
    """Verify a provided list of checksum entries against a capsule root."""

    root = capsule_root.resolve()

    if not root.is_dir():
        raise NotADirectoryError(root)

    missing: list[str] = []
    mismatched: list[ChecksumMismatch] = []
    checked = 0

    for entry in sorted(expected_entries, key=lambda item: item.relative_path):
        file_path = safe_join(root, entry.relative_path)

        if not file_path.is_file():
            missing.append(entry.relative_path)
            continue

        checked += 1
        actual_sha256 = sha256_file(file_path).lower()
        expected_sha256 = entry.sha256.lower()

        if actual_sha256 != expected_sha256:
            mismatched.append(
                ChecksumMismatch(
                    relative_path=entry.relative_path,
                    expected_sha256=expected_sha256,
                    actual_sha256=actual_sha256,
                )
            )

    ok = not missing and not mismatched

    return ChecksumReport(
        ok=ok,
        checked=checked,
        missing=tuple(missing),
        mismatched=tuple(mismatched),
    )


def entries_to_mapping(entries: Iterable[ChecksumEntry]) -> Mapping[str, str]:
    """Return `{relative_path: sha256}` for checksum entries."""

    return {entry.relative_path: entry.sha256.lower() for entry in entries}


def iter_capsule_files(
    capsule_root: Path,
    *,
    exclude_paths: Iterable[str] = DEFAULT_EXCLUDED_CHECKSUM_PATHS,
) -> Iterator[Path]:
    """Yield regular files below `capsule_root` in deterministic order."""

    root = capsule_root.resolve()
    excluded = {normalize_relative_path(path) for path in exclude_paths}

    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue

        relative_path = to_safe_relative_path(root, file_path)

        if relative_path in excluded:
            continue

        yield file_path


def safe_join(root: Path, relative_path: str) -> Path:
    """
    Join `root` and a safe relative POSIX path.

    Raises if the resulting path escapes `root`.
    """

    normalized = normalize_relative_path(relative_path)
    root_resolved = root.resolve()
    candidate = (root_resolved / normalized).resolve()

    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise UnsafeChecksumPathError(
            f"Checksum path escapes capsule root: {relative_path!r}"
        ) from exc

    return candidate


def to_safe_relative_path(root: Path, file_path: Path) -> str:
    """Return a normalized POSIX relative path from root to file."""

    root_resolved = root.resolve()
    file_resolved = file_path.resolve()

    try:
        relative = file_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise UnsafeChecksumPathError(
            f"File is outside capsule root: {file_path}"
        ) from exc

    return normalize_relative_path(relative.as_posix())


def normalize_relative_path(path: str) -> str:
    """
    Normalize and validate a capsule-relative POSIX path.

    This function intentionally rejects:
    - empty paths
    - absolute paths
    - path traversal with `..`
    - current-directory segments such as `.`
    - raw non-canonical paths such as `metadata/./build.json`

    Rejecting raw `.` segments keeps checksum manifests deterministic and avoids
    ambiguous equivalents for the same capsule file.
    """

    raw = str(path).replace("\\", "/").strip()

    if not raw:
        raise UnsafeChecksumPathError("Checksum path cannot be empty.")

    if raw == ".":
        raise UnsafeChecksumPathError("Checksum path cannot be current directory.")

    if raw.startswith("./"):
        raise UnsafeChecksumPathError(f"Current-directory segments are not allowed: {path!r}")

    if raw.endswith("/."):
        raise UnsafeChecksumPathError(f"Current-directory segments are not allowed: {path!r}")

    if "/./" in raw:
        raise UnsafeChecksumPathError(f"Current-directory segments are not allowed: {path!r}")

    raw_parts = raw.split("/")

    if any(part in {"", ".", ".."} for part in raw_parts):
        raise UnsafeChecksumPathError(f"Unsafe relative path: {path!r}")

    pure = PurePosixPath(raw)

    if pure.is_absolute():
        raise UnsafeChecksumPathError(f"Absolute paths are not allowed: {path!r}")

    normalized = pure.as_posix()

    if normalized.startswith("../") or normalized == "..":
        raise UnsafeChecksumPathError(f"Path traversal is not allowed: {path!r}")

    if normalized != raw:
        raise UnsafeChecksumPathError(
            f"Checksum path must already be normalized POSIX relative path: {path!r}"
        )

    return normalized


def validate_relative_path(path: str) -> None:
    """Validate a checksum relative path."""

    normalize_relative_path(path)


def _split_checksum_line(line: str) -> tuple[str, str]:
    """Split a sha256sum-style line into digest and relative path."""

    if " " not in line and "\t" not in line:
        raise InvalidChecksumFileError("expected '<sha256>  <relative_path>'")

    parts = line.split(maxsplit=1)

    if len(parts) != 2:
        raise InvalidChecksumFileError("expected digest and relative path")

    digest, raw_path = parts
    digest = digest.strip().lower()
    raw_path = raw_path.strip()

    if raw_path.startswith("*"):
        raw_path = raw_path[1:]

    if not SHA256_HEX_RE.fullmatch(digest):
        raise InvalidChecksumFileError(f"invalid SHA-256 digest {digest!r}")

    return digest, raw_path