doc_id: DOC-10
title: Konnaxion Builder CLI
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: canonical-draft
owner: Konnaxion
last_updated: 2026-05-02
depends_on:
  - DOC-00_Konnaxion_Canonical_Variables.md
  - DOC-03_Konnaxion_Capsule_Format.md
  - DOC-07_Konnaxion_Security_Gate.md
  - DOC-08_Konnaxion_Runtime_Docker_Compose.md
  - DOC-16_Konnaxion_Manager_GUI_Technical_Contract.md
  - DOC-18_Konnaxion_GUI_Target_Modes.md
---

# DOC-10 — Konnaxion Builder CLI

## 0. Purpose

This document defines the canonical command-line interface for building, verifying, exporting, and inspecting a `Konnaxion Capsule`.

The canonical public CLI command is:

```bash
kx
````

The current implementation may also expose this compatibility executable:

```bash
kx-builder
```

Documentation should prefer:

```bash
kx capsule <command>
```

Implementation and development examples may use:

```bash
uv run kx-builder capsule <command>
```

The Builder CLI must produce portable, signed `.kxcap` files that can be imported by the `Konnaxion Capsule Manager` and executed through the `Konnaxion Agent` without manual image loading, manual runtime env edits, manual Traefik edits, or tunnel-only behavior.

This document depends on:

```text
DOC-00_Konnaxion_Canonical_Variables.md
DOC-03_Konnaxion_Capsule_Format.md
DOC-07_Konnaxion_Security_Gate.md
DOC-08_Konnaxion_Runtime_Docker_Compose.md
DOC-16_Konnaxion_Manager_GUI_Technical_Contract.md
DOC-18_Konnaxion_GUI_Target_Modes.md
```

All naming, paths, profiles, ports, services, instance states, security statuses, image archive names, and variable names must remain aligned with `DOC-00`.

Scope boundary:

```text
DOC-10 owns build-time capsule commands only.
DOC-10 does not own runtime instance commands.
DOC-10 does not own backup, restore or rollback commands.
DOC-10 does not own live network profile mutation.
```

Runtime operations belong to:

```text
Konnaxion Capsule Manager
Konnaxion Agent
Docker Compose Runtime
```

Backup, restore, rollback, and live runtime operations belong to:

```text
DOC-09_Konnaxion_Backup_Restore_Rollback.md
DOC-14_Konnaxion_Operator_Guide.md
DOC-16_Konnaxion_Manager_GUI_Technical_Contract.md
```

---

## 1. Scope

The Builder CLI is responsible for:

```text
Building frontend and backend release artifacts
Building canonical app Docker images
Exporting all required runtime images as loadable .oci.tar archives
Generating manifest.yaml
Generating docker-compose.capsule.yml
Injecting canonical profiles
Generating env templates
Generating healthcheck templates
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

The canonical public CLI executable is:

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

The development executable may be:

```bash
kx-builder
```

The compatibility mapping is:

| Public command               | Implementation-compatible command    |
| ---------------------------- | ------------------------------------ |
| `kx capsule build`           | `kx-builder capsule build`           |
| `kx capsule verify`          | `kx-builder capsule verify`          |
| `kx capsule inspect`         | `kx-builder capsule inspect`         |
| `kx capsule list-profiles`   | `kx-builder capsule list-profiles`   |
| `kx capsule export-manifest` | `kx-builder capsule export-manifest` |

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

These commands are not owned by DOC-10:

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

| Command group                | Owning document                                                                         |
| ---------------------------- | --------------------------------------------------------------------------------------- |
| `kx capsule build`           | `DOC-10_Konnaxion_Builder_CLI.md`                                                       |
| `kx capsule verify`          | `DOC-10_Konnaxion_Builder_CLI.md`                                                       |
| `kx capsule inspect`         | `DOC-10_Konnaxion_Builder_CLI.md`                                                       |
| `kx capsule list-profiles`   | `DOC-10_Konnaxion_Builder_CLI.md`                                                       |
| `kx capsule export-manifest` | `DOC-10_Konnaxion_Builder_CLI.md`                                                       |
| `kx capsule import`          | `DOC-04_Konnaxion_Manager_Architecture.md` / `DOC-05_Konnaxion_Agent_Security_Model.md` |
| `kx instance *`              | `DOC-04_Konnaxion_Manager_Architecture.md` / `DOC-05_Konnaxion_Agent_Security_Model.md` |
| `kx backup *`                | `DOC-09_Konnaxion_Backup_Restore_Rollback.md`                                           |
| `kx security check`          | `DOC-07_Konnaxion_Security_Gate.md`                                                     |
| `kx network set-profile`     | `DOC-06_Konnaxion_Network_Profiles.md`                                                  |

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

Development or GUI integration may write capsules to:

```text
./runtime/capsules/
```

Example:

```text
./runtime/capsules/konnaxion-v14-demo-2026.05.02.kxcap
```

---

## 5. Canonical Capsule Structure

The Builder CLI must produce a `.kxcap` archive using this structure:

```text
.kxcap
├── manifest.yaml
├── docker-compose.capsule.yml
├── images.yaml
├── images/
│   ├── frontend-next.oci.tar
│   ├── django-api.oci.tar
│   ├── traefik.oci.tar
│   ├── postgres.oci.tar
│   ├── redis.oci.tar
│   ├── celeryworker.oci.tar
│   ├── celerybeat.oci.tar
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
│   └── capsule-healthcheck.json
├── policies/
│   └── capsule-policy.json
├── metadata/
│   ├── build.json
│   └── source-inventory.json
├── checksums.txt
└── signature.sig
```

Optional private-only service archive:

```text
images/flower.oci.tar
```

The Builder must fail if the generated capsule structure does not match the canonical format.

The Builder must never produce a deployable-looking capsule whose `images/` directory contains only:

```text
images/README.json
```

That state is invalid because the Droplet runtime cannot start private app images without offline-loadable image archives.

---

## 6. Canonical Services Built or Exported by the CLI

The Builder must use canonical service names defined by `DOC-00`.

| Service         | Builder Responsibility                                                                           |
| --------------- | ------------------------------------------------------------------------------------------------ |
| `frontend-next` | Build Next.js production frontend image and export as `frontend-next.oci.tar`                    |
| `django-api`    | Build Django/Gunicorn backend image and export as `django-api.oci.tar`                           |
| `traefik`       | Pull/include approved Traefik image and export as `traefik.oci.tar`                              |
| `media-nginx`   | Pull/include approved media/static image and export as `media-nginx.oci.tar`                     |
| `postgres`      | Pull/include approved upstream image and export as `postgres.oci.tar`; no custom secret baked in |
| `redis`         | Pull/include approved upstream image and export as `redis.oci.tar`; no custom secret baked in    |
| `celeryworker`  | Reuse the `django-api` image and export a canonical `celeryworker.oci.tar` service archive       |
| `celerybeat`    | Reuse the `django-api` image and export a canonical `celerybeat.oci.tar` service archive         |
| `flower`        | Private-only optional service; may reuse the `django-api` image                                  |
| `kx-agent`      | Not bundled as an application service unless explicitly approved                                 |

The capsule must not include images with non-canonical service names unless the manifest maps them explicitly.

---

## 7. Canonical Image Tags and Archives

## 7.1 App Image Tags

The Builder should tag app-built images with capsule-scoped tags:

```text
konnaxion/frontend-next:<APP_VERSION>-<CAPSULE_ID>
konnaxion/django-api:<APP_VERSION>-<CAPSULE_ID>
```

Example:

```text
konnaxion/frontend-next:v14-konnaxion-v14-demo-2026.05.02
konnaxion/django-api:v14-konnaxion-v14-demo-2026.05.02
```

For runtime compose compatibility, the Agent may retag loaded images to:

```text
konnaxion/frontend-next:v14
konnaxion/django-api:v14
```

## 7.2 External Runtime Images

Approved default external images:

```text
traefik:v3.1
postgres:16
redis:7
nginx:stable
```

These must be exported into the capsule so a Droplet or offline runtime does not need registry access.

## 7.3 Archive Names

Archive names are canonical by service:

```text
images/frontend-next.oci.tar
images/django-api.oci.tar
images/traefik.oci.tar
images/postgres.oci.tar
images/redis.oci.tar
images/celeryworker.oci.tar
images/celerybeat.oci.tar
images/media-nginx.oci.tar
```

Even when multiple services share the same image tag, each canonical service should have a manifest-visible archive entry.

---

## 8. Frontend Image Contract

The Builder must build `frontend-next` as a production runtime image.

The runtime image must not require:

```text
pnpm download at runtime
Corepack download at runtime
network access during container start
development server command
```

The runtime image must include:

```text
package.json
node_modules/
.next/
public/
next.config.*
env.mjs
```

The runtime command must be equivalent to:

```bash
node node_modules/next/dist/bin/next start -H 0.0.0.0 -p 3000
```

The build stage must set:

```text
NODE_OPTIONS=--max-old-space-size=4096
NODE_ENV=production
```

A canonical frontend Dockerfile template is:

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --no-frozen-lockfile

COPY . .

ENV NODE_ENV=production
ENV NODE_OPTIONS=--max-old-space-size=4096

RUN pnpm build

FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.* ./
COPY --from=builder /app/env.mjs ./env.mjs

EXPOSE 3000

CMD ["node", "node_modules/next/dist/bin/next", "start", "-H", "0.0.0.0", "-p", "3000"]
```

---

## 9. Backend Image Contract

The Builder must build `django-api` as a production runtime image.

The Builder must not allow local virtualenvs, caches, stale generated files, or development artifacts to pollute the Docker build context.

The Builder must create or enforce a clean backend build context that excludes:

```text
.venv
venv
env
__pycache__
.pytest_cache
.mypy_cache
.ruff_cache
media
staticfiles
logs
*.pyc
*.pyo
*.pyd
*.sqlite3
*.log
```

The Builder must verify the backend context before build.

Required sanity checks:

```text
backend/konnaxion/ethikos/models.py exists
backend/konnaxion/ethikos/models.py must not contain migration-file content
backend/konnaxion/ethikos/models.py must contain expected app models
production Django Dockerfile exists
```

The Builder must fail if a source file is unexpectedly replaced by migration content, generated content, or an empty placeholder.

---

## 10. Build Pipeline

A canonical `kx capsule build` must execute these stages in order:

```text
1. Load build configuration
2. Validate repository layout
3. Validate canonical variables
4. Validate network profiles
5. Prepare clean backend Docker context
6. Build frontend production image
7. Build backend production image
8. Pull or verify approved external runtime images
9. Export all required runtime images as images/*.oci.tar
10. Generate images.yaml
11. Generate docker-compose.capsule.yml
12. Generate manifest.yaml
13. Generate env templates
14. Add profiles
15. Add migrations and optional seed data
16. Generate healthcheck templates
17. Run build-time tests and static checks
18. Run build-time security checks
19. Generate checksums.txt
20. Sign capsule
21. Verify finished capsule
22. Write .kxcap to output path
```

If any critical stage fails, the Builder must stop and return a non-zero exit code.

The Builder must not sign a capsule until image archives and checksums are complete.

---

## 11. Command: `kx capsule build`

## 11.1 Purpose

Build a new signed `Konnaxion Capsule`.

## 11.2 Canonical Syntax

```bash
kx capsule build \
  --source-dir ./Konnaxion \
  --output ./dist/capsules/konnaxion-v14-demo-2026.05.02.kxcap \
  --channel demo \
  --capsule-id konnaxion-v14-demo-2026.05.02 \
  --version 2026.05.02-demo.1 \
  --app-version v14 \
  --param-version kx-param-2026.04.30 \
  --profile public_vps \
  --signing-key-file ./runtime/signing/kx-demo-ed25519-private.pem \
  --public-key-file ./runtime/signing/kx-demo-ed25519-public.pem \
  --force
```

Compatibility form:

```bash
uv run kx-builder capsule build \
  --source-dir C:\mycode\Konnaxion\Konnaxion \
  --output C:\mycode\Konnaxion\runtime\capsules\konnaxion-v14-demo-2026.05.02.kxcap \
  --channel demo \
  --capsule-id konnaxion-v14-demo-2026.05.02 \
  --version 2026.05.02-demo.1 \
  --app-version v14 \
  --param-version kx-param-2026.04.30 \
  --profile public_vps \
  --signing-key-file C:\mycode\Konnaxion\runtime\signing\kx-demo-ed25519-private.pem \
  --public-key-file C:\mycode\Konnaxion\runtime\signing\kx-demo-ed25519-public.pem \
  --force
```

## 11.3 Common Options

| Option                |                     Required | Description                                              |
| --------------------- | ---------------------------: | -------------------------------------------------------- |
| `--source-dir`        |                          Yes | Source repo root containing `backend/` and `frontend/`   |
| `--output`            |                          Yes | Output `.kxcap` path                                     |
| `--channel`           |                          Yes | Build channel, e.g. `dev`, `demo`, `release`, `ci`       |
| `--capsule-id`        |                          Yes | Capsule ID, e.g. `konnaxion-v14-demo-2026.05.02`         |
| `--version`           |                          Yes | Capsule version, e.g. `2026.05.02-demo.1`                |
| `--app-version`       |                          Yes | Application version, e.g. `v14`                          |
| `--param-version`     |                          Yes | Parameter version, e.g. `kx-param-2026.04.30`            |
| `--profile`           |                          Yes | Default network profile to embed, e.g. `public_vps`      |
| `--signing-key-file`  | Required except unsigned dev | Private signing key                                      |
| `--public-key-file`   |                  Recommended | Public key used for verification metadata                |
| `--include-seed-data` |                           No | Include approved seed data                               |
| `--skip-tests`        |                           No | Skip tests; forbidden for release builds                 |
| `--unsigned`          |                           No | Produce unsigned dev capsule; forbidden for demo/release |
| `--force`             |                           No | Overwrite existing output                                |
| `--verbose`           |                           No | Detailed logs                                            |
| `--json`              |                           No | Machine-readable output                                  |

## 11.4 Example: Demo Capsule

```bash
kx capsule build \
  --source-dir ./Konnaxion \
  --output ./dist/capsules/konnaxion-v14-demo-2026.05.02.kxcap \
  --channel demo \
  --capsule-id konnaxion-v14-demo-2026.05.02 \
  --version 2026.05.02-demo.1 \
  --app-version v14 \
  --param-version kx-param-2026.04.30 \
  --profile public_vps \
  --include-seed-data \
  --signing-key-file ./runtime/signing/kx-demo-ed25519-private.pem \
  --public-key-file ./runtime/signing/kx-demo-ed25519-public.pem \
  --force
```

## 11.5 Example: Release Capsule

```bash
kx capsule build \
  --source-dir ./Konnaxion \
  --output ./dist/capsules/konnaxion-v14-release-2026.05.02.kxcap \
  --channel release \
  --capsule-id konnaxion-v14-release-2026.05.02 \
  --version 2026.05.02-release.1 \
  --app-version v14 \
  --param-version kx-param-2026.04.30 \
  --profile public_vps \
  --signing-key-file ./secrets/release-ed25519-private.pem \
  --public-key-file ./secrets/release-ed25519-public.pem
```

Release builds must be signed.

Release builds must not use:

```text
--skip-tests
--unsigned
```

Demo builds must be signed unless explicitly configured as development-only.

---

## 12. Command: `kx capsule verify`

## 12.1 Purpose

Verify a `.kxcap` file before import, distribution, or installation.

## 12.2 Syntax

```bash
kx capsule verify ./dist/capsules/konnaxion-v14-demo-2026.05.02.kxcap
```

Compatibility form:

```bash
uv run kx-builder capsule verify C:\mycode\Konnaxion\runtime\capsules\konnaxion-v14-demo-2026.05.02.kxcap
```

## 12.3 Required Checks

The verify command must check:

```text
capsule file exists
capsule extension is .kxcap
manifest.yaml exists
manifest schema is valid
docker-compose.capsule.yml exists
images.yaml exists
all required directories exist
all required profiles exist
all required image archives exist
all listed image archives exist
all listed image archives use .oci.tar suffix
all listed image archives are non-empty
all listed image archive checksums match images.yaml
checksums.txt exists
all checksums match
signature.sig exists
signature is valid when verifier provided
no forbidden secrets are present
no forbidden public ports are declared
no Docker socket mount is declared
no privileged containers are declared
no host network mode is declared
all service names are canonical or explicitly mapped
```

## 12.4 Mandatory Image Verification Failure Cases

Verification must fail if any of these are true:

```text
images/ contains only README.json
images.yaml is missing
images.yaml has no images
manifest declares service images but archive files are absent
frontend-next.oci.tar is missing
django-api.oci.tar is missing
traefik.oci.tar is missing
postgres.oci.tar is missing
redis.oci.tar is missing
celeryworker.oci.tar is missing
celerybeat.oci.tar is missing
media-nginx.oci.tar is missing
any archive checksum does not match
any archive is zero bytes
```

A capsule with this structure is invalid:

```text
images/
└── README.json
```

The verify command must not report `OK` for that capsule.

## 12.5 Output

Human-readable output:

```text
Konnaxion Capsule Verification

Capsule: konnaxion-v14-demo-2026.05.02.kxcap
Status: PASS

[PASS] manifest_schema
[PASS] image_archives_present
[PASS] image_checksums
[PASS] capsule_signature
[PASS] dangerous_ports_blocked
[PASS] docker_socket_not_mounted
[PASS] no_privileged_containers
[PASS] no_host_network
```

Machine-readable output:

```bash
kx capsule verify ./dist/capsules/konnaxion-v14-demo-2026.05.02.kxcap --json
```

Example JSON:

```json
{
  "capsule_id": "konnaxion-v14-demo-2026.05.02",
  "capsule_version": "2026.05.02-demo.1",
  "status": "PASS",
  "checks": [
    {
      "name": "manifest_schema",
      "status": "PASS"
    },
    {
      "name": "image_archives_present",
      "status": "PASS"
    },
    {
      "name": "capsule_signature",
      "status": "PASS"
    }
  ],
  "warnings": [],
  "errors": []
}
```

---

## 13. Command: `kx capsule inspect`

## 13.1 Purpose

Print metadata from a `.kxcap` file without importing it.

## 13.2 Syntax

```bash
kx capsule inspect konnaxion-v14-demo-2026.05.02.kxcap
```

## 13.3 Expected Output

```text
Capsule ID: konnaxion-v14-demo-2026.05.02
Capsule Version: 2026.05.02-demo.1
Application Version: v14
Parameter Version: kx-param-2026.04.30
Default Network Profile: public_vps
Default Exposure Mode: public
Services:
  - traefik
  - frontend-next
  - django-api
  - postgres
  - redis
  - celeryworker
  - celerybeat
  - media-nginx
Images:
  - images/traefik.oci.tar
  - images/frontend-next.oci.tar
  - images/django-api.oci.tar
  - images/postgres.oci.tar
  - images/redis.oci.tar
  - images/celeryworker.oci.tar
  - images/celerybeat.oci.tar
  - images/media-nginx.oci.tar
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

## 14. Command: `kx capsule list-profiles`

## 14.1 Purpose

List network profiles embedded in a capsule.

## 14.2 Syntax

```bash
kx capsule list-profiles konnaxion-v14-demo-2026.05.02.kxcap
```

## 14.3 Output

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

## 15. Command: `kx capsule export-manifest`

## 15.1 Purpose

Extract `manifest.yaml` from a capsule for inspection, auditing, or CI checks.

## 15.2 Syntax

```bash
kx capsule export-manifest konnaxion-v14-demo-2026.05.02.kxcap \
  --output ./dist/manifests/konnaxion-v14-demo-2026.05.02.manifest.yaml
```

---

## 16. Command: `kx capsule doctor`

## 16.1 Purpose

Check the local build environment.

## 16.2 Syntax

```bash
kx capsule doctor
```

## 16.3 Required Checks

```text
Docker available
Docker daemon running
Docker Compose available
Node.js available
pnpm available
Python available
backend source exists
frontend source exists
backend production Dockerfile exists
frontend package.json exists
frontend env.mjs exists
Git worktree status available
sufficient disk space
sufficient memory
signing key configured for demo/release builds
external images pullable or already available
```

Example:

```text
Konnaxion Builder Doctor

[PASS] docker_available
[PASS] docker_daemon_running
[PASS] docker_compose_available
[PASS] node_available
[PASS] pnpm_available
[PASS] python_available
[PASS] backend_root_exists
[PASS] frontend_root_exists
[PASS] backend_production_dockerfile_exists
[PASS] frontend_env_mjs_exists
[WARN] git_worktree_dirty
[PASS] signing_key_available
```

A dirty Git worktree may be allowed for development builds but should block release builds unless explicitly overridden.

---

## 17. Build Configuration File

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
  id: konnaxion-v14-demo-2026.05.02
  version: 2026.05.02-demo.1
  output: ./dist/capsules/konnaxion-v14-demo-2026.05.02.kxcap
  include_seed_data: true

profiles:
  default_network_profile: public_vps
  default_exposure_mode: public
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
  include_external_runtime_images: true
  generate_checksums: true
  sign_capsule: true
  clean_backend_context: true
```

Command using config:

```bash
kx capsule build --config kxbuild.yaml
```

Command-line flags override config values unless explicitly forbidden by the selected build profile.

---

## 18. Canonical `manifest.yaml`

The Builder must generate `manifest.yaml`.

Minimum required fields:

```yaml
project: Konnaxion
app_version: v14
capsule_id: konnaxion-v14-demo-2026.05.02
capsule_version: 2026.05.02-demo.1
param_version: kx-param-2026.04.30

default_network_profile: public_vps
default_exposure_mode: public

required_ram_mb: 4096
recommended_ram_mb: 8192

services:
  traefik:
    role: reverse_proxy
    public_entrypoint: true
    image: traefik:v3.1
    archive: images/traefik.oci.tar

  frontend-next:
    role: frontend
    internal_port: 3000
    image: konnaxion/frontend-next:v14
    archive: images/frontend-next.oci.tar

  django-api:
    role: backend_api
    internal_port: 5000
    image: konnaxion/django-api:v14
    archive: images/django-api.oci.tar

  postgres:
    role: database
    internal_only: true
    image: postgres:16
    archive: images/postgres.oci.tar

  redis:
    role: broker
    internal_only: true
    image: redis:7
    archive: images/redis.oci.tar

  celeryworker:
    role: background_worker
    internal_only: true
    image: konnaxion/django-api:v14
    archive: images/celeryworker.oci.tar

  celerybeat:
    role: scheduler
    internal_only: true
    image: konnaxion/django-api:v14
    archive: images/celerybeat.oci.tar

  media-nginx:
    role: media_static
    internal_only: true
    image: nginx:stable
    archive: images/media-nginx.oci.tar

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

## 19. Canonical `images.yaml`

The Builder must generate `images.yaml`.

Example:

```yaml
generated_at: "2026-05-02T21:24:27Z"
images:
  - service: frontend-next
    image: konnaxion/frontend-next:v14-konnaxion-v14-demo-2026.05.02
    archive: frontend-next.oci.tar
    sha256: "<sha256>"
    size_bytes: 524288000
    exported_at: "2026-05-02T21:24:27Z"

  - service: django-api
    image: konnaxion/django-api:v14-konnaxion-v14-demo-2026.05.02
    archive: django-api.oci.tar
    sha256: "<sha256>"
    size_bytes: 156237824
    exported_at: "2026-05-02T21:24:27Z"

  - service: traefik
    image: traefik:v3.1
    archive: traefik.oci.tar
    sha256: "<sha256>"
    size_bytes: 0
    exported_at: "2026-05-02T21:24:27Z"
```

The `archive` field is relative to:

```text
images/
```

The Builder must keep `images.yaml`, `manifest.yaml`, and `checksums.txt` consistent.

---

## 20. Canonical `docker-compose.capsule.yml`

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
Use image names that match manifest/image metadata
Use commands compatible with offline-loaded images
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

The Builder does not need to embed live public hostnames in `docker-compose.capsule.yml`.

The Agent owns final runtime rendering for:

```text
KX_HOST
DJANGO_ALLOWED_HOSTS
NEXT_PUBLIC_API_BASE
NEXT_PUBLIC_BACKEND_BASE
Traefik Host() rules
```

However, Builder output must contain enough route metadata for the Agent to render those values correctly.

---

## 21. Runtime Handoff Requirements for `public_vps`

A capsule built by DOC-10 must be usable by the Manager and Agent for `public_vps` deployment without manual editing.

For `public_vps`, the Agent must be able to generate:

```text
KX_HOST=<public host>
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,<public host>,django-api,kx-<instance>-django-api
NEXT_PUBLIC_API_BASE=https://<public host>/api
NEXT_PUBLIC_BACKEND_BASE=https://<public host>
Traefik file-provider rule Host(`<public host>`)
```

The Builder must not bake a specific Droplet host into the capsule.

The Builder must provide canonical placeholders:

```text
<GENERATED_FROM_PROFILE>
<SET_BY_MANAGER>
<GENERATED_ON_INSTALL>
```

The Manager and Agent must resolve those placeholders at import/create/start time.

---

## 22. Build-Time Secret Policy

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
cookies
authorization headers
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
NEXT_PUBLIC_API_BASE=<GENERATED_FROM_PROFILE>
NEXT_PUBLIC_BACKEND_BASE=<GENERATED_FROM_PROFILE>
```

---

## 23. Signing and Checksums

## 23.1 Checksums

The Builder must generate:

```text
checksums.txt
```

The checksum file must include all relevant files inside the capsule except `signature.sig`.

Recommended format:

```text
sha256  manifest.yaml
sha256  docker-compose.capsule.yml
sha256  images.yaml
sha256  images/frontend-next.oci.tar
sha256  images/django-api.oci.tar
sha256  images/traefik.oci.tar
sha256  images/postgres.oci.tar
sha256  images/redis.oci.tar
sha256  images/celeryworker.oci.tar
sha256  images/celerybeat.oci.tar
sha256  images/media-nginx.oci.tar
```

## 23.2 Signature

The Builder must generate:

```text
signature.sig
```

The signature must cover:

```text
checksums.txt
manifest.yaml
docker-compose.capsule.yml
images.yaml
profiles/
env-templates/
images/
healthchecks/
policies/
metadata/
```

Release and demo capsules must be signed.

Unsigned capsules are allowed only for local development and must be clearly marked:

```yaml
signature_status: unsigned_dev_only
```

The Manager and Agent must reject unsigned capsules unless explicitly running in a development mode.

---

## 24. Build Profiles

The Builder supports these build profiles:

| Build Profile |                  Purpose |                         Signed | Tests Required |     Seed Data |
| ------------- | -----------------------: | -----------------------------: | -------------: | ------------: |
| `dev`         |  Local developer testing |                       Optional |       Optional |      Optional |
| `demo`        |       Demo-ready capsule |                       Required |       Required |      Optional |
| `release`     | Production-grade capsule |                       Required |       Required | No by default |
| `ci`          |  Automated CI validation | Required for release artifacts |       Required |            No |

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

## 25. Required Build Checks

The Builder must perform these checks before producing a capsule:

```text
canonical_service_names
canonical_network_profiles
repository_layout_valid
clean_backend_context_valid
frontend_runtime_image_valid
backend_runtime_image_valid
external_images_available
image_export_complete
image_metadata_generated
no_real_secrets
no_public_internal_ports
no_docker_socket_mount
no_privileged_containers
no_host_network
manifest_schema
compose_schema
checksums_generated
signature_generated
capsule_verify_passes
```

For release builds, all required checks must pass.

For demo builds, all security checks must pass.

For dev builds, warnings may be allowed, but the capsule must be marked as development-only.

---

## 26. Output Status Values

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

| Build Result               | Meaning                                       |
| -------------------------- | --------------------------------------------- |
| `BUILD_PASS`               | Capsule produced and verified                 |
| `BUILD_PASS_WITH_WARNINGS` | Capsule produced, non-blocking warnings exist |
| `BUILD_FAIL`               | Build failed                                  |
| `BUILD_SECURITY_BLOCKED`   | Build blocked by security policy              |

---

## 27. Exit Codes

Canonical exit codes:

| Code | Meaning                 |
| ---: | ----------------------- |
|  `0` | Success                 |
|  `1` | General error           |
|  `2` | Invalid CLI usage       |
|  `3` | Build failed            |
|  `4` | Verification failed     |
|  `5` | Security policy failure |
|  `6` | Missing dependency      |
|  `7` | Signing failure         |
|  `8` | Manifest/schema failure |
|  `9` | File or path error      |

Scripts and CI systems should rely on these exit codes.

---

## 28. Logs

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
REDIS_URL password segment
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

## 29. JSON Output Contract

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
  "capsule_id": "konnaxion-v14-demo-2026.05.02",
  "capsule_version": "2026.05.02-demo.1",
  "output": "./dist/capsules/konnaxion-v14-demo-2026.05.02.kxcap",
  "images": [
    "images/frontend-next.oci.tar",
    "images/django-api.oci.tar"
  ],
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

## 30. CI Usage

A release pipeline should run:

```bash
kx capsule doctor
kx capsule build --config kxbuild.yaml
kx capsule verify ./dist/capsules/konnaxion-v14-demo-2026.05.02.kxcap
kx capsule inspect ./dist/capsules/konnaxion-v14-demo-2026.05.02.kxcap
```

Example CI release gate:

```bash
kx capsule verify ./dist/capsules/konnaxion-v14-demo-2026.05.02.kxcap --json > capsule-verify.json
```

The CI job must fail if:

```text
status != PASS
any check.status == FAIL_BLOCKING
signature is missing
release build is unsigned
forbidden secret is detected
forbidden port is exposed
required image archive is missing
image checksum mismatch exists
```

---

## 31. Developer Workflow

## 31.1 Local Dev Capsule

```bash
kx capsule doctor

kx capsule build \
  --source-dir ./Konnaxion \
  --output ./dist/capsules/konnaxion-v14-dev-2026.05.02.kxcap \
  --channel dev \
  --capsule-id konnaxion-v14-dev-2026.05.02 \
  --version 2026.05.02-dev.1 \
  --app-version v14 \
  --param-version kx-param-2026.04.30 \
  --profile local_only \
  --unsigned \
  --force
```

## 31.2 Demo Capsule

```bash
kx capsule build \
  --source-dir ./Konnaxion \
  --output ./dist/capsules/konnaxion-v14-demo-2026.05.02.kxcap \
  --channel demo \
  --capsule-id konnaxion-v14-demo-2026.05.02 \
  --version 2026.05.02-demo.1 \
  --app-version v14 \
  --param-version kx-param-2026.04.30 \
  --profile public_vps \
  --include-seed-data \
  --signing-key-file ./runtime/signing/kx-demo-ed25519-private.pem \
  --public-key-file ./runtime/signing/kx-demo-ed25519-public.pem \
  --force

kx capsule verify ./dist/capsules/konnaxion-v14-demo-2026.05.02.kxcap
```

## 31.3 Release Capsule

```bash
kx capsule build \
  --source-dir ./Konnaxion \
  --output ./dist/capsules/konnaxion-v14-release-2026.05.02.kxcap \
  --channel release \
  --capsule-id konnaxion-v14-release-2026.05.02 \
  --version 2026.05.02-release.1 \
  --app-version v14 \
  --param-version kx-param-2026.04.30 \
  --profile public_vps \
  --signing-key-file ./secrets/release-ed25519-private.pem \
  --public-key-file ./secrets/release-ed25519-public.pem

kx capsule verify ./dist/capsules/konnaxion-v14-release-2026.05.02.kxcap
```

---

## 32. Interaction With Manager and Agent

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

## 33. Import Contract

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
images.yaml
docker-compose.capsule.yml
profiles/
env-templates/
healthchecks/
policies/
```

No manual editing should be required after build.

The import contract must not require runtime backup data.

The capsule may declare backup-related capabilities, such as healthcheck names or required writable paths, but it must not contain backup sets, production database dumps, runtime secrets, or restore state.

Backup and restore behavior is defined by:

```text
DOC-09_Konnaxion_Backup_Restore_Rollback.md
```

---

## 34. Droplet/Public VPS Compatibility Requirements

A capsule built for `public_vps` must support the Manager/Agent Droplet flow:

```text
Manager on Windows
  -> SSH to Droplet
  -> private Agent at 127.0.0.1:8765
  -> import capsule
  -> load image archives
  -> create runtime env
  -> render Traefik file-provider config
  -> start instance
```

The Builder must ensure:

```text
all required images are offline-loadable
runtime compose never requires public registry pull for app images
frontend container starts without network access
backend container starts without local source bind mounts
metadata lets Agent set public host correctly
```

The Builder must not require:

```text
temporary SSH tunnel
public Agent listener
manual docker save/load
manual Traefik patch
manual DJANGO_ALLOWED_HOSTS patch
manual frontend Dockerfile patch
```

---

## 35. Security Requirements

The Builder must enforce these requirements:

```text
Private-by-default where applicable
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
Images archived and checksummed
Logs redacted
Release builds cannot skip tests
Release builds cannot be unsigned
Demo builds cannot be unsigned unless explicitly development-only
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

## 36. Forbidden Build Outputs

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
contains only images/README.json instead of images/*.oci.tar
requires runtime registry access for Konnaxion app images
requires runtime pnpm/corepack download for frontend start
```

---

## 37. Minimal Implementation Plan

## 37.1 MVP Builder

Minimum viable implementation:

```text
kx capsule build
kx capsule verify
kx capsule inspect
kx capsule doctor
```

MVP build features:

```text
build frontend production image
build backend production image from clean context
include Traefik/Postgres/Redis/media images
generate manifest.yaml
generate images.yaml
generate docker-compose.capsule.yml
include canonical profiles
include env templates
export image tar files
generate checksums
sign capsule
verify capsule
```

## 37.2 Phase 2

```text
JSON output
CI integration
schema command
stronger secret scanning
SBOM generation
image provenance metadata
release channels
delta capsules
image deduplication
```

## 37.3 Phase 3

```text
GUI integration
remote signing support
hardware appliance factory build
offline update packages
multi-instance build variants
registry-backed release promotion
```

---

## 38. Open Design Questions

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
whether duplicate image archives should be deduplicated by digest
```

These questions must not block the DOC-10 CLI contract.

---

## 39. Fixed Decisions

This document fixes the following decisions:

```text
Canonical CLI executable: kx
Canonical Builder group: kx capsule
Implementation compatibility executable: kx-builder
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
The Builder must generate images.yaml
The Builder must generate docker-compose.capsule.yml
The Builder must export all required image archives
The Builder must use canonical service names
The Builder must include canonical network profiles
Frontend runtime must not require Corepack/pnpm download
Backend image must be built from a clean context
DOC-10 owns build-time capsule commands only
DOC-10 does not own runtime backup, restore or rollback commands
DOC-10 may reference runtime commands only for handoff/alignment
```

---

## 40. Reference Command Summary

```bash
# Check local build environment
kx capsule doctor

# Build demo capsule
kx capsule build \
  --source-dir ./Konnaxion \
  --output ./dist/capsules/konnaxion-v14-demo-2026.05.02.kxcap \
  --channel demo \
  --capsule-id konnaxion-v14-demo-2026.05.02 \
  --version 2026.05.02-demo.1 \
  --app-version v14 \
  --param-version kx-param-2026.04.30 \
  --profile public_vps \
  --include-seed-data \
  --signing-key-file ./runtime/signing/kx-demo-ed25519-private.pem \
  --public-key-file ./runtime/signing/kx-demo-ed25519-public.pem \
  --force

# Verify capsule
kx capsule verify ./dist/capsules/konnaxion-v14-demo-2026.05.02.kxcap

# Inspect capsule
kx capsule inspect ./dist/capsules/konnaxion-v14-demo-2026.05.02.kxcap

# List embedded network profiles
kx capsule list-profiles ./dist/capsules/konnaxion-v14-demo-2026.05.02.kxcap

# Export manifest
kx capsule export-manifest ./dist/capsules/konnaxion-v14-demo-2026.05.02.kxcap \
  --output ./dist/manifests/konnaxion-v14-demo-2026.05.02.manifest.yaml
```

Compatibility command summary:

```bash
uv run kx-builder capsule build \
  --source-dir C:\mycode\Konnaxion\Konnaxion \
  --output C:\mycode\Konnaxion\runtime\capsules\konnaxion-v14-demo-2026.05.02.kxcap \
  --channel demo \
  --capsule-id konnaxion-v14-demo-2026.05.02 \
  --version 2026.05.02-demo.1 \
  --app-version v14 \
  --param-version kx-param-2026.04.30 \
  --profile public_vps \
  --signing-key-file C:\mycode\Konnaxion\runtime\signing\kx-demo-ed25519-private.pem \
  --public-key-file C:\mycode\Konnaxion\runtime\signing\kx-demo-ed25519-public.pem \
  --force

uv run kx-builder capsule verify C:\mycode\Konnaxion\runtime\capsules\konnaxion-v14-demo-2026.05.02.kxcap
```


