---
doc_id: DOC-10
title: Konnaxion Builder CLI
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: canonical-draft
owner: Konnaxion
last_updated: 2026-04-30
depends_on:
  - DOC-00_Konnaxion_Canonical_Variables.md
  - DOC-03_Konnaxion_Capsule_Format.md
  - DOC-07_Konnaxion_Security_Gate.md
  - DOC-08_Konnaxion_Runtime_Docker_Compose.md
---

# DOC-10 — Konnaxion Builder CLI

## 0. Purpose

This document defines the canonical command-line interface for building, verifying, exporting, and inspecting a `Konnaxion Capsule`.

The canonical CLI command is:

```bash
kx
```

The Builder CLI must produce portable, signed `.kxcap` files that can be imported by the `Konnaxion Capsule Manager` and executed through the `Konnaxion Agent`.

This document depends on:

```text
DOC-00_Konnaxion_Canonical_Variables.md
DOC-03_Konnaxion_Capsule_Format.md
DOC-07_Konnaxion_Security_Gate.md
DOC-08_Konnaxion_Runtime_Docker_Compose.md
```

All naming, paths, profiles, ports, services, instance states, security statuses, and variable names must remain aligned with `DOC-00`.

Scope boundary:

```text
DOC-10 owns build-time capsule commands only.
DOC-10 does not own runtime instance commands.
DOC-10 does not own backup, restore or rollback commands.
```

Runtime operations belong to the `Konnaxion Capsule Manager` and `Konnaxion Agent`.

Backup, restore and rollback command contracts belong to:

```text
DOC-09_Konnaxion_Backup_Restore_Rollback.md
DOC-14_Konnaxion_Operator_Guide.md
```

---

## 1. Scope

The Builder CLI is responsible for:

```text
Building frontend and backend release artifacts
Building canonical Docker images
Exporting images as OCI tar files
Generating manifest.yaml
Generating docker-compose.capsule.yml
Injecting canonical profiles
Validating capsule structure
Running build-time security checks
Generating checksums
Signing the capsule
Producing a .kxcap file
Verifying an existing .kxcap file
Inspecting capsule metadata
```

The Builder CLI is not responsible for:

```text
Running a production instance
Managing live network profiles
Opening or closing firewall ports
Creating local users
Running long-lived services
Hosting Konnaxion
Managing runtime backups
Verifying runtime backup sets
Restoring runtime data
Rolling back live instances
Running live healthchecks
Changing active network exposure
Replacing the Konnaxion Capsule Manager
Replacing the Konnaxion Agent
```

Runtime actions are handled by:

```text
Konnaxion Capsule Manager
Konnaxion Agent
Docker Compose Runtime
```

---

## 2. Canonical CLI Name

The canonical CLI executable is:

```bash
kx
```

The Builder functionality lives under:

```bash
kx capsule <command>
kx build <command>
```

The preferred public command group is:

```bash
kx capsule
```

The `kx build` group may exist as a convenience alias, but documentation should primarily use `kx capsule`.

---

## 3. Canonical Builder Commands

## 3.1 Capsule Commands

```bash
kx capsule build
kx capsule verify
kx capsule inspect
kx capsule list-profiles
kx capsule export-manifest
```

## 3.2 Optional Developer Commands

```bash
kx capsule clean
kx capsule doctor
kx capsule schema
kx capsule sign
kx capsule checksum
```

## 3.3 Runtime Commands Mentioned for Alignment Only

The Builder CLI may reference runtime commands only to explain the handoff between a built capsule and a running instance.

These commands are **not owned by DOC-10**:

```bash
kx capsule import

kx instance create
kx instance start
kx instance stop
kx instance status
kx instance logs
kx instance backup
kx instance restore
kx instance update
kx instance rollback
kx instance restore-new
kx instance health

kx backup list
kx backup verify
kx backup test-restore

kx security check
kx network set-profile
```

Ownership:

| Command group | Owning document |
|---|---|
| `kx capsule build` | `DOC-10_Konnaxion_Builder_CLI.md` |
| `kx capsule verify` | `DOC-10_Konnaxion_Builder_CLI.md` |
| `kx capsule inspect` | `DOC-10_Konnaxion_Builder_CLI.md` |
| `kx capsule list-profiles` | `DOC-10_Konnaxion_Builder_CLI.md` |
| `kx capsule export-manifest` | `DOC-10_Konnaxion_Builder_CLI.md` |
| `kx capsule import` | `DOC-04_Konnaxion_Manager_Architecture.md` / `DOC-05_Konnaxion_Agent_Security_Model.md` |
| `kx instance *` | `DOC-04_Konnaxion_Manager_Architecture.md` / `DOC-05_Konnaxion_Agent_Security_Model.md` |
| `kx backup *` | `DOC-09_Konnaxion_Backup_Restore_Rollback.md` |
| `kx security check` | `DOC-07_Konnaxion_Security_Gate.md` |
| `kx network set-profile` | `DOC-06_Konnaxion_Network_Profiles.md` |

DOC-10 must not become the canonical reference for runtime operations.

---

## 3.4 Namespace Ownership Rule

The `kx` executable is shared across Builder, Manager and Agent workflows, but ownership is split by command namespace.

DOC-10 owns only these public command namespaces:

```bash
kx capsule build
kx capsule verify
kx capsule inspect
kx capsule list-profiles
kx capsule export-manifest
kx capsule doctor
```

DOC-10 may define developer convenience commands:

```bash
kx capsule clean
kx capsule schema
kx capsule sign
kx capsule checksum
```

DOC-10 must not define behavior for live runtime commands such as:

```bash
kx instance backup
kx instance restore
kx instance rollback
kx backup verify
kx backup test-restore
kx network set-profile
```

Those commands are intentionally delegated to runtime documents because they operate on a `Konnaxion Instance`, not on a static `.kxcap` file.

---

## 4. Canonical Build Output

A successful build must output one `.kxcap` file.

Canonical filename pattern:

```text
konnaxion-v14-demo-YYYY.MM.DD.kxcap
```

Example:

```text
konnaxion-v14-demo-2026.04.30.kxcap
```

Canonical output directory:

```text
./dist/capsules/
```

Example:

```text
./dist/capsules/konnaxion-v14-demo-2026.04.30.kxcap
```

---

## 5. Canonical Capsule Structure

The Builder CLI must produce a `.kxcap` archive using this structure:

```text
.kxcap
├── manifest.yaml
├── docker-compose.capsule.yml
├── images/
│   ├── frontend-next.oci.tar
│   ├── django-api.oci.tar
│   ├── traefik.oci.tar
│   └── media-nginx.oci.tar
├── profiles/
│   ├── local_only.yaml
│   ├── intranet_private.yaml
│   ├── private_tunnel.yaml
│   ├── public_temporary.yaml
│   ├── public_vps.yaml
│   └── offline.yaml
├── env-templates/
│   ├── django.env.template
│   ├── postgres.env.template
│   ├── redis.env.template
│   └── frontend.env.template
├── migrations/
├── seed-data/
├── healthchecks/
├── checksums.txt
└── signature.sig
```

The Builder must fail if the generated capsule structure does not match the canonical format.

---

## 6. Canonical Services Built by the CLI

The Builder must use the canonical service names defined by `DOC-00`.

| Service | Builder Responsibility |
|---|---|
| `frontend-next` | Build Next.js production frontend image |
| `django-api` | Build Django/Gunicorn backend image |
| `traefik` | Include approved Traefik image/config |
| `media-nginx` | Include approved media/static service image |
| `postgres` | Reference approved upstream image, no custom secret baked in |
| `redis` | Reference approved upstream image, no custom secret baked in |
| `celeryworker` | Use the `django-api` image with worker command |
| `celerybeat` | Use the `django-api` image with beat command |
| `flower` | Private-only optional service |
| `kx-agent` | Not bundled as an application service unless explicitly approved |

The capsule must not include images with non-canonical service names unless the manifest maps them explicitly.

---

## 7. Build Pipeline

A canonical `kx capsule build` must execute these stages in order:

```text
1. Load build configuration
2. Validate repository layout
3. Validate canonical variables
4. Validate network profiles
5. Build frontend
6. Build backend
7. Build Docker images
8. Run tests and static checks
9. Generate docker-compose.capsule.yml
10. Generate manifest.yaml
11. Export Docker images as OCI tar files
12. Generate env templates
13. Add profiles
14. Add migrations and optional seed data
15. Generate healthchecks
16. Generate checksums.txt
17. Sign capsule
18. Verify finished capsule
19. Write .kxcap to output path
```

If any critical stage fails, the Builder must stop and return a non-zero exit code.

---

## 8. Command: `kx capsule build`

## 8.1 Purpose

Build a new signed `Konnaxion Capsule`.

## 8.2 Canonical Syntax

```bash
kx capsule build \
  --app-version v14 \
  --capsule-version 2026.04.30-demo.1 \
  --profile demo \
  --output ./dist/capsules/konnaxion-v14-demo-2026.04.30.kxcap
```

## 8.3 Common Options

| Option | Required | Description |
|---|---:|---|
| `--app-version` | Yes | Application version, e.g. `v14` |
| `--capsule-version` | Yes | Capsule version, e.g. `2026.04.30-demo.1` |
| `--profile` | Yes | Build profile, e.g. `demo`, `release`, `dev` |
| `--output` | Yes | Output `.kxcap` path |
| `--source-root` | No | Source repo root, default current directory |
| `--frontend-root` | No | Frontend path, default `frontend` |
| `--backend-root` | No | Backend path, default `backend` |
| `--include-seed-data` | No | Include approved seed data |
| `--skip-tests` | No | Skip tests; forbidden for release builds |
| `--unsigned` | No | Produce unsigned dev capsule; forbidden for release builds |
| `--verbose` | No | Detailed logs |
| `--json` | No | Machine-readable output |

## 8.4 Example: Demo Capsule

```bash
kx capsule build \
  --app-version v14 \
  --capsule-version 2026.04.30-demo.1 \
  --profile demo \
  --include-seed-data \
  --output ./dist/capsules/konnaxion-v14-demo-2026.04.30.kxcap
```

## 8.5 Example: Release Capsule

```bash
kx capsule build \
  --app-version v14 \
  --capsule-version 2026.04.30-release.1 \
  --profile release \
  --output ./dist/capsules/konnaxion-v14-release-2026.04.30.kxcap
```

Release builds must be signed.

Release builds must not use `--skip-tests`.

Release builds must not use `--unsigned`.

---

## 9. Command: `kx capsule verify`

## 9.1 Purpose

Verify a `.kxcap` file before import, distribution, or installation.

## 9.2 Syntax

```bash
kx capsule verify ./dist/capsules/konnaxion-v14-demo-2026.04.30.kxcap
```

## 9.3 Required Checks

The verify command must check:

```text
capsule file exists
capsule extension is .kxcap
manifest.yaml exists
manifest schema is valid
docker-compose.capsule.yml exists
all required directories exist
all required profiles exist
all listed OCI images exist
checksums.txt exists
all checksums match
signature.sig exists
signature is valid
no forbidden secrets are present
no forbidden public ports are declared
no Docker socket mount is declared
no privileged containers are declared
no host network mode is declared
all service names are canonical or explicitly mapped
```

## 9.4 Output

Human-readable output:

```text
Konnaxion Capsule Verification

Capsule: konnaxion-v14-demo-2026.04.30.kxcap
Status: PASS

[PASS] manifest_schema
[PASS] image_checksums
[PASS] capsule_signature
[PASS] dangerous_ports_blocked
[PASS] docker_socket_not_mounted
[PASS] no_privileged_containers
[PASS] no_host_network
```

Machine-readable output:

```bash
kx capsule verify ./dist/capsules/konnaxion-v14-demo-2026.04.30.kxcap --json
```

Example JSON:

```json
{
  "capsule_id": "konnaxion-v14-demo-2026.04.30",
  "capsule_version": "2026.04.30-demo.1",
  "status": "PASS",
  "checks": [
    {
      "name": "manifest_schema",
      "status": "PASS"
    },
    {
      "name": "capsule_signature",
      "status": "PASS"
    }
  ]
}
```

---

## 10. Command: `kx capsule inspect`

## 10.1 Purpose

Print metadata from a `.kxcap` file without importing it.

## 10.2 Syntax

```bash
kx capsule inspect konnaxion-v14-demo-2026.04.30.kxcap
```

## 10.3 Expected Output

```text
Capsule ID: konnaxion-v14-demo-2026.04.30
Capsule Version: 2026.04.30-demo.1
Application Version: v14
Default Network Profile: intranet_private
Default Exposure Mode: private
Services:
  - traefik
  - frontend-next
  - django-api
  - postgres
  - redis
  - celeryworker
  - celerybeat
  - media-nginx
Profiles:
  - local_only
  - intranet_private
  - private_tunnel
  - public_temporary
  - public_vps
  - offline
Signed: yes
```

---

## 11. Command: `kx capsule list-profiles`

## 11.1 Purpose

List network profiles embedded in a capsule.

## 11.2 Syntax

```bash
kx capsule list-profiles konnaxion-v14-demo-2026.04.30.kxcap
```

## 11.3 Output

```text
local_only
intranet_private
private_tunnel
public_temporary
public_vps
offline
```

The command must fail if any canonical profile is missing.

---

## 12. Command: `kx capsule export-manifest`

## 12.1 Purpose

Extract `manifest.yaml` from a capsule for inspection, auditing, or CI checks.

## 12.2 Syntax

```bash
kx capsule export-manifest konnaxion-v14-demo-2026.04.30.kxcap \
  --output ./dist/manifests/konnaxion-v14-demo-2026.04.30.manifest.yaml
```

---

## 13. Command: `kx capsule doctor`

## 13.1 Purpose

Check the local build environment.

## 13.2 Syntax

```bash
kx capsule doctor
```

## 13.3 Required Checks

```text
Docker available
Docker Compose available
Node.js available
pnpm available
Python available
backend source exists
frontend source exists
Git worktree status available
sufficient disk space
sufficient memory
signing key configured for release builds
```

Example:

```text
Konnaxion Builder Doctor

[PASS] docker_available
[PASS] docker_compose_available
[PASS] node_available
[PASS] pnpm_available
[PASS] python_available
[PASS] backend_root_exists
[PASS] frontend_root_exists
[WARN] git_worktree_dirty
[PASS] signing_key_available
```

A dirty Git worktree may be allowed for development builds but should block release builds unless explicitly overridden.

---

## 14. Build Configuration File

The Builder may accept a canonical config file:

```text
kxbuild.yaml
```

Example:

```yaml
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30

source:
  root: .
  frontend_root: frontend
  backend_root: backend

capsule:
  id: konnaxion-v14-demo-2026.04.30
  version: 2026.04.30-demo.1
  output: ./dist/capsules/konnaxion-v14-demo-2026.04.30.kxcap
  include_seed_data: true

profiles:
  default_network_profile: intranet_private
  default_exposure_mode: private
  include:
    - local_only
    - intranet_private
    - private_tunnel
    - public_temporary
    - public_vps
    - offline

security:
  require_signature: true
  allow_unknown_images: false
  allow_privileged_containers: false
  allow_docker_socket_mount: false
  allow_host_network: false
  block_dangerous_ports: true

build:
  run_tests: true
  export_oci_images: true
  generate_checksums: true
  sign_capsule: true
```

Command using config:

```bash
kx capsule build --config kxbuild.yaml
```

Command-line flags override config values unless explicitly forbidden by the selected build profile.

---

## 15. Canonical `manifest.yaml`

The Builder must generate `manifest.yaml`.

Minimum required fields:

```yaml
project: Konnaxion
app_version: v14
capsule_id: konnaxion-v14-demo-2026.04.30
capsule_version: 2026.04.30-demo.1
param_version: kx-param-2026.04.30

default_network_profile: intranet_private
default_exposure_mode: private

required_ram_mb: 4096
recommended_ram_mb: 8192

services:
  traefik:
    role: reverse_proxy
    public_entrypoint: true

  frontend-next:
    role: frontend
    internal_port: 3000

  django-api:
    role: backend_api
    internal_port: 5000

  postgres:
    role: database
    internal_only: true

  redis:
    role: broker
    internal_only: true

  celeryworker:
    role: background_worker
    internal_only: true

  celerybeat:
    role: scheduler
    internal_only: true

  media-nginx:
    role: media_static
    internal_only: true

routes:
  "/": frontend-next
  "/api/": django-api
  "/admin/": django-api
  "/media/": media-nginx

profiles:
  - local_only
  - intranet_private
  - private_tunnel
  - public_temporary
  - public_vps
  - offline

security:
  require_signed_capsule: true
  generate_secrets_on_install: true
  expose_docker_socket: false
  allow_privileged_containers: false
  allow_host_network: false
  allow_unknown_images: false
```

The Builder must fail if required manifest fields are missing.

---

## 16. Canonical `docker-compose.capsule.yml`

The Builder must generate or include `docker-compose.capsule.yml`.

It must obey the following rules:

```text
Use canonical service names
Use internal Docker networks
Expose only Traefik entrypoints
Do not publish Postgres
Do not publish Redis
Do not publish Django direct port
Do not publish Next.js direct port
Do not publish Flower by default
Do not mount Docker socket
Do not use privileged containers
Do not use host network
Use named volumes or instance paths provided by the Agent
```

Forbidden examples:

```yaml
services:
  postgres:
    ports:
      - "5432:5432"
```

```yaml
services:
  django-api:
    privileged: true
```

```yaml
services:
  frontend-next:
    ports:
      - "3000:3000"
```

```yaml
services:
  any-service:
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
```

---

## 17. Build-Time Secret Policy

The Builder must not bake secrets into images or capsule files.

Forbidden during build:

```text
real DJANGO_SECRET_KEY
real POSTGRES_PASSWORD
real DATABASE_URL with password
SSH private keys
Git tokens
provider tokens
API keys
production .env files
private certificates
```

Allowed:

```text
template env files
placeholder values
schema examples
non-secret defaults
development-only fake values clearly marked as fake
```

Required placeholder format:

```text
<GENERATED_ON_INSTALL>
<GENERATED_FROM_PROFILE>
<SET_BY_MANAGER>
<OPTIONAL>
```

Example:

```env
DJANGO_SECRET_KEY=<GENERATED_ON_INSTALL>
POSTGRES_PASSWORD=<GENERATED_ON_INSTALL>
DJANGO_ALLOWED_HOSTS=<GENERATED_FROM_PROFILE>
```

---

## 18. Signing and Checksums

## 18.1 Checksums

The Builder must generate:

```text
checksums.txt
```

The checksum file must include all relevant files inside the capsule except `signature.sig`.

Recommended format:

```text
sha256  manifest.yaml
sha256  docker-compose.capsule.yml
sha256  images/frontend-next.oci.tar
sha256  images/django-api.oci.tar
sha256  images/traefik.oci.tar
sha256  images/media-nginx.oci.tar
```

## 18.2 Signature

The Builder must generate:

```text
signature.sig
```

The signature must cover:

```text
checksums.txt
manifest.yaml
docker-compose.capsule.yml
profiles/
env-templates/
images/
healthchecks/
```

Release capsules must be signed.

Unsigned capsules are allowed only for local development and must be clearly marked:

```yaml
signature_status: unsigned_dev_only
```

The Manager and Agent must reject unsigned capsules unless explicitly running in a development mode.

---

## 19. Build Profiles

The Builder supports these build profiles:

| Build Profile | Purpose | Signed | Tests Required | Seed Data |
|---|---|---:|---:|---:|
| `dev` | Local developer testing | Optional | Optional | Optional |
| `demo` | Demo-ready capsule | Required | Required | Optional |
| `release` | Production-grade capsule | Required | Required | No by default |
| `ci` | Automated CI validation | Required for release artifacts | Required | No |

These are build profiles, not network profiles.

Do not confuse build profile values with `NETWORK_PROFILE` values.

Canonical network profiles remain:

```text
local_only
intranet_private
private_tunnel
public_temporary
public_vps
offline
```

---

## 20. Required Build Checks

The Builder must perform these checks before producing a capsule:

```text
canonical_service_names
canonical_network_profiles
no_real_secrets
no_public_internal_ports
no_docker_socket_mount
no_privileged_containers
no_host_network
manifest_schema
compose_schema
image_export_complete
checksums_generated
signature_generated
capsule_verify_passes
```

For release builds, all required checks must pass.

For demo builds, all security checks must pass.

For dev builds, warnings may be allowed, but the capsule must be marked as development-only.

---

## 21. Output Status Values

The Builder uses the canonical Security Gate statuses from `DOC-00`:

```text
PASS
WARN
FAIL_BLOCKING
SKIPPED
UNKNOWN
```

A build can return:

```text
BUILD_PASS
BUILD_PASS_WITH_WARNINGS
BUILD_FAIL
BUILD_SECURITY_BLOCKED
```

Mapping:

| Build Result | Meaning |
|---|---|
| `BUILD_PASS` | Capsule produced and verified |
| `BUILD_PASS_WITH_WARNINGS` | Capsule produced, non-blocking warnings exist |
| `BUILD_FAIL` | Build failed |
| `BUILD_SECURITY_BLOCKED` | Build blocked by security policy |

---

## 22. Exit Codes

Canonical exit codes:

| Code | Meaning |
|---:|---|
| `0` | Success |
| `1` | General error |
| `2` | Invalid CLI usage |
| `3` | Build failed |
| `4` | Verification failed |
| `5` | Security policy failure |
| `6` | Missing dependency |
| `7` | Signing failure |
| `8` | Manifest/schema failure |
| `9` | File or path error |

Scripts and CI systems should rely on these exit codes.

---

## 23. Logs

Default log directory:

```text
./dist/logs/
```

Canonical build log:

```text
./dist/logs/kx-capsule-build-<TIMESTAMP>.log
```

Canonical verify log:

```text
./dist/logs/kx-capsule-verify-<TIMESTAMP>.log
```

Logs must not contain secrets.

The Builder must redact:

```text
DJANGO_SECRET_KEY
POSTGRES_PASSWORD
DATABASE_URL password segment
API keys
tokens
private keys
authorization headers
cookies
```

Canonical redaction marker:

```text
[REDACTED]
```

---

## 24. JSON Output Contract

All major commands should support:

```bash
--json
```

Example:

```bash
kx capsule build --config kxbuild.yaml --json
```

Minimum JSON fields:

```json
{
  "command": "kx capsule build",
  "status": "BUILD_PASS",
  "capsule_id": "konnaxion-v14-demo-2026.04.30",
  "capsule_version": "2026.04.30-demo.1",
  "output": "./dist/capsules/konnaxion-v14-demo-2026.04.30.kxcap",
  "checks": [],
  "warnings": [],
  "errors": []
}
```

All statuses inside `checks` must use:

```text
PASS
WARN
FAIL_BLOCKING
SKIPPED
UNKNOWN
```

---

## 25. CI Usage

A release pipeline should run:

```bash
kx capsule doctor
kx capsule build --config kxbuild.yaml
kx capsule verify ./dist/capsules/konnaxion-v14-demo-2026.04.30.kxcap
kx capsule inspect ./dist/capsules/konnaxion-v14-demo-2026.04.30.kxcap
```

Example CI release gate:

```bash
kx capsule verify ./dist/capsules/konnaxion-v14-demo-2026.04.30.kxcap --json > capsule-verify.json
```

The CI job must fail if:

```text
status != PASS
any check.status == FAIL_BLOCKING
signature is missing
release build is unsigned
forbidden secret is detected
forbidden port is exposed
```

---

## 26. Developer Workflow

## 26.1 Local Dev Capsule

```bash
kx capsule doctor

kx capsule build \
  --app-version v14 \
  --capsule-version 2026.04.30-dev.1 \
  --profile dev \
  --output ./dist/capsules/konnaxion-v14-dev-2026.04.30.kxcap
```

## 26.2 Demo Capsule

```bash
kx capsule build \
  --app-version v14 \
  --capsule-version 2026.04.30-demo.1 \
  --profile demo \
  --include-seed-data \
  --output ./dist/capsules/konnaxion-v14-demo-2026.04.30.kxcap

kx capsule verify ./dist/capsules/konnaxion-v14-demo-2026.04.30.kxcap
```

## 26.3 Release Capsule

```bash
kx capsule build \
  --app-version v14 \
  --capsule-version 2026.04.30-release.1 \
  --profile release \
  --output ./dist/capsules/konnaxion-v14-release-2026.04.30.kxcap

kx capsule verify ./dist/capsules/konnaxion-v14-release-2026.04.30.kxcap
```

---

## 27. Interaction With Manager and Agent

The Builder produces the capsule.

The Manager imports it.

The Agent runs it.

Canonical handoff:

```text
kx capsule build
  ↓
.kxcap
  ↓
Konnaxion Capsule Manager
  ↓
Konnaxion Agent
  ↓
Docker Compose Runtime
  ↓
Konnaxion Instance
```

The Builder must not assume that the build machine and runtime machine are the same.

The Builder must also not assume that runtime state exists.

The Builder operates on:

```text
source repository
build configuration
generated images
capsule metadata
.kxcap archive
```

The Manager and Agent operate on:

```text
Konnaxion Instance
runtime volumes
network profiles
firewall rules
backup sets
restore plans
rollback state
```

---

## 28. Import Contract

A capsule built by the Builder must be importable by the Manager without manual edits.

The Manager must be able to derive:

```text
CAPSULE_ID
CAPSULE_VERSION
APP_VERSION
PARAM_VERSION
default NETWORK_PROFILE
default EXPOSURE_MODE
required services
routes
env templates
image list
healthchecks
security requirements
```

from:

```text
manifest.yaml
docker-compose.capsule.yml
profiles/
env-templates/
healthchecks/
```

No manual editing should be required after build.

The import contract must not require runtime backup data.

The capsule may declare backup-related capabilities, such as healthcheck names or required writable paths, but it must not contain backup sets, production database dumps, runtime secrets, or restore state.

Backup and restore behavior is defined by:

```text
DOC-09_Konnaxion_Backup_Restore_Rollback.md
```

---

## 29. Security Requirements

The Builder must enforce these requirements:

```text
Private-by-default
Signed capsules by default
No real secrets in capsule
No exposed internal ports
No Docker socket mount
No privileged containers
No host networking
Canonical service names only
Canonical network profiles only
Checksums for all payloads
Manifest schema validation
Logs redacted
Release builds cannot skip tests
Release builds cannot be unsigned
```

If a security requirement fails, the build must return:

```text
BUILD_SECURITY_BLOCKED
```

and exit code:

```text
5
```

---

## 30. Forbidden Build Outputs

The Builder must never produce a capsule that:

```text
exposes Postgres publicly
exposes Redis publicly
exposes frontend-next directly on 3000 publicly
exposes django-api directly on 5000 or 8000 publicly
exposes Flower publicly
mounts /var/run/docker.sock
uses privileged: true
uses network_mode: host
contains real production secrets
contains SSH private keys
contains provider tokens
contains a production DB dump in cleartext
```

---

## 31. Minimal Implementation Plan

## 31.1 MVP Builder

Minimum viable implementation:

```text
kx capsule build
kx capsule verify
kx capsule inspect
kx capsule doctor
```

MVP build features:

```text
build frontend image
build backend image
include Traefik/media images
generate manifest.yaml
generate docker-compose.capsule.yml
include canonical profiles
include env templates
export OCI image tar files
generate checksums
sign capsule
verify capsule
```

## 31.2 Phase 2

```text
JSON output
CI integration
schema command
stronger secret scanning
SBOM generation
image provenance metadata
release channels
delta capsules
```

## 31.3 Phase 3

```text
GUI integration
remote signing support
hardware appliance factory build
offline update packages
multi-instance build variants
```

---

## 32. Open Design Questions

The following are intentionally left open for later documents:

```text
exact signing technology
exact archive container format
exact SBOM format
exact OCI image naming convention
exact image registry strategy
whether capsules can support deltas
whether capsules can include encrypted demo datasets
whether release signing uses local keys or remote signer
```

These questions must not block the DOC-10 CLI contract.

---

## 33. Fixed Decisions

This document fixes the following decisions:

```text
Canonical CLI executable: kx
Canonical Builder group: kx capsule
Canonical output: .kxcap
Canonical default capsule output path: ./dist/capsules/
Release capsules must be signed
Demo capsules must be signed
Release builds cannot skip tests
The Builder must reject real secrets
The Builder must reject dangerous exposed ports
The Builder must reject Docker socket mounts
The Builder must reject privileged containers
The Builder must reject host networking
The Builder must generate and verify checksums
The Builder must generate manifest.yaml
The Builder must generate docker-compose.capsule.yml
The Builder must use canonical service names
The Builder must include canonical network profiles
DOC-10 owns build-time capsule commands only
DOC-10 does not own runtime backup, restore or rollback commands
DOC-10 may reference runtime commands only for handoff/alignment
```

---

## 34. Reference Command Summary

```bash
# Check local build environment
kx capsule doctor

# Build demo capsule
kx capsule build \
  --app-version v14 \
  --capsule-version 2026.04.30-demo.1 \
  --profile demo \
  --include-seed-data \
  --output ./dist/capsules/konnaxion-v14-demo-2026.04.30.kxcap

# Verify capsule
kx capsule verify ./dist/capsules/konnaxion-v14-demo-2026.04.30.kxcap

# Inspect capsule
kx capsule inspect ./dist/capsules/konnaxion-v14-demo-2026.04.30.kxcap

# List embedded network profiles
kx capsule list-profiles ./dist/capsules/konnaxion-v14-demo-2026.04.30.kxcap

# Export manifest
kx capsule export-manifest ./dist/capsules/konnaxion-v14-demo-2026.04.30.kxcap \
  --output ./dist/manifests/konnaxion-v14-demo-2026.04.30.manifest.yaml
```
