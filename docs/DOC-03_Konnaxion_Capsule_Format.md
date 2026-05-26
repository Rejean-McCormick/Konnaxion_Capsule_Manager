---
doc_id: DOC-03
filename: DOC-03_Konnaxion_Capsule_Format.md
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: draft
owner: Konnaxion Architecture
created_at: 2026-04-30
updated_at: 2026-05-03
depends_on:
  - DOC-00_Konnaxion_Canonical_Variables.md
  - DOC-02_Konnaxion_Capsule_Architecture.md
related_docs:
  - DOC-04_Konnaxion_Manager_Architecture.md
  - DOC-05_Konnaxion_Agent_Security_Model.md
  - DOC-06_Konnaxion_Network_Profiles.md
  - DOC-07_Konnaxion_Security_Gate.md
  - DOC-08_Konnaxion_Runtime_Docker_Compose.md
  - DOC-10_Konnaxion_Builder_CLI.md
---

# DOC-03 — Konnaxion Capsule Format

## 1. Purpose

This document defines the canonical file format for a **Konnaxion Capsule**.

A Konnaxion Capsule is the portable, signed, immutable package used by **Konnaxion Capsule Manager** to create or update a **Konnaxion Instance** on a **Konnaxion Box**, local host, intranet server, or VPS.

The capsule must support plug-and-play deployment while preserving the security model defined in DOC-00 and enforced by the **Konnaxion Agent**.

## 2. Canonical definition

```text
Konnaxion Capsule
= one portable .kxcap file
= application runtime contract + container images + manifest + profiles + templates + checksums + signature
= no real secrets
= no real production database
= no host-specific runtime state
```

The canonical extension is:

```text
.kxcap
```

The canonical package name pattern is:

```text
konnaxion-v14-<CHANNEL>-<YYYY.MM.DD>.kxcap
```

Examples:

```text
konnaxion-v14-demo-2026.04.30.kxcap
konnaxion-v14-intranet-2026.04.30.kxcap
konnaxion-v14-release-2026.04.30.kxcap
```

## 3. Design rules

The capsule format follows these rules:

```text
1. Immutable after build.
2. Signed before distribution.
3. Verified before import.
4. Deterministic where possible.
5. Private-by-default.
6. Deny-by-default networking.
7. No real secrets inside the capsule.
8. No production database dump inside the capsule unless encrypted and explicitly marked.
9. No direct public exposure of internal services.
10. No privileged containers unless explicitly approved by a future security review.
11. No runtime dependency on public package registries.
12. No runtime dependency on Docker image pulls.
13. No healthcheck dependency on tools absent from the selected image.
14. No public_vps runtime may silently fall back to 127.0.0.1 as its public host.
```

The capsule is not the installed instance.

```text
Capsule  = application artifact
Instance = running environment, generated secrets, data, logs, media, backups
```

## 4. High-level lifecycle

```text
Developer machine / CI
  ↓
kx capsule build
  ↓
.kxcap generated
  ↓
kx capsule verify
  ↓
Capsule signed and distributed
  ↓
Konnaxion Capsule Manager imports capsule
  ↓
Konnaxion Agent validates Security Gate
  ↓
Instance is created or updated
```

## 5. Archive container

### 5.1 Physical format

The MVP format is:

```text
tar archive + zstd compression
```

Canonical extension remains:

```text
.kxcap
```

Implementation detail:

```text
.kxcap = tar.zst with a Konnaxion manifest and signature layout
```

The extension must not be changed to `.tar.zst` for user-facing distribution.

### 5.2 Future-compatible alternatives

Future versions may support:

```text
OCI artifact
SquashFS image
encrypted capsule container
multi-architecture capsule index
```

These are not part of the MVP unless specified in a later document.

## 6. Required root layout

Every `.kxcap` file must contain this root structure:

```text
.kxcap
├── manifest.yaml
├── docker-compose.capsule.yml
├── images/
├── profiles/
├── env-templates/
├── migrations/
├── seed-data/
├── healthchecks/
├── policies/
├── metadata/
├── checksums.txt
└── signature.sig
```

The root entries are mandatory unless explicitly marked optional in this document.

A capsule whose `images/` directory contains only placeholder files such as `README.json` is invalid for deployable runtime profiles.

## 7. Root file responsibilities

| Path | Required | Purpose |
|---|---:|---|
| `manifest.yaml` | yes | Canonical machine-readable description of the capsule |
| `docker-compose.capsule.yml` | yes | Runtime service definition consumed by Konnaxion Agent |
| `images/` | yes | Offline-loadable OCI image archives |
| `profiles/` | yes | Network exposure profiles |
| `env-templates/` | yes | Secret-free environment templates |
| `migrations/` | yes | Database and application migration runners |
| `seed-data/` | optional | Demo or bootstrap data |
| `healthchecks/` | yes | Startup and readiness probes |
| `policies/` | yes | Security and runtime policy definitions |
| `metadata/` | yes | Build metadata, SBOM, changelog, compatibility info |
| `checksums.txt` | yes | Digest list for capsule contents |
| `signature.sig` | yes | Signature over the manifest and checksums |

## 8. `manifest.yaml`

`manifest.yaml` is the primary contract of the capsule.

It must be valid YAML and must pass the manifest schema version declared in the file.

### 8.1 Required fields

```yaml
schema_version: kxcap/v1
capsule_id: konnaxion-v14-demo-2026.04.30
capsule_version: 2026.04.30-demo.1
app_name: Konnaxion
app_version: v14
channel: demo
created_at: 2026-04-30T00:00:00Z
builder_version: kx-builder-0.1.0
minimum_manager_version: kx-manager-0.1.0
minimum_agent_version: kx-agent-0.1.0
architecture:
  - linux/amd64
runtime: docker-compose
required_ram_mb: 4096
recommended_ram_mb: 8192
default_network_profile: intranet_private
default_exposure_mode: private
```

### 8.2 Service declarations

The manifest must declare every service the capsule expects to run.

Canonical service names:

```yaml
services:
  traefik:
    role: reverse_proxy
    image: traefik:v3.1
    image_archive: images/traefik_v3.1_linux-amd64.oci.tar
    public_entrypoint: true
    internal: false

  frontend-next:
    role: frontend
    image: konnaxion/frontend-next:v14
    image_archive: images/konnaxion-frontend-next_v14_linux-amd64.oci.tar
    internal_port: 3000
    internal: true

  django-api:
    role: backend_api
    image: konnaxion/django-api:v14
    image_archive: images/konnaxion-django-api_v14_linux-amd64.oci.tar
    internal_port: 5000
    internal: true

  postgres:
    role: database
    image: postgres:16
    image_archive: images/postgres_16_linux-amd64.oci.tar
    internal_port: 5432
    internal: true
    persistent: true

  redis:
    role: broker
    image: redis:7
    image_archive: images/redis_7_linux-amd64.oci.tar
    internal_port: 6379
    internal: true
    persistent: true

  celeryworker:
    role: background_worker
    image: konnaxion/django-api:v14
    image_archive: images/konnaxion-django-api_v14_linux-amd64.oci.tar
    internal: true

  celerybeat:
    role: scheduler
    image: konnaxion/django-api:v14
    image_archive: images/konnaxion-django-api_v14_linux-amd64.oci.tar
    internal: true

  media-nginx:
    role: media_server
    image: nginx:stable
    image_archive: images/nginx_stable_linux-amd64.oci.tar
    internal_port: 80
    internal: true
```

`flower` is optional and must be private-only if included.

```yaml
  flower:
    role: celery_monitoring
    image: konnaxion/django-api:v14
    image_archive: images/konnaxion-django-api_v14_linux-amd64.oci.tar
    internal_port: 5555
    internal: true
    enabled_by_default: false
```

### 8.3 Route declarations

The manifest must declare canonical routes:

```yaml
routes:
  - path: /
    service: frontend-next
    upstream_port: 3000

  - path: /api/
    service: django-api
    upstream_port: 5000

  - path: /admin/
    service: django-api
    upstream_port: 5000

  - path: /media/
    service: media-nginx
    upstream_port: 80
```

No capsule may route public traffic directly to `postgres`, `redis`, `celeryworker`, `celerybeat`, or `flower`.

A route is considered infrastructure-reachable when Traefik forwards to the expected upstream. Application-level `4xx` responses from Django for `/api/`, `/admin/`, or `/media/` are not automatically infrastructure failures. Traefik’s own unmatched-router `404` is a failure.

### 8.4 Network profile declarations

The manifest must list allowed profile files:

```yaml
network_profiles:
  - id: local_only
    file: profiles/local_only.yaml
    default: false

  - id: intranet_private
    file: profiles/intranet_private.yaml
    default: true

  - id: private_tunnel
    file: profiles/private_tunnel.yaml
    default: false

  - id: public_temporary
    file: profiles/public_temporary.yaml
    default: false

  - id: public_vps
    file: profiles/public_vps.yaml
    default: false
```

Only one profile may have `default: true`.

### 8.5 Security declarations

The manifest must include:

```yaml
security:
  require_signed_capsule: true
  generate_secrets_on_install: true
  allow_unknown_images: false
  allow_privileged_containers: false
  allow_host_network: false
  allow_docker_socket_mount: false
  allow_public_database: false
  allow_public_redis: false
  allow_public_admin_dashboard: false
  default_exposure_mode: private
```

### 8.6 Data declarations

```yaml
data:
  postgres:
    persistent: true
    backup_required: true
    restore_supported: true

  redis:
    persistent: true
    backup_required: false
    restore_supported: false

  media:
    persistent: true
    backup_required: true
    restore_supported: true

  logs:
    persistent: true
    backup_required: false
    retention_days_default: 14
```

## 9. `docker-compose.capsule.yml`

This file defines the runtime stack used by Konnaxion Agent.

It must not be executed directly by end users unless in developer/debug mode.

The Agent is responsible for injecting:

```text
KX_INSTANCE_ID
KX_NETWORK_PROFILE
KX_EXPOSURE_MODE
KX_HOST
runtime env files
volume paths
profile-specific network bindings
Traefik dynamic file-provider config
```

### 9.1 Compose rules

The compose file must obey:

```text
1. No `privileged: true`.
2. No `network_mode: host`.
3. No Docker socket mount.
4. No bind mount to `/`, `/etc`, `/root`, `/var/run`, `/tmp`, or `/dev/shm`.
5. No direct public port mapping for internal services.
6. Traefik is the only public entrypoint.
7. Postgres and Redis are internal only.
8. Flower is disabled by default or private only.
9. public_vps must use the configured public host, never 127.0.0.1.
10. Runtime healthchecks must use commands available inside the selected image.
```

### 9.2 Canonical internal networks

```yaml
networks:
  kx_edge:
    internal: false
  kx_internal:
    internal: true
```

Expected network placement:

| Service | `kx_edge` | `kx_internal` |
|---|---:|---:|
| `traefik` | yes | yes |
| `frontend-next` | no | yes |
| `django-api` | no | yes |
| `media-nginx` | no | yes |
| `postgres` | no | yes |
| `redis` | no | yes |
| `celeryworker` | no | yes |
| `celerybeat` | no | yes |
| `flower` | no | yes |

### 9.3 Traefik file-provider runtime config

The canonical generated runtime must use Traefik file-provider config for instance routes.

Canonical generated file:

```text
/opt/konnaxion/instances/<INSTANCE_ID>/state/traefik-dynamic.yml
```

Example for public VPS:

```yaml
http:
  routers:
    kx-frontend:
      rule: "Host(`{{KX_HOST}}`) && PathPrefix(`/`)"
      entryPoints:
        - websecure
      tls: {}
      service: kx-frontend
      priority: 1

    kx-api:
      rule: "Host(`{{KX_HOST}}`) && PathPrefix(`/api/`)"
      entryPoints:
        - websecure
      tls: {}
      service: kx-api
      priority: 100

    kx-admin:
      rule: "Host(`{{KX_HOST}}`) && PathPrefix(`/admin/`)"
      entryPoints:
        - websecure
      tls: {}
      service: kx-api
      priority: 100

    kx-media:
      rule: "Host(`{{KX_HOST}}`) && PathPrefix(`/media/`)"
      entryPoints:
        - websecure
      tls: {}
      service: kx-media
      priority: 100

  services:
    kx-frontend:
      loadBalancer:
        servers:
          - url: "http://kx-{{INSTANCE_ID}}-frontend-next:3000"

    kx-api:
      loadBalancer:
        servers:
          - url: "http://kx-{{INSTANCE_ID}}-django-api:5000"

    kx-media:
      loadBalancer:
        servers:
          - url: "http://kx-{{INSTANCE_ID}}-media-nginx:80"
```

Docker labels may be emitted as metadata, but file-provider config is canonical for generated instance routing. Docker labels alone are not sufficient.

## 10. `images/`

The `images/` directory contains OCI-compatible image archives.

Canonical layout:

```text
images/
├── konnaxion-frontend-next_v14_linux-amd64.oci.tar
├── konnaxion-django-api_v14_linux-amd64.oci.tar
├── traefik_v3.1_linux-amd64.oci.tar
├── nginx_stable_linux-amd64.oci.tar
├── postgres_16_linux-amd64.oci.tar
└── redis_7_linux-amd64.oci.tar
```

The Agent imports these images using an allowlist derived from `manifest.yaml`.

No image may be loaded if:

```text
1. It is not declared in manifest.yaml.
2. Its archive is missing from images/.
3. Its digest does not match checksums.txt.
4. Its signature or provenance policy fails.
5. Its name collides with an existing unknown local image unless explicitly approved.
```

A capsule is invalid if:

```text
images/ contains only README.json
images/ is empty
manifest.yaml declares an image_archive that does not exist
checksums.txt omits an image_archive
a required runtime service has neither a declared image_archive nor an approved external-pull policy
```

### 10.1 Frontend image requirements

The `frontend-next` runtime image must be self-contained.

It must include:

```text
package.json
node_modules/
.next/
public/
next.config.*
env.mjs
```

It must not require runtime network access to install dependencies.

The canonical runtime command is:

```text
node node_modules/next/dist/bin/next start -H 0.0.0.0 -p 3000
```

The frontend image must not use runtime `pnpm start` if that requires Corepack to download `pnpm`.

### 10.2 Django image requirements

The `django-api` runtime image must contain the actual application source tree used for the build.

The Builder must prevent polluted or incorrect Docker build contexts. A built `django-api` image is invalid if application files are overwritten by migration files, virtualenv files, cache files, or generated artifacts.

The runtime must start the backend on:

```text
0.0.0.0:5000
```

### 10.3 Support image requirements

Support images may be based on upstream images, but the capsule must still include their offline-loadable archives unless the selected profile explicitly allows controlled image pulls.

Canonical support images for MVP:

```text
traefik:v3.1
nginx:stable
postgres:16
redis:7
```

## 11. `profiles/`

Network profile files define how the instance may be exposed.

Canonical profiles:

```text
profiles/local_only.yaml
profiles/intranet_private.yaml
profiles/private_tunnel.yaml
profiles/public_temporary.yaml
profiles/public_vps.yaml
```

### 11.1 `local_only.yaml`

```yaml
profile_id: local_only
exposure_mode: private
bind:
  - interface: loopback
    ports:
      - 443
allow_lan: false
allow_wan: false
requires_expiration: false
```

### 11.2 `intranet_private.yaml`

```yaml
profile_id: intranet_private
exposure_mode: lan
bind:
  - interface: lan
    ports:
      - 443
allow_lan: true
allow_wan: false
requires_expiration: false
```

### 11.3 `private_tunnel.yaml`

```yaml
profile_id: private_tunnel
exposure_mode: vpn
provider_options:
  - tailscale
allow_lan: false
allow_wan: false
requires_expiration: false
```

### 11.4 `public_temporary.yaml`

```yaml
profile_id: public_temporary
exposure_mode: temporary_tunnel
provider_options:
  - cloudflare_tunnel
  - tailscale_funnel
allow_lan: false
allow_wan: true
requires_expiration: true
max_duration_hours: 8
require_auth: true
```

### 11.5 `public_vps.yaml`

```yaml
profile_id: public_vps
exposure_mode: public
bind:
  - interface: public
    ports:
      - 80
      - 443
allow_lan: true
allow_wan: true
requires_expiration: false
requires_security_review: true
requires_public_host: true
```

For `public_vps`, the Manager must provide a canonical public host. The Agent must reject or fail configuration if the host is empty.

Valid examples:

```text
demo.example.com
138.197.174.76.sslip.io
```

Invalid generated public VPS host values:

```text
127.0.0.1
localhost
0.0.0.0
```

## 12. `env-templates/`

Environment templates define required runtime variables without storing real secrets.

Canonical files:

```text
env-templates/django.env.template
env-templates/postgres.env.template
env-templates/redis.env.template
env-templates/frontend.env.template
env-templates/kx.env.template
```

### 12.1 Django template

```env
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_SECRET_KEY={{GENERATED_ON_INSTALL}}
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS={{GENERATED_ALLOWED_HOSTS}}
DJANGO_CSRF_TRUSTED_ORIGINS={{GENERATED_CSRF_TRUSTED_ORIGINS}}
DJANGO_ADMIN_URL=admin/
USE_DOCKER=yes
DATABASE_URL=postgres://konnaxion:{{POSTGRES_PASSWORD}}@postgres:5432/konnaxion
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
SENTRY_DSN={{OPTIONAL_SENTRY_DSN}}
```

For `public_vps`, generated `DJANGO_ALLOWED_HOSTS` must include:

```text
127.0.0.1
localhost
{{KX_HOST}}
django-api
kx-{{INSTANCE_ID}}-django-api
```

For `public_vps`, generated `DJANGO_CSRF_TRUSTED_ORIGINS` must include:

```text
https://{{KX_HOST}}
http://{{KX_HOST}}
```

### 12.2 Postgres template

```env
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=konnaxion
POSTGRES_USER=konnaxion
POSTGRES_PASSWORD={{GENERATED_ON_INSTALL}}
```

### 12.3 Redis template

```env
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_URL=redis://redis:6379/0
```

### 12.4 Frontend template

```env
NEXT_PUBLIC_API_BASE={{KX_BASE_URL}}/api
NEXT_PUBLIC_BACKEND_BASE={{KX_BASE_URL}}
NEXT_TELEMETRY_DISABLED=1
NODE_OPTIONS=--max-old-space-size=4096
```

For `public_vps`, `KX_BASE_URL` must resolve to:

```text
https://{{KX_HOST}}
```

It must not resolve to `https://127.0.0.1`.

### 12.5 Konnaxion runtime template

```env
KX_INSTANCE_ID={{INSTANCE_ID}}
KX_CAPSULE_ID={{CAPSULE_ID}}
KX_CAPSULE_VERSION={{CAPSULE_VERSION}}
KX_APP_VERSION=v14
KX_PARAM_VERSION=kx-param-2026.04.30
KX_NETWORK_PROFILE={{NETWORK_PROFILE}}
KX_EXPOSURE_MODE={{EXPOSURE_MODE}}
KX_PUBLIC_MODE_ENABLED=false
KX_PUBLIC_MODE_EXPIRES_AT=
KX_HOST={{GENERATED_FROM_NETWORK_PROFILE}}
KX_REQUIRE_SIGNED_CAPSULE=true
KX_GENERATE_SECRETS_ON_INSTALL=true
KX_ALLOW_UNKNOWN_IMAGES=false
KX_ALLOW_PRIVILEGED_CONTAINERS=false
KX_ALLOW_DOCKER_SOCKET_MOUNT=false
KX_ALLOW_HOST_NETWORK=false
KX_BACKUP_ENABLED=true
KX_BACKUP_RETENTION_DAYS=14
```

For `public_vps`, generated values must include:

```env
KX_NETWORK_PROFILE=public_vps
KX_EXPOSURE_MODE=public
KX_PUBLIC_MODE_ENABLED=true
KX_HOST={{PUBLIC_HOST}}
```

## 13. `migrations/`

The `migrations/` directory contains controlled runtime migration entrypoints.

Canonical layout:

```text
migrations/
├── migrate.sh
├── collectstatic.sh
├── create_initial_admin.sh
├── seed_demo_data.sh
└── migration-policy.yaml
```

### 13.1 Migration policy

```yaml
migration_policy:
  run_database_migrations_on_first_start: true
  run_database_migrations_on_update: true
  require_backup_before_update_migration: true
  allow_destructive_migrations: false
  allow_manual_override: false
```

### 13.2 Required migration behavior

The Agent must:

```text
1. Create or verify database connectivity.
2. Run Django migrations.
3. Collect static files if required.
4. Load seed data only if the selected channel/profile allows it.
5. Refuse destructive migrations unless explicitly approved by a future migration policy.
```

## 14. `seed-data/`

Seed data is optional.

Canonical layout:

```text
seed-data/
├── demo-users.json
├── demo-content.json
├── demo-projects.json
└── seed-policy.yaml
```

Seed data must be clearly marked:

```yaml
seed_policy:
  channel: demo
  contains_personal_data: false
  safe_for_public_demo: true
  requires_user_confirmation: false
  can_run_on_existing_instance: false
```

No production personal data may be included in seed files.

## 15. `healthchecks/`

The `healthchecks/` directory declares readiness and runtime checks.

Canonical file:

```text
healthchecks/checks.yaml
```

Example:

```yaml
checks:
  - id: frontend_ready
    type: http
    url: http://frontend-next:3000/
    expected_status_any:
      - 200
      - 301
      - 302
      - 308
    required: true

  - id: django_socket_ready
    type: tcp
    host: django-api
    port: 5000
    required: true

  - id: django_route_reachable
    type: http
    url: http://django-api:5000/api/
    expected_status_any:
      - 200
      - 400
      - 401
      - 403
      - 404
    required: true

  - id: postgres_ready
    type: tcp
    host: postgres
    port: 5432
    required: true

  - id: redis_ready
    type: tcp
    host: redis
    port: 6379
    required: true

  - id: public_gateway_ready
    type: http
    url: '{{KX_BASE_URL}}/'
    expected_status_any:
      - 200
      - 301
      - 302
      - 308
    required: true
```

### 15.1 Healthcheck tool rules

Healthchecks must not depend on absent tools.

Examples of fragile healthchecks:

```text
wget inside an image that does not include wget
curl inside an image that does not include curl
shell pipelines that assume bash in an sh-only image
```

Canonical Django runtime healthcheck:

```text
python -c "import socket; sock=socket.create_connection(('127.0.0.1',5000),5); sock.close()"
```

The Django healthcheck validates that Gunicorn/Uvicorn is listening. Public HTTP route validation is a separate Traefik route check.

### 15.2 Route check classification

Route checks must distinguish:

```text
Traefik unmatched-router 404     = FAIL
Frontend / returns 2xx/3xx       = PASS
Django /api/ returns Django 4xx  = PASS for infrastructure reachability
Django /admin/ returns Django 4xx = PASS for infrastructure reachability
Django 5xx                       = FAIL
Connection refused/timeout       = FAIL
```

A Django `404` or `400` with Uvicorn/Django headers proves the route reached Django. It is not equivalent to Traefik’s default `404 page not found`.

## 16. `policies/`

The `policies/` directory contains validation policies enforced before import and before start.

Canonical files:

```text
policies/security-policy.yaml
policies/network-policy.yaml
policies/runtime-policy.yaml
policies/backup-policy.yaml
```

### 16.1 Security policy

```yaml
security_policy:
  require_signature: true
  require_checksums: true
  block_unknown_images: true
  block_missing_image_archives: true
  block_privileged_containers: true
  block_host_network: true
  block_docker_socket_mount: true
  block_public_database: true
  block_public_redis: true
  block_public_flower: true
  block_shell_hooks: true
```

### 16.2 Network policy

```yaml
network_policy:
  allowed_public_ports:
    - 80
    - 443
  allowed_lan_ports:
    - 443
  blocked_ports:
    - 3000
    - 5000
    - 5432
    - 5555
    - 6379
    - 8000
  public_mode_requires_expiration: false
  public_vps_requires_public_host: true
```

### 16.3 Runtime policy

```yaml
runtime_policy:
  allowed_runtime: docker-compose
  allow_kubernetes: false
  allow_serverless: false
  allow_custom_shell_commands: false
  allow_arbitrary_compose_override: false
  require_offline_runtime_images: true
```

## 17. `metadata/`

Canonical layout:

```text
metadata/
├── build-info.yaml
├── sbom.spdx.json
├── changelog.md
├── compatibility.yaml
├── release-notes.md
└── provenance.json
```

### 17.1 `build-info.yaml`

```yaml
build:
  built_at: 2026-04-30T00:00:00Z
  built_by: kx-builder
  source_repo: Konnaxion
  source_ref: main
  source_commit: '<GIT_COMMIT_SHA>'
  dirty_worktree: false
  ci_run_id: '<CI_RUN_ID>'
```

### 17.2 `compatibility.yaml`

```yaml
compatibility:
  minimum_manager_version: kx-manager-0.1.0
  minimum_agent_version: kx-agent-0.1.0
  supported_platforms:
    - linux/amd64
  minimum_ram_mb: 4096
  recommended_ram_mb: 8192
  minimum_disk_free_gb: 20
```

### 17.3 `provenance.json`

`provenance.json` must identify:

```text
source commit
builder version
image tags
image digests
image archive filenames
build platform
timestamp
signing key identity or key fingerprint
```

## 18. `checksums.txt`

`checksums.txt` must contain a digest for every file except `signature.sig`.

Canonical format:

```text
sha256  manifest.yaml  <digest>
sha256  docker-compose.capsule.yml  <digest>
sha256  images/konnaxion-frontend-next_v14_linux-amd64.oci.tar  <digest>
sha256  images/konnaxion-django-api_v14_linux-amd64.oci.tar  <digest>
sha256  images/traefik_v3.1_linux-amd64.oci.tar  <digest>
sha256  images/nginx_stable_linux-amd64.oci.tar  <digest>
sha256  images/postgres_16_linux-amd64.oci.tar  <digest>
sha256  images/redis_7_linux-amd64.oci.tar  <digest>
```

The Agent must refuse import if:

```text
1. checksums.txt is missing.
2. a listed file is missing.
3. an unlisted file exists, unless allowed by schema.
4. any digest mismatch occurs.
5. a required image archive is missing.
6. images/ contains only placeholder files.
```

## 19. `signature.sig`

`signature.sig` signs:

```text
manifest.yaml
checksums.txt
metadata/provenance.json
```

The signature does not replace file checksums. Both are required.

Initial signing approach:

```text
Ed25519 detached signature
```

Future signing approaches may include:

```text
Sigstore/cosign
hardware-backed signing key
organization-level release signing
```

The Manager must show signature status before import:

```text
Capsule signature: valid
Signer: Konnaxion Release Key
Capsule ID: konnaxion-v14-demo-2026.04.30
Capsule version: 2026.04.30-demo.1
```

## 20. Forbidden capsule contents

A `.kxcap` file must not contain:

```text
real DJANGO_SECRET_KEY
real POSTGRES_PASSWORD
real DATABASE_URL with password
SSH private keys
API keys
provider tokens
Git tokens
private certificates
raw production database dump
old server crontabs
old systemd service files from compromised hosts
/tmp contents
/dev/shm contents
unknown Docker volumes
local .venv or virtualenv content
node_modules from the developer workstation
Docker build cache
test reports
coverage reports
```

If a forbidden item is detected, the Agent must return:

```text
FAIL_BLOCKING
```

## 21. Install-time generated material

The following must be generated on install, not packaged inside the capsule:

```text
DJANGO_SECRET_KEY
POSTGRES_PASSWORD
KX_INSTANCE_ID if not provided
initial admin password or invite token
local TLS material if using local/intranet profile
runtime env files
instance-specific Traefik dynamic config
backup encryption key if enabled
```

## 22. Instance output after import

After import and start, the Manager/Agent creates:

```text
/opt/konnaxion/instances/<INSTANCE_ID>/
├── env/
│   ├── django.env
│   ├── postgres.env
│   ├── redis.env
│   ├── frontend.env
│   └── kx.env
├── postgres/
├── redis/
├── media/
├── logs/
├── backups/
├── state/
│   ├── docker-compose.runtime.yml
│   └── traefik-dynamic.yml
└── runtime/
```

The capsule remains stored separately:

```text
/opt/konnaxion/capsules/<CAPSULE_ID>.kxcap
```

Extracted capsule contents remain stored separately:

```text
/opt/konnaxion/shared/capsules/<CAPSULE_ID>/
```

## 23. Validation flow

Before import:

```text
1. Verify physical archive format.
2. Read manifest.yaml.
3. Validate manifest schema.
4. Verify checksums.txt.
5. Verify signature.sig.
6. Validate service allowlist.
7. Validate image allowlist.
8. Validate required image archives exist.
9. Validate image archive checksums.
10. Validate profiles.
11. Validate security policies.
12. Confirm compatibility with Manager and Agent versions.
```

Before start:

```text
1. Generate missing secrets.
2. Render env templates.
3. Render network profile.
4. Validate public host for public_vps.
5. Create internal Docker networks.
6. Create persistent volumes.
7. Load allowed images.
8. Apply firewall/profile rules.
9. Render Traefik dynamic config.
10. Run Security Gate.
11. Run migrations.
12. Start services.
13. Run healthchecks.
```

## 24. Security Gate required checks

Every capsule must support the following Security Gate checks:

```text
capsule_signature
image_checksums
image_archives_present
manifest_schema
secrets_present
secrets_not_default
firewall_enabled
dangerous_ports_blocked
postgres_not_public
redis_not_public
docker_socket_not_mounted
no_privileged_containers
no_host_network
allowed_images_only
admin_surface_private
backup_configured
public_host_valid
runtime_routes_valid
```

Status values:

```text
PASS
WARN
FAIL_BLOCKING
SKIPPED
UNKNOWN
```

Any of these must block startup if they fail:

```text
capsule_signature
image_checksums
image_archives_present
manifest_schema
dangerous_ports_blocked
postgres_not_public
redis_not_public
docker_socket_not_mounted
no_privileged_containers
no_host_network
allowed_images_only
public_host_valid
```

## 25. Update semantics

A capsule update must never modify a running instance blindly.

Required update flow:

```text
1. Import new capsule.
2. Verify new capsule.
3. Compare compatibility.
4. Backup current instance database and media.
5. Create update transaction.
6. Stop affected services.
7. Switch images/config.
8. Run migrations.
9. Start services.
10. Run healthchecks.
11. Mark update complete.
```

If healthchecks fail:

```text
1. Stop new services.
2. Restore previous capsule reference.
3. Restore previous runtime configuration.
4. Restart old services.
5. Mark update as failed.
6. Preserve logs for inspection.
```

## 26. Rollback metadata

Each capsule import must record rollback metadata:

```yaml
rollback:
  previous_capsule_id: konnaxion-v14-demo-2026.04.20
  previous_capsule_version: 2026.04.20-demo.1
  backup_id: backup-demo-001-20260430-170000
  migration_state_before: '<MIGRATION_HASH>'
  migration_state_after: '<MIGRATION_HASH>'
```

Database rollback is only allowed if a compatible backup exists.

## 27. Developer build command

Canonical command:

```bash
kx capsule build \
  --channel demo \
  --app-version v14 \
  --profile intranet_private \
  --output konnaxion-v14-demo-2026.04.30.kxcap
```

Public VPS demo command:

```bash
kx capsule build \
  --channel demo \
  --app-version v14 \
  --profile public_vps \
  --output konnaxion-v14-demo-2026.04.30.kxcap
```

Expected builder phases:

```text
1. verify clean source tree
2. create clean backend Docker build context
3. create clean frontend Docker build context
4. install dependencies
5. run backend tests
6. run frontend typecheck
7. build frontend
8. build backend image
9. build frontend image
10. build support images
11. export OCI images into images/
12. generate manifest
13. verify image archives exist
14. generate checksums
15. generate SBOM/provenance
16. sign capsule
17. verify final capsule
```

The Builder must fail if required image archives are missing. It must not produce a deployable-looking capsule containing only `images/README.json`.

## 28. Manager import command

Canonical command:

```bash
kx capsule import konnaxion-v14-demo-2026.04.30.kxcap
```

Canonical start command:

```bash
kx instance start demo-001 --network intranet_private
```

Canonical verification command:

```bash
kx security check demo-001
```

For Droplet/VPS deployment, the Manager must reach the private Droplet Agent through SSH-local HTTP unless a real non-loopback `remote_agent_url` is explicitly configured:

```text
Manager on Windows
  -> ssh root@<droplet_host>
  -> curl http://127.0.0.1:8765/v1/...
  -> Droplet Agent
```

The Manager must not require a temporary localhost tunnel for normal Droplet deploy.

## 29. MVP scope

The MVP capsule format includes:

```text
.kxcap tar.zst archive
manifest.yaml
Docker Compose runtime
OCI image archives
network profiles
secret-free env templates
migrations
healthchecks
checksums
signature
Security Gate policies
Traefik file-provider runtime config
public_vps host propagation
```

The MVP does not include:

```text
multi-node clustering
Kubernetes runtime
automatic cloud provisioning
embedded production data
third-party app marketplace
arbitrary plugin system
full remote fleet management
```

## 30. Acceptance criteria

A capsule is valid only if:

```text
1. It imports on a clean Konnaxion Box.
2. It starts in local_only mode with no network exposure.
3. It starts in intranet_private mode with only HTTPS exposed to LAN.
4. It starts in public_vps mode with a configured public host.
5. It refuses public_vps mode if host is missing or loopback-only.
6. It refuses to expose Postgres publicly.
7. It refuses to expose Redis publicly.
8. It refuses to expose Next.js direct port 3000 publicly.
9. It refuses Docker socket mounts.
10. It generates fresh secrets on install.
11. It renders DJANGO_ALLOWED_HOSTS from the selected network profile.
12. It renders NEXT_PUBLIC_API_BASE from the selected network profile.
13. It renders Traefik dynamic routes for the selected host.
14. It runs database migrations successfully.
15. It passes healthchecks.
16. It can be backed up.
17. It can be stopped and restarted.
18. It can be updated with rollback metadata.
19. It contains required OCI image archives.
20. It fails verification when required image archives are missing.
```

## 31. Open decisions

These are intentionally not finalized in DOC-03:

```text
1. Exact signing implementation: raw Ed25519 vs cosign/Sigstore.
2. Exact local TLS strategy for intranet mode.
3. Whether `.kxcap` should support encryption at rest in MVP.
4. Whether seed data should be split by module.
5. Whether frontend build occurs only at capsule-build time or may be host-rebuilt in developer mode.
6. Whether Konnaxion Box should support rootless Docker in MVP.
7. Whether support images must always be embedded or may use a signed/pinned external registry policy.
8. Whether public_vps should require a real DNS domain or allow sslip.io/nip.io style demo hosts.
```

These decisions belong in:

```text
DOC-05_Konnaxion_Agent_Security_Model.md
DOC-06_Konnaxion_Network_Profiles.md
DOC-07_Konnaxion_Security_Gate.md
DOC-10_Konnaxion_Builder_CLI.md
DOC-11_Konnaxion_Box_Appliance_Image.md
```

## 32. Summary

The Konnaxion Capsule format defines a secure, portable, plug-and-play package for deploying Konnaxion without exposing the user to Docker, Traefik, env files, database setup, firewall rules, or manual migrations.

The capsule is immutable and signed. The instance is generated locally. Secrets are created at install time. Network exposure is controlled by predefined profiles. Internal services remain private. Public mode is never the default.

For VPS deployment, the capsule must include offline-loadable image archives, the Agent must generate correct public runtime configuration, and healthchecks must distinguish infrastructure failure from application-level route responses.

Canonical target:

```text
Konnaxion Capsule
  ↓
Konnaxion Capsule Manager
  ↓
Konnaxion Agent
  ↓
Security Gate
  ↓
Docker Compose Runtime
  ↓
Konnaxion Instance
```