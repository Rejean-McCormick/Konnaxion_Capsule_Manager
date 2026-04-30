"""Tests for Konnaxion capsule manifest validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from kx_agent.capsules.manifest import (
    MANIFEST_SCHEMA_VERSION,
    REQUIRED_CAPSULE_ROOT_ENTRIES,
    REQUIRED_ENV_TEMPLATES,
    REQUIRED_PROFILES,
    REQUIRED_RUNTIME_SERVICES,
    CapsuleManifest,
    CapsuleManifestError,
    ManifestIssueLevel,
    capsule_filename_for,
    load_manifest,
    load_manifest_text,
    validate_capsule_root,
)
from kx_shared.konnaxion_constants import (
    APP_VERSION,
    CAPSULE_EXTENSION,
    DEFAULT_CAPSULE_ID,
    DEFAULT_CAPSULE_VERSION,
    DEFAULT_CHANNEL,
    PARAM_VERSION,
    PRODUCT_NAME,
    DockerService,
    NetworkProfile,
)


def valid_manifest_data() -> dict:
    """Return a minimal canonical manifest mapping."""

    services = [
        {
            "name": service_name,
            "image": f"konnaxion/{service_name}:{APP_VERSION}",
            "required": True,
        }
        for service_name in sorted(REQUIRED_RUNTIME_SERVICES)
    ]

    images = [
        {
            "service": service["name"],
            "path": f"images/{service['name']}.oci.tar",
            "digest": f"sha256:{service['name'].replace('-', ''):0<64}"[:71],
        }
        for service in services
    ]

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "capsule_id": DEFAULT_CAPSULE_ID,
        "capsule_version": DEFAULT_CAPSULE_VERSION,
        "app_name": PRODUCT_NAME,
        "app_version": APP_VERSION,
        "channel": DEFAULT_CHANNEL,
        "created_at": "2026-04-30T00:00:00Z",
        "builder_version": "kx-builder-0.1.0",
        "param_version": PARAM_VERSION,
        "services": services,
        "images": images,
        "profiles": sorted(REQUIRED_PROFILES),
        "env_templates": sorted(REQUIRED_ENV_TEMPLATES),
        "healthchecks": ["healthchecks/startup.yaml", "healthchecks/readiness.yaml"],
        "policies": ["policies/security_gate.yaml", "policies/runtime_policy.yaml"],
    }


def write_manifest(path: Path, data: dict) -> Path:
    path.write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8")
    return path


def test_default_demo_manifest_is_valid() -> None:
    manifest = CapsuleManifest.default_demo()

    result = manifest.validate()

    assert result.valid is True
    assert result.errors == ()
    assert manifest.schema_version == MANIFEST_SCHEMA_VERSION
    assert manifest.capsule_id == DEFAULT_CAPSULE_ID
    assert manifest.capsule_version == DEFAULT_CAPSULE_VERSION
    assert manifest.app_name == PRODUCT_NAME
    assert manifest.app_version == APP_VERSION
    assert manifest.param_version == PARAM_VERSION


def test_valid_manifest_mapping_is_valid() -> None:
    manifest = CapsuleManifest.from_mapping(valid_manifest_data())

    result = manifest.validate()

    assert result.valid is True
    assert result.errors == ()
    assert set(manifest.service_names()) >= REQUIRED_RUNTIME_SERVICES
    assert set(manifest.profiles) == REQUIRED_PROFILES
    assert set(manifest.env_templates) == REQUIRED_ENV_TEMPLATES


def test_load_manifest_from_file(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path / "manifest.yaml", valid_manifest_data())

    manifest = load_manifest(manifest_path)

    assert manifest.capsule_id == DEFAULT_CAPSULE_ID
    assert manifest.app_version == APP_VERSION


def test_load_manifest_rejects_wrong_filename(tmp_path: Path) -> None:
    wrong_path = write_manifest(tmp_path / "not-manifest.yaml", valid_manifest_data())

    with pytest.raises(CapsuleManifestError, match="manifest.yaml"):
        load_manifest(wrong_path)


def test_load_manifest_text_accepts_yaml_string() -> None:
    text = yaml.safe_dump(valid_manifest_data(), sort_keys=True)

    manifest = load_manifest_text(text)

    assert manifest.capsule_id == DEFAULT_CAPSULE_ID
    assert DockerService.DJANGO_API.value in manifest.service_names()


def test_manifest_requires_all_root_fields() -> None:
    data = valid_manifest_data()
    del data["schema_version"]
    del data["services"]

    manifest = CapsuleManifest.from_mapping(data)
    result = manifest.validate()

    assert result.valid is False
    assert {issue.path for issue in result.errors} >= {"schema_version", "services"}


def test_manifest_rejects_wrong_schema_version() -> None:
    data = valid_manifest_data()
    data["schema_version"] = "wrong/v1"

    result = CapsuleManifest.from_mapping(data).validate()

    assert result.valid is False
    assert any(issue.path == "schema_version" for issue in result.errors)


def test_manifest_rejects_wrong_app_name_version_and_param_version() -> None:
    data = valid_manifest_data()
    data["app_name"] = "Wrong"
    data["app_version"] = "v0"
    data["param_version"] = "wrong-param"

    result = CapsuleManifest.from_mapping(data).validate()

    assert result.valid is False
    assert {issue.path for issue in result.errors} >= {
        "app_name",
        "app_version",
        "param_version",
    }


def test_manifest_rejects_noncanonical_capsule_id() -> None:
    data = valid_manifest_data()
    data["capsule_id"] = "demo"

    result = CapsuleManifest.from_mapping(data).validate()

    assert result.valid is False
    assert any(issue.path == "capsule_id" for issue in result.errors)


def test_manifest_rejects_invalid_created_at() -> None:
    data = valid_manifest_data()
    data["created_at"] = "not-a-date"

    result = CapsuleManifest.from_mapping(data).validate()

    assert result.valid is False
    assert any(issue.path == "created_at" for issue in result.errors)


def test_manifest_rejects_missing_required_service() -> None:
    data = valid_manifest_data()
    data["services"] = [
        service
        for service in data["services"]
        if service["name"] != DockerService.DJANGO_API.value
    ]

    result = CapsuleManifest.from_mapping(data).validate()

    assert result.valid is False
    assert any(
        issue.path == f"services.{DockerService.DJANGO_API.value}"
        for issue in result.errors
    )


def test_manifest_rejects_unknown_service_aliases() -> None:
    data = valid_manifest_data()
    data["services"].append({"name": "backend", "image": "konnaxion/backend:v14"})

    result = CapsuleManifest.from_mapping(data).validate()

    assert result.valid is False
    assert any(issue.path == "services.backend" for issue in result.errors)


def test_manifest_rejects_missing_required_image() -> None:
    data = valid_manifest_data()
    data["images"] = [
        image
        for image in data["images"]
        if image["service"] != DockerService.POSTGRES.value
    ]

    result = CapsuleManifest.from_mapping(data).validate()

    assert result.valid is False
    assert any(
        issue.path == f"images.{DockerService.POSTGRES.value}"
        for issue in result.errors
    )


def test_manifest_rejects_image_outside_images_directory() -> None:
    data = valid_manifest_data()
    data["images"][0]["path"] = "tmp/frontend-next.tar"

    result = CapsuleManifest.from_mapping(data).validate()

    assert result.valid is False
    assert any(".path" in issue.path for issue in result.errors)


def test_manifest_rejects_unknown_image_service() -> None:
    data = valid_manifest_data()
    data["images"].append({"service": "db", "path": "images/db.oci.tar"})

    result = CapsuleManifest.from_mapping(data).validate()

    assert result.valid is False
    assert any(issue.path == "images.db" for issue in result.errors)


@pytest.mark.parametrize("profile", [profile.value for profile in NetworkProfile])
def test_manifest_accepts_each_canonical_profile(profile: str) -> None:
    data = valid_manifest_data()

    assert profile in data["profiles"]


def test_manifest_rejects_missing_profile() -> None:
    data = valid_manifest_data()
    data["profiles"].remove(NetworkProfile.INTRANET_PRIVATE.value)

    result = CapsuleManifest.from_mapping(data).validate()

    assert result.valid is False
    assert any(
        issue.path == f"profiles.{NetworkProfile.INTRANET_PRIVATE.value}"
        for issue in result.errors
    )


def test_manifest_rejects_unknown_profile() -> None:
    data = valid_manifest_data()
    data["profiles"].append("wifi_public")

    result = CapsuleManifest.from_mapping(data).validate()

    assert result.valid is False
    assert any(issue.path == "profiles.wifi_public" for issue in result.errors)


def test_manifest_rejects_missing_env_template() -> None:
    data = valid_manifest_data()
    data["env_templates"].remove("django.env.template")

    result = CapsuleManifest.from_mapping(data).validate()

    assert result.valid is False
    assert any(issue.path == "env_templates.django.env.template" for issue in result.errors)


def test_manifest_warns_on_extra_env_template() -> None:
    data = valid_manifest_data()
    data["env_templates"].append("extra.env.template")

    result = CapsuleManifest.from_mapping(data).validate()

    assert result.valid is True
    assert any(issue.level == ManifestIssueLevel.WARNING for issue in result.warnings)


def test_manifest_requires_healthchecks() -> None:
    data = valid_manifest_data()
    data["healthchecks"] = []

    result = CapsuleManifest.from_mapping(data).validate()

    assert result.valid is False
    assert any(issue.path == "healthchecks" for issue in result.errors)


def test_manifest_requires_policies() -> None:
    data = valid_manifest_data()
    data["policies"] = []

    result = CapsuleManifest.from_mapping(data).validate()

    assert result.valid is False
    assert any(issue.path == "policies" for issue in result.errors)


def test_require_valid_raises_for_errors() -> None:
    data = valid_manifest_data()
    data["services"] = []

    manifest = CapsuleManifest.from_mapping(data)

    with pytest.raises(CapsuleManifestError):
        manifest.require_valid()


def test_validate_capsule_root_accepts_required_layout(tmp_path: Path) -> None:
    for entry in REQUIRED_CAPSULE_ROOT_ENTRIES:
        path = tmp_path / entry
        if "." in Path(entry).name:
            path.write_text("", encoding="utf-8")
        else:
            path.mkdir(parents=True, exist_ok=True)

    result = validate_capsule_root(tmp_path)

    assert result.valid is True
    assert result.errors == ()


def test_validate_capsule_root_rejects_missing_entries(tmp_path: Path) -> None:
    (tmp_path / "manifest.yaml").write_text("", encoding="utf-8")

    result = validate_capsule_root(tmp_path)

    assert result.valid is False
    assert any(issue.path == "docker-compose.capsule.yml" for issue in result.errors)
    assert any(issue.path == "signature.sig" for issue in result.errors)


def test_validate_capsule_root_rejects_nonexistent_path(tmp_path: Path) -> None:
    result = validate_capsule_root(tmp_path / "missing")

    assert result.valid is False
    assert any("does not exist" in issue.message for issue in result.errors)


def test_validate_capsule_root_rejects_file_instead_of_directory(tmp_path: Path) -> None:
    path = tmp_path / "capsule.kxcap"
    path.write_text("", encoding="utf-8")

    result = validate_capsule_root(path)

    assert result.valid is False
    assert any("must be a directory" in issue.message for issue in result.errors)


def test_capsule_filename_for_uses_canonical_extension() -> None:
    filename = capsule_filename_for(DEFAULT_CAPSULE_ID)

    assert filename == f"{DEFAULT_CAPSULE_ID}{CAPSULE_EXTENSION}"


def test_capsule_filename_for_rejects_empty_capsule_id() -> None:
    with pytest.raises(CapsuleManifestError):
        capsule_filename_for("")
