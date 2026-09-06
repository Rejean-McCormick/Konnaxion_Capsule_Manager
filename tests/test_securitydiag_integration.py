from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from kx_agent import main as agent_main
from kx_agent.runtime.compose import ComposeValidationError, validate_compose_spec
from kx_agent.security import evidence
from kx_agent.security.gate import context_from_compose, run_security_gate


def test_agent_rejects_non_loopback_bind(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = agent_main.AgentRuntimeConfig.from_environment()
    unsafe = agent_main.AgentRuntimeConfig(
        host="0.0.0.0",
        port=cfg.port,
        log_level=cfg.log_level,
        instance_id=cfg.instance_id,
        network_profile=cfg.network_profile,
        exposure_mode=cfg.exposure_mode,
        root_dir=cfg.root_dir,
        agent_dir=cfg.agent_dir,
        instances_dir=cfg.instances_dir,
        capsules_dir=cfg.capsules_dir,
        backups_root=cfg.backups_root,
        shared_dir=cfg.shared_dir,
    )
    with pytest.raises(agent_main.AgentStartupError, match="local-only"):
        agent_main.validate_config(unsafe)


def test_signed_manifest_image_allowlist_rejects_wrong_image() -> None:
    compose = {
        "services": {
            "django-api": {"image": "evil/example:latest"},
        }
    }
    manifest = {
        "schema_version": "kxcap/v1",
        "capsule_id": "demo",
        "capsule_version": "1",
        "app_name": "Konnaxion",
        "app_version": "v14",
        "channel": "stable",
    }
    env = {
        "DJANGO_SECRET_KEY": "x" * 64,
        "POSTGRES_PASSWORD": "strong-password-value",
        "DATABASE_URL": "postgres://user:strong-password-value@postgres:5432/konnaxion",
    }
    context = context_from_compose(
        instance_id="demo",
        compose=compose,
        manifest=manifest,
        env=env,
        capsule_signature_verified=True,
        image_checksums_verified=True,
        firewall_enabled=True,
        backup_configured=True,
        admin_surface_private=True,
        postgres_public=False,
        redis_public=False,
        allowed_images={"konnaxion/django-api:v14"},
    )
    result = run_security_gate(context)
    by_check = {item.check.value: item for item in result.results}
    assert by_check["allowed_images_only"].status.value == "FAIL_BLOCKING"


def test_runtime_exposure_detects_internal_published_port() -> None:
    compose = {
        "services": {
            "traefik": {"ports": ["80:80", "443:443"]},
            "postgres": {"ports": ["0.0.0.0:5432:5432"]},
            "redis": {},
        }
    }
    postgres_public, redis_public, admin_private, details = evidence._runtime_exposure(compose)
    assert postgres_public is True
    assert redis_public is False
    assert admin_private is False
    assert details["postgres_ports"]


def test_security_gate_evidence_redacts_secret_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "security-gate.json"
    monkeypatch.setattr(evidence, "instance_security_gate_file", lambda _: target)
    evidence.write_security_gate_evidence(
        "demo",
        {"status": "PASS", "DJANGO_SECRET_KEY": "must-not-be-written"},
    )
    text = target.read_text(encoding="utf-8")
    assert "must-not-be-written" not in text
    assert "<REDACTED>" in text


def test_security_gate_evidence_is_non_secret_and_restricted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "security-gate.json"
    monkeypatch.setattr(evidence, "instance_security_gate_file", lambda _: target)

    path = evidence.write_security_gate_evidence(
        "demo",
        {
            "status": "PASS",
            "results": [
                {
                    "check": "capsule_signature",
                    "status": "PASS",
                }
            ],
        },
    )

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == "kx-security-gate-evidence/v1"
    assert data["status"] == "PASS"

    # POSIX permissions are meaningful on Linux/macOS only.
    # Windows does not expose Unix permission bits consistently through stat().
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o640


def _valid_compose_for_policy() -> dict:
    services = {
        "traefik": {
            "image": "traefik:v3.1",
            "ports": ["80:80", "443:443"],
        },
        "frontend-next": {
            "image": "konnaxion/frontend-next:v14",
        },
        "django-api": {
            "image": "konnaxion/django-api:v14",
        },
        "postgres": {
            "image": "postgres:16",
        },
        "redis": {
            "image": "redis:7",
        },
        "celeryworker": {
            "image": "konnaxion/django-api:v14",
        },
        "celerybeat": {
            "image": "konnaxion/django-api:v14",
        },
        "media-nginx": {
            "image": "nginx:1.27",
        },
    }

    return {
        "services": services,
        "networks": {
            "kx-private": {"internal": True},
            "kx-data": {"internal": True},
            "kx-edge": {},
        },
    }


def test_compose_policy_rejects_host_pid_namespace() -> None:
    compose = _valid_compose_for_policy()
    compose["services"]["django-api"]["pid"] = "host"

    with pytest.raises(ComposeValidationError, match="host PID"):
        validate_compose_spec(compose)


def test_compose_policy_rejects_host_bind_outside_konnaxion_root() -> None:
    compose = _valid_compose_for_policy()
    compose["services"]["django-api"]["volumes"] = ["/etc:/host-etc:ro"]

    with pytest.raises(ComposeValidationError, match="forbidden host bind mount"):
        validate_compose_spec(compose)