# Konnaxion Capsule Manager

Konnaxion Capsule Manager packages Konnaxion v14 into signed, portable `.kxcap` capsules and runs them through a local Manager, privileged Agent, Docker Compose runtime, private-by-default network profiles, Security Gate checks, backups, restores, rollback, and the canonical `kx` CLI.

## Purpose

The project turns Konnaxion into a portable, secure, plug-and-play appliance system.

```text
Konnaxion Capsule
→ Konnaxion Capsule Manager
→ Konnaxion Agent
→ Docker Compose Runtime
→ Konnaxion Instance
````

## Core Components

* `kx_shared/` — canonical constants, paths, states, profiles, and validation
* `kx_agent/` — privileged local service for runtime, security, network, and backups
* `kx_manager/` — user-facing API/UI layer
* `kx_builder/` — capsule build, manifest, checksum, image, and signature tooling
* `kx_cli/` — canonical `kx` operator/developer CLI
* `profiles/` — approved network profiles
* `policies/` — runtime and Security Gate policies
* `templates/` — Docker Compose and environment templates
* `tests/` — contract and integration tests

## Default Runtime

Konnaxion runs through Docker Compose with:

```text
traefik
frontend-next
django-api
postgres
redis
celeryworker
celerybeat
flower
media-nginx
kx-agent
```

## Security Model

Konnaxion is private by default.

The system enforces:

* signed capsules only
* generated secrets on install
* deny-by-default networking
* Traefik-only HTTP/S entrypoint
* no public PostgreSQL or Redis
* no Docker socket mounts
* no privileged app containers
* blocking Security Gate checks before startup

## Canonical CLI

```bash
kx capsule build
kx capsule verify
kx capsule import

kx instance create
kx instance start
kx instance stop
kx instance status
kx instance logs
kx instance backup
kx instance restore
kx instance restore-new
kx instance update
kx instance rollback
kx instance health

kx backup list
kx backup verify
kx backup test-restore

kx security check
kx network set-profile
```

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Target

Konnaxion as a signed, portable, private-by-default capsule system deployable on a Konnaxion Box, local host, intranet server, private tunnel, temporary public demo, or hardened VPS.


