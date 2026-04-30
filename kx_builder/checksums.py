"""
Konnaxion Capsule Builder checksum utilities.

This module generates and verifies deterministic SHA-256 checksums for
Konnaxion Capsule contents.

Canonical capsule rule:

    checksums.txt = digest list for capsule contents
    signature.sig  = signature over manifest/checksums, generated after checksums

Therefore, checksum generation excludes checksums.txt and signature.sig by
default, while verification can read checksums.txt and validate every listed
file.

This module does not sign capsules. Signing belongs in kx_builder/signature.py.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

from kx_shared.konnaxion_constants import (
    CAPSULE_REQUIRED_ROOT_ENTRIES,
    CAPSULE_ROOT_DIRS,
    CAPSULE_ROOT_FILES,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HASH_ALGORITHM = "sha256"
DEFAULT_CHUNK_SIZE = 1024 * 1024

CHECKSUMS_FILENAME = "checksums.txt"
SIGNATURE_FILENAME = "signature.sig"

DEFAULT_EXCLUDED_FILENAMES = frozenset(
    {
        CHECKSUMS_FILENAME,
        SIGNATURE_FILENAME,
    }
)

DEFAULT_EXCLUDED_DIRS = frozenset(
    {
        "__pycache__",
        ".git",
        ".hg",
        ".svn",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".DS_Store",
    }
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ChecksumError(Exception):
    """Base class for checksum errors."""


class ChecksumFormatError(ChecksumError):
    """Raised when checksums.txt has invalid syntax."""


class ChecksumVerificationError(ChecksumError):
    """Raised when checksum verification fails."""


class CapsuleLayoutError(ChecksumError):
    """Raised when capsule layout is incomplete or unsafe."""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ChecksumStatus(StrEnum):
    """Checksum verification status."""

    PASS = "PASS"
    FAIL = "FAIL"
    MISSING = "MISSING"
    EXTRA = "EXTRA"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ChecksumEntry:
    """One checksum line."""

    sha256: str
    path: str

    def __post_init__(self) -> None:
        normalized_path = normalize_relative_path(self.path)
        normalized_hash = self.sha256.strip().lower()

        if len(normalized_hash) != 64:
            raise ChecksumFormatError(f"Invalid sha256 length for {self.path}")

        try:
            int(normalized_hash, 16)
        except ValueError as exc:
            raise ChecksumFormatError(f"Invalid sha256 hex digest for {self.path}") from exc

        object.__setattr__(self, "sha256", normalized_hash)
        object.__setattr__(self, "path", normalized_path)

    def to_line(self) -> str:
        """Render one checksums.txt line."""
        return f"{self.sha256}  {self.path}"

    @classmethod
    def from_line(cls, line: str) -> "ChecksumEntry":
        """Parse one checksums.txt line."""
        stripped = line.strip()

        if not stripped:
            raise ChecksumFormatError("Empty checksum line.")

        if stripped.startswith("#"):
            raise ChecksumFormatError("Comment lines are not checksum entries.")

        parts = stripped.split(maxsplit=1)
        if len(parts) != 2:
            raise ChecksumFormatError(f"Invalid checksum line: {line!r}")

        digest, path = parts
        return cls(sha256=digest, path=path.strip())


@dataclass(frozen=True)
class ChecksumManifest:
    """In-memory representation of checksums.txt."""

    entries: tuple[ChecksumEntry, ...] = field(default_factory=tuple)
    algorithm: str = HASH_ALGORITHM

    def __post_init__(self) -> None:
        if self.algorithm != HASH_ALGORITHM:
            raise ChecksumFormatError(f"Unsupported checksum algorithm: {self.algorithm}")

        sorted_entries = tuple(sorted(self.entries, key=lambda entry: entry.path))
        paths = [entry.path for entry in sorted_entries]

        if len(paths) != len(set(paths)):
            duplicates = sorted(path for path in set(paths) if paths.count(path) > 1)
            raise ChecksumFormatError(f"Duplicate checksum paths: {duplicates}")

        object.__setattr__(self, "entries", sorted_entries)

    @property
    def by_path(self) -> dict[str, ChecksumEntry]:
        """Return checksum entries indexed by relative path."""
        return {entry.path: entry for entry in self.entries}

    def to_text(self) -> str:
        """Render deterministic checksums.txt content."""
        lines = [entry.to_line() for entry in self.entries]
        return "\n".join(lines) + ("\n" if lines else "")

    @classmethod
    def from_text(cls, text: str) -> "ChecksumManifest":
        """Parse checksums.txt content."""
        entries: list[ChecksumEntry] = []

        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            try:
                entries.append(ChecksumEntry.from_line(stripped))
            except ChecksumFormatError as exc:
                raise ChecksumFormatError(f"Invalid checksums.txt line {line_number}: {exc}") from exc

        return cls(entries=tuple(entries))

    @classmethod
    def from_file(cls, path: Path) -> "ChecksumManifest":
        """Read checksums.txt from disk."""
        return cls.from_text(path.read_text(encoding="utf-8"))

    def write(self, path: Path) -> Path:
        """Write checksums.txt to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_text(), encoding="utf-8")
        return path


@dataclass(frozen=True)
class ChecksumVerificationItem:
    """Verification result for one file."""

    path: str
    status: ChecksumStatus
    expected_sha256: str | None = None
    actual_sha256: str | None = None
    message: str | None = None

    @property
    def passed(self) -> bool:
        """Return True if this item passed verification."""
        return self.status == ChecksumStatus.PASS

    def to_dict(self) -> dict[str, str | bool | None]:
        """Serialize to primitive dict."""
        return {
            "path": self.path,
            "status": self.status.value,
            "expected_sha256": self.expected_sha256,
            "actual_sha256": self.actual_sha256,
            "message": self.message,
            "passed": self.passed,
        }


@dataclass(frozen=True)
class ChecksumVerificationResult:
    """Aggregate checksum verification result."""

    root: Path
    items: tuple[ChecksumVerificationItem, ...]
    checked_extra_files: bool = True

    @property
    def passed(self) -> bool:
        """Return True if all items passed."""
        return all(item.passed for item in self.items)

    @property
    def failures(self) -> tuple[ChecksumVerificationItem, ...]:
        """Return non-passing verification items."""
        return tuple(item for item in self.items if not item.passed)

    def assert_passed(self) -> None:
        """Raise if verification failed."""
        if not self.passed:
            failed = ", ".join(f"{item.path}:{item.status.value}" for item in self.failures)
            raise ChecksumVerificationError(f"Checksum verification failed: {failed}")

    def to_dict(self) -> dict[str, object]:
        """Serialize to primitive dict."""
        return {
            "root": str(self.root),
            "passed": self.passed,
            "checked_extra_files": self.checked_extra_files,
            "items": [item.to_dict() for item in self.items],
        }


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def normalize_relative_path(path: str | Path) -> str:
    """
    Normalize a checksum path.

    Checksum paths must be POSIX-style, relative, and must not escape the capsule
    root.
    """
    raw = str(path).replace("\\", "/").strip()

    if not raw:
        raise ChecksumFormatError("Checksum path is empty.")

    candidate = Path(raw)

    if candidate.is_absolute():
        raise ChecksumFormatError(f"Checksum path must be relative: {path}")

    parts = tuple(part for part in raw.split("/") if part not in {"", "."})

    if any(part == ".." for part in parts):
        raise ChecksumFormatError(f"Checksum path must not contain '..': {path}")

    return "/".join(parts)


def relative_to_root(path: Path, root: Path) -> str:
    """Return normalized POSIX relative path from root."""
    return normalize_relative_path(path.relative_to(root).as_posix())


def is_excluded_path(
    path: Path,
    *,
    root: Path,
    excluded_filenames: frozenset[str] = DEFAULT_EXCLUDED_FILENAMES,
    excluded_dirs: frozenset[str] = DEFAULT_EXCLUDED_DIRS,
) -> bool:
    """Return True if path should be excluded from checksum generation."""
    rel_parts = path.relative_to(root).parts

    if any(part in excluded_dirs for part in rel_parts):
        return True

    return path.name in excluded_filenames


def iter_capsule_files(
    root: Path,
    *,
    excluded_filenames: frozenset[str] = DEFAULT_EXCLUDED_FILENAMES,
    excluded_dirs: frozenset[str] = DEFAULT_EXCLUDED_DIRS,
) -> Iterator[Path]:
    """
    Yield capsule files in deterministic relative-path order.

    Excludes checksums.txt and signature.sig by default.
    """
    if not root.exists():
        raise CapsuleLayoutError(f"Capsule root does not exist: {root}")

    if not root.is_dir():
        raise CapsuleLayoutError(f"Capsule root is not a directory: {root}")

    files: list[Path] = []

    for current_root, dirnames, filenames in os.walk(root):
        current = Path(current_root)

        dirnames[:] = sorted(
            dirname for dirname in dirnames if dirname not in excluded_dirs
        )

        for filename in sorted(filenames):
            path = current / filename
            if is_excluded_path(
                path,
                root=root,
                excluded_filenames=excluded_filenames,
                excluded_dirs=excluded_dirs,
            ):
                continue
            files.append(path)

    yield from sorted(files, key=lambda item: relative_to_root(item, root))


# ---------------------------------------------------------------------------
# Layout validation
# ---------------------------------------------------------------------------

def validate_capsule_layout(root: Path) -> None:
    """
    Validate required capsule root files/directories before checksum generation.

    checksums.txt and signature.sig may be absent during generation because they
    are produced after the rest of the capsule contents.
    """
    if not root.exists():
        raise CapsuleLayoutError(f"Capsule root does not exist: {root}")

    if not root.is_dir():
        raise CapsuleLayoutError(f"Capsule root is not a directory: {root}")

    missing: list[str] = []

    for entry in CAPSULE_REQUIRED_ROOT_ENTRIES:
        if entry in {CHECKSUMS_FILENAME, SIGNATURE_FILENAME}:
            continue

        if not (root / entry).exists():
            missing.append(entry)

    if missing:
        raise CapsuleLayoutError(f"Capsule root is missing required entries: {missing}")

    for directory in CAPSULE_ROOT_DIRS:
        candidate = root / directory
        if candidate.exists() and not candidate.is_dir():
            raise CapsuleLayoutError(f"Capsule layout entry must be a directory: {directory}")

    for filename in CAPSULE_ROOT_FILES:
        if filename in {CHECKSUMS_FILENAME, SIGNATURE_FILENAME}:
            continue

        candidate = root / filename
        if candidate.exists() and not candidate.is_file():
            raise CapsuleLayoutError(f"Capsule layout entry must be a file: {filename}")


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def sha256_file(path: Path, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    """Return SHA-256 hex digest for a file."""
    if not path.is_file():
        raise ChecksumError(f"Cannot hash non-file path: {path}")

    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)

    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Return SHA-256 hex digest for bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str, *, encoding: str = "utf-8") -> str:
    """Return SHA-256 hex digest for text."""
    return sha256_bytes(text.encode(encoding))


# ---------------------------------------------------------------------------
# Manifest generation and IO
# ---------------------------------------------------------------------------

def generate_checksum_manifest(
    root: Path,
    *,
    validate_layout: bool = True,
    excluded_filenames: frozenset[str] = DEFAULT_EXCLUDED_FILENAMES,
    excluded_dirs: frozenset[str] = DEFAULT_EXCLUDED_DIRS,
) -> ChecksumManifest:
    """Generate checksum manifest for capsule root."""
    root = root.resolve()

    if validate_layout:
        validate_capsule_layout(root)

    entries = tuple(
        ChecksumEntry(
            sha256=sha256_file(path),
            path=relative_to_root(path, root),
        )
        for path in iter_capsule_files(
            root,
            excluded_filenames=excluded_filenames,
            excluded_dirs=excluded_dirs,
        )
    )

    return ChecksumManifest(entries=entries)


def write_checksums(
    root: Path,
    *,
    output_path: Path | None = None,
    validate_layout: bool = True,
) -> Path:
    """
    Generate and write checksums.txt for capsule root.

    Returns the written path.
    """
    root = root.resolve()
    manifest = generate_checksum_manifest(root, validate_layout=validate_layout)
    target = output_path or (root / CHECKSUMS_FILENAME)
    return manifest.write(target)


def read_checksums(path: Path) -> ChecksumManifest:
    """Read a checksums.txt file."""
    return ChecksumManifest.from_file(path)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_checksum_manifest(
    root: Path,
    manifest: ChecksumManifest,
    *,
    check_extra_files: bool = True,
    excluded_filenames: frozenset[str] = DEFAULT_EXCLUDED_FILENAMES,
    excluded_dirs: frozenset[str] = DEFAULT_EXCLUDED_DIRS,
) -> ChecksumVerificationResult:
    """Verify files under root against a checksum manifest."""
    root = root.resolve()
    items: list[ChecksumVerificationItem] = []
    expected = manifest.by_path

    for rel_path, entry in expected.items():
        absolute_path = root / rel_path

        if not absolute_path.exists():
            items.append(
                ChecksumVerificationItem(
                    path=rel_path,
                    status=ChecksumStatus.MISSING,
                    expected_sha256=entry.sha256,
                    actual_sha256=None,
                    message="Listed file is missing.",
                )
            )
            continue

        if not absolute_path.is_file():
            items.append(
                ChecksumVerificationItem(
                    path=rel_path,
                    status=ChecksumStatus.ERROR,
                    expected_sha256=entry.sha256,
                    actual_sha256=None,
                    message="Listed path is not a file.",
                )
            )
            continue

        actual = sha256_file(absolute_path)
        status = ChecksumStatus.PASS if actual == entry.sha256 else ChecksumStatus.FAIL

        items.append(
            ChecksumVerificationItem(
                path=rel_path,
                status=status,
                expected_sha256=entry.sha256,
                actual_sha256=actual,
                message=None if status == ChecksumStatus.PASS else "Digest mismatch.",
            )
        )

    if check_extra_files:
        actual_paths = {
            relative_to_root(path, root)
            for path in iter_capsule_files(
                root,
                excluded_filenames=excluded_filenames,
                excluded_dirs=excluded_dirs,
            )
        }

        extra_paths = sorted(actual_paths.difference(expected.keys()))

        for rel_path in extra_paths:
            items.append(
                ChecksumVerificationItem(
                    path=rel_path,
                    status=ChecksumStatus.EXTRA,
                    expected_sha256=None,
                    actual_sha256=sha256_file(root / rel_path),
                    message="File exists but is not listed in checksums.txt.",
                )
            )

    return ChecksumVerificationResult(
        root=root,
        items=tuple(sorted(items, key=lambda item: item.path)),
        checked_extra_files=check_extra_files,
    )


def verify_checksums(
    root: Path,
    *,
    checksums_path: Path | None = None,
    check_extra_files: bool = True,
) -> ChecksumVerificationResult:
    """Read checksums.txt and verify capsule root."""
    root = root.resolve()
    manifest_path = checksums_path or (root / CHECKSUMS_FILENAME)

    if not manifest_path.exists():
        raise ChecksumVerificationError(f"checksums.txt does not exist: {manifest_path}")

    manifest = read_checksums(manifest_path)
    return verify_checksum_manifest(
        root,
        manifest,
        check_extra_files=check_extra_files,
    )


def assert_checksums_valid(
    root: Path,
    *,
    checksums_path: Path | None = None,
    check_extra_files: bool = True,
) -> ChecksumVerificationResult:
    """Verify checksums and raise if any item fails."""
    result = verify_checksums(
        root,
        checksums_path=checksums_path,
        check_extra_files=check_extra_files,
    )
    result.assert_passed()
    return result


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChecksumDiff:
    """Difference between two checksum manifests."""

    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]
    unchanged: tuple[str, ...]

    @property
    def has_changes(self) -> bool:
        """Return True if any entry changed."""
        return bool(self.added or self.removed or self.changed)

    def to_dict(self) -> dict[str, list[str] | bool]:
        """Serialize to primitive dict."""
        return {
            "added": list(self.added),
            "removed": list(self.removed),
            "changed": list(self.changed),
            "unchanged": list(self.unchanged),
            "has_changes": self.has_changes,
        }


def diff_manifests(old: ChecksumManifest, new: ChecksumManifest) -> ChecksumDiff:
    """Compare two checksum manifests."""
    old_by_path = old.by_path
    new_by_path = new.by_path

    old_paths = set(old_by_path)
    new_paths = set(new_by_path)

    added = tuple(sorted(new_paths - old_paths))
    removed = tuple(sorted(old_paths - new_paths))

    common = sorted(old_paths & new_paths)
    changed = tuple(
        path
        for path in common
        if old_by_path[path].sha256 != new_by_path[path].sha256
    )
    unchanged = tuple(
        path
        for path in common
        if old_by_path[path].sha256 == new_by_path[path].sha256
    )

    return ChecksumDiff(
        added=added,
        removed=removed,
        changed=changed,
        unchanged=unchanged,
    )


# ---------------------------------------------------------------------------
# CLI-friendly facade
# ---------------------------------------------------------------------------

class ChecksumBuilder:
    """Builder facade for checksum generation and verification."""

    def generate(self, root: Path, *, validate_layout: bool = True) -> ChecksumManifest:
        """Generate a checksum manifest."""
        return generate_checksum_manifest(root, validate_layout=validate_layout)

    def write(self, root: Path, *, validate_layout: bool = True) -> Path:
        """Generate and write checksums.txt."""
        return write_checksums(root, validate_layout=validate_layout)

    def verify(self, root: Path, *, check_extra_files: bool = True) -> ChecksumVerificationResult:
        """Verify checksums.txt under root."""
        return verify_checksums(root, check_extra_files=check_extra_files)

    def assert_valid(self, root: Path, *, check_extra_files: bool = True) -> ChecksumVerificationResult:
        """Verify checksums.txt and raise on failure."""
        return assert_checksums_valid(root, check_extra_files=check_extra_files)


__all__ = [
    "CHECKSUMS_FILENAME",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_EXCLUDED_DIRS",
    "DEFAULT_EXCLUDED_FILENAMES",
    "HASH_ALGORITHM",
    "SIGNATURE_FILENAME",
    "CapsuleLayoutError",
    "ChecksumBuilder",
    "ChecksumDiff",
    "ChecksumEntry",
    "ChecksumError",
    "ChecksumFormatError",
    "ChecksumManifest",
    "ChecksumStatus",
    "ChecksumVerificationError",
    "ChecksumVerificationItem",
    "ChecksumVerificationResult",
    "assert_checksums_valid",
    "diff_manifests",
    "generate_checksum_manifest",
    "is_excluded_path",
    "iter_capsule_files",
    "normalize_relative_path",
    "read_checksums",
    "relative_to_root",
    "sha256_bytes",
    "sha256_file",
    "sha256_text",
    "validate_capsule_layout",
    "verify_checksum_manifest",
    "verify_checksums",
    "write_checksums",
]
