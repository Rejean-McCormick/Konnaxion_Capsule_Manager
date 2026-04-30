"""
Tests for Konnaxion Capsule verification.

These tests focus on the verification contract that every `.kxcap` must satisfy:
- required root files exist
- checksums are deterministic and strict
- checksum paths cannot escape the capsule root
- tampered files are detected
- secret-bearing files are rejected by verification policy
- verifier integration is exercised when `kx_agent.capsules.verifier` exists

The tests intentionally avoid Docker, network, and privileged Agent operations.
"""

from __future__ import annotations

import importlib
import tarfile
from pathlib import Path
from typing import Any

import pytest

from kx_agent.capsules.checksums import (
    CHECKSUM_FILENAME,
    SIGNATURE_FILENAME,
    ChecksumEntry,
    InvalidChecksumFileError,
    UnsafeChecksumPathError,
    build_checksum_entries,
    format_checksums,
    normalize_relative_path,
    parse_checksums_text,
    sha256_file,
    verify_capsule_checksums,
    write_checksums_file,
)


REQUIRED_CAPSULE_ROOT_FILES = (
    "manifest.yaml",
    "docker-compose.capsule.yml",
    "checksums.txt",
    "signature.sig",
)

REQUIRED_CAPSULE_ROOT_DIRS = (
    "images",
    "profiles",
    "env-templates",
    "migrations",
    "healthchecks",
    "policies",
    "metadata",
)

FORBIDDEN_SECRET_FILES = (
    ".env",
    "backend/.env",
    "frontend/.env.local",
    "secrets/postgres_password.txt",
    "keys/id_rsa",
    "certs/private.key",
)


@pytest.fixture()
def capsule_root(tmp_path: Path) -> Path:
    """Create a minimal extracted Konnaxion Capsule layout."""

    root = tmp_path / "capsule"
    root.mkdir()

    for directory in REQUIRED_CAPSULE_ROOT_DIRS:
        (root / directory).mkdir(parents=True)

    (root / "manifest.yaml").write_text(
        "\n".join(
            [
                "schema_version: kxcap/v1",
                "capsule_id: konnaxion-v14-demo-2026.04.30",
                "capsule_version: 2026.04.30-demo.1",
                "app_name: Konnaxion",
                "app_version: v14",
                "param_version: kx-param-2026.04.30",
                "channel: demo",
                "services:",
                "  - traefik",
                "  - frontend-next",
                "  - django-api",
                "  - postgres",
                "  - redis",
                "  - celeryworker",
                "  - celerybeat",
                "  - media-nginx",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (root / "docker-compose.capsule.yml").write_text(
        "\n".join(
            [
                "services:",
                "  traefik:",
                "    image: traefik:latest",
                "  frontend-next:",
                "    image: konnaxion/frontend-next:v14",
                "  django-api:",
                "    image: konnaxion/django-api:v14",
                "  postgres:",
                "    image: postgres:16",
                "  redis:",
                "    image: redis:7",
                "  celeryworker:",
                "    image: konnaxion/django-api:v14",
                "  celerybeat:",
                "    image: konnaxion/django-api:v14",
                "  media-nginx:",
                "    image: nginx:stable",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (root / "profiles" / "intranet_private.yaml").write_text(
        "\n".join(
            [
                "schema_version: kx-network-profile/v1",
                "profile:",
                "  name: intranet_private",
                "  default: true",
                "exposure:",
                "  mode: private",
                "canonical_env:",
                "  KX_NETWORK_PROFILE: intranet_private",
                "  KX_EXPOSURE_MODE: private",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (root / "env-templates" / "django.env.template").write_text(
        "DJANGO_SECRET_KEY=<GENERATED_ON_INSTALL>\n",
        encoding="utf-8",
    )
    (root / "env-templates" / "postgres.env.template").write_text(
        "POSTGRES_PASSWORD=<GENERATED_ON_INSTALL>\n",
        encoding="utf-8",
    )
    (root / "env-templates" / "redis.env.template").write_text(
        "REDIS_URL=redis://redis:6379/0\n",
        encoding="utf-8",
    )
    (root / "env-templates" / "frontend.env.template").write_text(
        "NEXT_PUBLIC_API_BASE=<GENERATED_FROM_PROFILE>\n",
        encoding="utf-8",
    )

    (root / "healthchecks" / "http.yaml").write_text(
        "routes:\n  - /\n  - /api/\n",
        encoding="utf-8",
    )
    (root / "policies" / "security_gate.yaml").write_text(
        "required: true\n",
        encoding="utf-8",
    )
    (root / "metadata" / "build.json").write_text(
        '{"builder":"kx-builder","app_version":"v14"}\n',
        encoding="utf-8",
    )
    (root / "migrations" / "run.sh").write_text(
        "#!/usr/bin/env sh\npython manage.py migrate\n",
        encoding="utf-8",
    )
    (root / "images" / "frontend-next.oci.tar").write_bytes(
        b"frontend image placeholder"
    )
    (root / "images" / "django-api.oci.tar").write_bytes(
        b"django image placeholder"
    )

    write_checksums_file(root)
    (root / SIGNATURE_FILENAME).write_bytes(b"signature placeholder")

    return root


def test_minimal_capsule_fixture_has_required_layout(capsule_root: Path) -> None:
    for relative_path in REQUIRED_CAPSULE_ROOT_FILES:
        assert (capsule_root / relative_path).exists(), relative_path

    for relative_path in REQUIRED_CAPSULE_ROOT_DIRS:
        assert (capsule_root / relative_path).is_dir(), relative_path


def test_sha256_file_is_deterministic(tmp_path: Path) -> None:
    file_path = tmp_path / "data.txt"
    file_path.write_text("konnaxion\n", encoding="utf-8")

    first = sha256_file(file_path)
    second = sha256_file(file_path)

    assert first == second
    assert len(first) == 64


def test_parse_checksums_text_accepts_sha256sum_format() -> None:
    text = (
        "# comment\n"
        + ("a" * 64)
        + "  manifest.yaml\n"
        + ("b" * 64)
        + " *docker-compose.capsule.yml\n"
    )

    entries = parse_checksums_text(text)

    assert entries == (
        ChecksumEntry(relative_path="manifest.yaml", sha256="a" * 64),
        ChecksumEntry(relative_path="docker-compose.capsule.yml", sha256="b" * 64),
    )


def test_parse_checksums_text_rejects_invalid_digest() -> None:
    with pytest.raises(InvalidChecksumFileError):
        parse_checksums_text("not-a-digest  manifest.yaml\n")


def test_parse_checksums_text_rejects_duplicate_paths() -> None:
    text = (
        ("a" * 64)
        + "  manifest.yaml\n"
        + ("b" * 64)
        + "  manifest.yaml\n"
    )

    with pytest.raises(InvalidChecksumFileError):
        parse_checksums_text(text)


@pytest.mark.parametrize(
    "relative_path",
    [
        "../manifest.yaml",
        "/etc/passwd",
        "metadata/../../secret",
        "",
        ".",
        "metadata/./build.json",
    ],
)
def test_checksum_paths_must_be_safe(relative_path: str) -> None:
    with pytest.raises(UnsafeChecksumPathError):
        normalize_relative_path(relative_path)


def test_build_checksum_entries_excludes_checksum_and_signature(
    capsule_root: Path,
) -> None:
    entries = build_checksum_entries(capsule_root)
    paths = {entry.relative_path for entry in entries}

    assert CHECKSUM_FILENAME not in paths
    assert SIGNATURE_FILENAME not in paths
    assert "manifest.yaml" in paths
    assert "docker-compose.capsule.yml" in paths


def test_format_checksums_is_deterministic() -> None:
    entries = (
        ChecksumEntry(relative_path="z.txt", sha256="f" * 64),
        ChecksumEntry(relative_path="a.txt", sha256="a" * 64),
    )

    assert format_checksums(entries).splitlines() == [
        ("a" * 64) + "  a.txt",
        ("f" * 64) + "  z.txt",
    ]


def test_verify_capsule_checksums_passes_for_untampered_capsule(
    capsule_root: Path,
) -> None:
    report = verify_capsule_checksums(capsule_root)

    assert report.ok is True
    assert report.failure_count == 0
    assert report.missing == ()
    assert report.extra == ()
    assert report.mismatched == ()


def test_verify_capsule_checksums_detects_tampering(capsule_root: Path) -> None:
    (capsule_root / "manifest.yaml").write_text("tampered: true\n", encoding="utf-8")

    report = verify_capsule_checksums(capsule_root)

    assert report.ok is False
    assert report.mismatched
    assert report.mismatched[0].relative_path == "manifest.yaml"


def test_verify_capsule_checksums_detects_missing_file(capsule_root: Path) -> None:
    (capsule_root / "metadata" / "build.json").unlink()

    report = verify_capsule_checksums(capsule_root)

    assert report.ok is False
    assert "metadata/build.json" in report.missing


def test_verify_capsule_checksums_detects_extra_file(capsule_root: Path) -> None:
    (capsule_root / "metadata" / "extra.json").write_text("{}", encoding="utf-8")

    report = verify_capsule_checksums(capsule_root)

    assert report.ok is False
    assert "metadata/extra.json" in report.extra


def test_verify_capsule_checksums_can_allow_extra_files(capsule_root: Path) -> None:
    (capsule_root / "metadata" / "extra.json").write_text("{}", encoding="utf-8")

    report = verify_capsule_checksums(capsule_root, allow_extra_files=True)

    assert report.ok is True
    assert report.extra == ()


@pytest.mark.parametrize("relative_path", FORBIDDEN_SECRET_FILES)
def test_capsule_policy_rejects_secret_bearing_paths(
    capsule_root: Path,
    relative_path: str,
) -> None:
    """
    Verification policy must reject these paths.

    This test uses the verifier module when available. Until that module exists
    or supports policy-level secret rejection, it is skipped instead of blocking
    checksum-only development.
    """

    secret_file = capsule_root / relative_path
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    secret_file.write_text("SECRET=value\n", encoding="utf-8")
    write_checksums_file(capsule_root)

    verifier = import_optional_verifier()

    if verifier is None:
        pytest.skip("kx_agent.capsules.verifier is not generated yet.")

    verify_func = getattr(verifier, "verify_extracted_capsule", None)

    if verify_func is None:
        pytest.skip("verify_extracted_capsule is not implemented yet.")

    result = verify_func(capsule_root)

    if hasattr(result, "ok"):
        assert result.ok is False
    elif isinstance(result, dict):
        assert result.get("ok") is False
    else:
        pytest.fail("Verifier returned unsupported result type.")


def test_optional_capsule_verifier_accepts_valid_capsule(capsule_root: Path) -> None:
    """
    Integration test for `kx_agent.capsules.verifier`.

    The checksum tests above always run. This test activates once the verifier
    module exposes `verify_extracted_capsule`.
    """

    verifier = import_optional_verifier()

    if verifier is None:
        pytest.skip("kx_agent.capsules.verifier is not generated yet.")

    verify_func = getattr(verifier, "verify_extracted_capsule", None)

    if verify_func is None:
        pytest.skip("verify_extracted_capsule is not implemented yet.")

    result = verify_func(capsule_root)

    if hasattr(result, "ok"):
        assert result.ok is True
    elif isinstance(result, dict):
        assert result.get("ok") is True
    else:
        pytest.fail("Verifier returned unsupported result type.")


def test_optional_capsule_archive_verifier_accepts_kxcap_file(
    capsule_root: Path,
    tmp_path: Path,
) -> None:
    """
    Integration test for archive-level `.kxcap` verification.

    The MVP physical format is tar-compatible for this test fixture. The test is
    skipped until the verifier module exposes `verify_capsule_archive`.
    """

    archive_path = tmp_path / "konnaxion-v14-demo-2026.04.30.kxcap"

    with tarfile.open(archive_path, "w") as tar:
        for path in sorted(capsule_root.rglob("*")):
            tar.add(path, arcname=path.relative_to(capsule_root).as_posix())

    verifier = import_optional_verifier()

    if verifier is None:
        pytest.skip("kx_agent.capsules.verifier is not generated yet.")

    verify_func = getattr(verifier, "verify_capsule_archive", None)

    if verify_func is None:
        pytest.skip("verify_capsule_archive is not implemented yet.")

    result = verify_func(archive_path)

    if hasattr(result, "ok"):
        assert result.ok is True
    elif isinstance(result, dict):
        assert result.get("ok") is True
    else:
        pytest.fail("Verifier returned unsupported result type.")


def import_optional_verifier() -> Any | None:
    try:
        return importlib.import_module("kx_agent.capsules.verifier")
    except ModuleNotFoundError:
        return None