doc_id: DOC-15
title: Konnaxion Developer Guide
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: draft
depends_on:
  - DOC-00_Konnaxion_Canonical_Variables.md
  - DOC-02_Konnaxion_Capsule_Architecture.md
  - DOC-03_Konnaxion_Capsule_Format.md
  - DOC-04_Konnaxion_Manager_Architecture.md
  - DOC-05_Konnaxion_Agent_Security_Model.md
  - DOC-06_Konnaxion_Network_Profiles.md
  - DOC-07_Konnaxion_Security_Gate.md
  - DOC-08_Konnaxion_Runtime_Docker_Compose.md
  - DOC-10_Konnaxion_Builder_CLI.md
---

# DOC-15 — Konnaxion Developer Guide

## 1. Purpose

This document defines the canonical developer workflow for **Konnaxion v14** and the new **Konnaxion Capsule** architecture.

It is intended for developers working on:

- Konnaxion frontend
- Konnaxion backend
- Konnaxion Docker runtime
- Konnaxion Capsule Builder
- Konnaxion Capsule Manager
- Konnaxion Agent
- deployment, security, backup, and release tooling

This guide is not an operator guide. Operational use of a deployed appliance is covered by:

```text
DOC-14_Konnaxion_Operator_Guide.md
````

This guide is not a security model. Agent and runtime security are covered by:

```text
DOC-05_Konnaxion_Agent_Security_Model.md
DOC-07_Konnaxion_Security_Gate.md
DOC-13_Konnaxion_Threat_Model.md
```

---

## 2. Canonical stack

Konnaxion v14 must be treated as the following stack:

```text
Frontend: Next.js / React / TypeScript
Backend: Django 5.1 + Django REST Framework
Database: PostgreSQL
Background jobs: Celery
Broker/result backend: Redis
Reverse proxy: Traefik
Media/static service: Nginx
Runtime target: Docker Compose
```

The platform currently uses a **Next.js frontend**, **Django + DRF backend**, **PostgreSQL**, and **Celery + Redis** for background processing. It is organized around five primary modules — Kollective Intelligence, ethiKos, keenKonnect, KonnectED, Kreative — plus common core and Reports/Insights. 

---

## 3. Repository layout

Canonical local repository root:

```text
C:\mycode\Konnaxion\Konnaxion
```

Canonical main directories:

```text
Konnaxion/
├── backend/
├── frontend/
├── docs/
├── PlantUML/
├── Structurizr/
├── EndPoints-Graphs/
├── demoVideo/
├── package.json
├── pnpm-lock.yaml
└── workspace.dsl
```

The project contains backend code, frontend code, docs, PlantUML diagrams, Structurizr architecture files, endpoint graphs, and technical reference material under `docs/Technical-Reference`. 

---

## 4. Development principles

## 4.1 Do not guess

When modifying Konnaxion, developers must not invent architecture that contradicts the existing implementation.

Canonical rules:

```text
Do not rename the project.
Do not replace Django/DRF with another backend framework.
Do not replace REST with GraphQL unless explicitly approved.
Do not assume Redis is only a cache.
Do not introduce Tailwind into the Django backend layer.
Do not create a second frontend shell.
Do not create a second Celery app.
Do not bypass the services layer for frontend API calls.
Do not expose internal runtime ports publicly.
```

The codebase instructions explicitly state that Konnaxion uses Django 5.1 + DRF + Celery + Redis on the backend, Next.js/React on the frontend, PostgreSQL as the production relational database, and Redis as Celery broker/result backend, not merely as a cache. 

## 4.2 Preserve modular domains

Konnaxion is a modular platform. Developers must add features to the correct domain instead of collapsing everything into one generic model or service.

Canonical backend domains:

```text
users
kollective_intelligence
ethikos
keenkonnect
konnected
kreative
trust
teambuilder
```

The backend documentation identifies real separate domain apps and warns against putting everything in one model. 

---

## 5. Backend development

## 5.1 Backend root

```text
backend/
```

Key files:

```text
backend/manage.py
backend/config/settings/base.py
backend/config/settings/local.py
backend/config/settings/production.py
backend/config/settings/test.py
backend/config/urls.py
backend/config/asgi.py
backend/config/wsgi.py
backend/config/celery_app.py
```

Canonical settings modules:

```text
config.settings.base
config.settings.local
config.settings.production
config.settings.test
```

Canonical assumptions:

```text
AUTH_USER_MODEL = "users.User"
ROOT_URLCONF = "config.urls"
WSGI application = config.wsgi.application
ASGI application = config.asgi.application
```

These settings and import paths are part of the Konnaxion backend ground truth. 

---

## 5.2 Backend local Docker workflow

When backend code, models, or dependencies change:

```powershell
cd C:\mycode\Konnaxion\Konnaxion\backend
docker-compose -f docker-compose.local.yml up -d --build
```

Generate migrations:

```powershell
docker-compose -f docker-compose.local.yml run --rm django python manage.py makemigrations
```

Apply migrations:

```powershell
docker-compose -f docker-compose.local.yml run --rm django python manage.py migrate
```

Check services:

```powershell
docker-compose -f docker-compose.local.yml ps
```

Create a superuser when needed:

```powershell
docker-compose -f docker-compose.local.yml run --rm django python manage.py createsuperuser
```

The backend migration workflow is already documented around `docker-compose.local.yml`, `makemigrations`, `migrate`, `ps`, and optional `createsuperuser`. 

---

## 5.3 Backend coding rules

When adding a backend feature:

```text
1. Identify the correct domain app.
2. Add or modify models in that app only.
3. Add migrations.
4. Add serializers.
5. Add permissions if required.
6. Add API views or ViewSets.
7. Register routes through the canonical router or app urls.
8. Add tests.
9. Update docs if routes, models, or parameters changed.
```

Do not:

```text
use auth.User directly
create duplicate Celery apps
invent settings module names
place unrelated features into users
add hardcoded environment values
commit real .env files
paste secrets into docs, logs, commits, or chats
```

---

## 5.4 Celery rules

Canonical Celery facts:

```text
Celery app name: konnaxion
Celery config file: backend/config/celery_app.py
Broker: REDIS_URL
Result backend: REDIS_URL
Beat scheduler: django_celery_beat.schedulers:DatabaseScheduler
```

When writing tasks:

```python
from celery import shared_task

@shared_task
def example_task():
    ...
```

Do not define another Celery app.

Celery workers and beat are part of the current backend structure and should rely on autodiscovery and Redis-backed configuration. 

---

## 6. Frontend development

## 6.1 Frontend root

```text
frontend/
```

The frontend is a Next.js / React / TypeScript application using the App Router and modular feature folders.

Canonical frontend concepts:

```text
global shell
shared layout
module pages
services layer
theme context/tokens
ThemeSwitcher
routes*.tsx
routes.json
routes-tests.json
```

The frontend has a global layout system with components such as `MainLayout`, `Header`, `Sider`, and `PageContainer`; module UIs plug into the shared shell rather than creating independent root apps. 

---

## 6.2 Frontend module rules

When adding a frontend screen:

```text
1. Add the screen under the correct module folder.
2. Use the existing global layout and page containers.
3. Use existing shared components where possible.
4. Register the route in the correct routing file.
5. Use the services layer for API calls.
6. Run typecheck.
7. Run production build.
```

Do not:

```text
create a second root layout
create module-specific independent apps
bypass the services layer
invent new API prefixes
invent new theme state
add a second ThemeSwitcher
assume Tailwind dark mode
```

The current frontend module pattern uses per-domain folders such as `modules/ethikos`, `modules/keenkonnect`, `modules/konnected`, `modules/kreative`, `modules/admin`, `modules/insights`, `modules/konsensus`, and `modules/konsultations`, with centralized routing files. 

---

## 6.3 Frontend API rules

Canonical backend API base:

```text
/api/
```

Canonical API prefixes include:

```text
/api/users/
/api/ethikos/topics/
/api/ethikos/stances/
/api/ethikos/arguments/
/api/ethikos/categories/
/api/keenkonnect/projects/
/api/kollective/votes/
/api/konnected/resources/
/api/konnected/certifications/paths/
/api/konnected/certifications/evaluations/
/api/konnected/certifications/peer-validations/
/api/konnected/portfolios/
/api/konnected/certifications/exam-attempts/
/api/kreative/artworks/
/api/kreative/galleries/
```

Compatibility aliases:

```text
/api/deliberate/
/api/deliberate/elite/
```

Do not rename `/api/ethikos/...` to `/api/deliberation/...` or similar. Frontend API calls should use the services layer and existing path prefixes. 

---

## 6.4 Frontend build workflow

Before deployment or capsule build:

```powershell
cd C:\mycode\Konnaxion\Konnaxion\frontend
pnpm install --frozen-lockfile
pnpm exec tsc --noEmit --pretty false
$env:NODE_OPTIONS="--max-old-space-size=4096"
pnpm build
```

Important rules:

```text
Run pnpm build from frontend/, not repo root.
Set NODE_OPTIONS=--max-old-space-size=4096 for large production builds.
Do not restart a production frontend until .next/BUILD_ID exists.
```

The frontend deployment runbook explicitly requires building from the `frontend` directory and setting `NODE_OPTIONS=--max-old-space-size=4096` to avoid Next.js heap out-of-memory failures. 

---

## 6.5 Reports / Insights routes

Canonical Reports routes:

```text
/reports
/reports/custom
/reports/smart-vote
/reports/usage
/reports/perf
```

These routes are real implemented routes and must remain aligned across navigation, UI specs, and technical references. 

Do not ignore:

```text
frontend/app/reports/
frontend/app/reports/ReportsPageShell.tsx
```

The deployment guide notes that `frontend/app/reports/` contains real Next.js routes and that missing `ReportsPageShell.tsx` can break production builds. 

---

## 7. Runtime and deployment development

## 7.1 Legacy deployment model

The current/historical VPS deployment is hybrid:

```text
Backend: Docker Compose
Frontend: Node.js / pnpm
Database: Docker Postgres
Redis: Docker Redis
Proxy: Docker Traefik
```

Canonical routing in that deployment:

```text
https://konnaxion.com/       -> Next.js frontend on port 3000
https://konnaxion.com/api/   -> Django
https://konnaxion.com/admin/ -> Django admin
https://konnaxion.com/media/ -> Docker nginx media service
```

This layout is documented in the Namecheap VPS guide. 

---

## 7.2 Target capsule runtime

For the capsule architecture, developers should target a fully containerized runtime:

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
```

Public routing remains:

```text
/        -> frontend-next
/api/    -> django-api
/admin/  -> django-api
/media/  -> media-nginx
```

Internal-only services:

```text
postgres
redis
celeryworker
celerybeat
flower unless protected
```

---

## 7.3 Dangerous ports

Developers must not create code, docs, compose files, or examples that publicly expose:

```text
3000  Next.js direct
5000  Django/Gunicorn internal
5432  PostgreSQL
6379  Redis
5555  Flower/dashboard
8000  Django dev server
Docker daemon TCP ports
```

The security recovery notes explicitly state that public users should reach only Traefik on `80/443`, not the frontend direct port, dashboard/admin ports, Postgres, Redis, or Django/Gunicorn. 

---

## 8. Konnaxion Capsule development

## 8.1 Capsule principle

A Konnaxion Capsule is the portable, signed application package.

Canonical extension:

```text
.kxcap
```

Canonical build output example:

```text
konnaxion-v14-demo-2026.04.30.kxcap
```

The capsule contains:

```text
manifest.yaml
docker-compose.capsule.yml
images/
profiles/
env-templates/
migrations/
seed-data/
healthchecks/
checksums.txt
signature.sig
```

The capsule must not contain:

```text
real .env files
DJANGO_SECRET_KEY
POSTGRES_PASSWORD
DATABASE_URL with password
SSH private keys
API tokens
provider credentials
Django admin passwords
production database dumps in cleartext
```

---

## 8.2 Capsule Builder workflow

Canonical CLI:

```text
kx
```

Build sequence:

```text
1. Validate working tree.
2. Run backend tests.
3. Run backend migrations check.
4. Run frontend typecheck.
5. Run frontend production build.
6. Build Docker images.
7. Export images as OCI archives.
8. Generate manifest.yaml.
9. Generate checksums.
10. Sign capsule.
11. Output .kxcap.
```

Canonical command:

```bash
kx capsule build --profile demo --output konnaxion-v14-demo-2026.04.30.kxcap
```

---

## 8.3 Capsule compatibility

Every capsule must declare:

```yaml
app_version: v14
capsule_version: 2026.04.30-demo.1
param_version: kx-param-2026.04.30
required_ram_mb: 4096
recommended_ram_mb: 8192
```

Every capsule must declare compatible network profiles:

```yaml
profiles:
  - local_only
  - intranet_private
  - private_tunnel
  - public_temporary
  - public_vps
  - offline
```

---

## 9. Konnaxion Agent development

Agent development must follow:

```text
DOC-05_Konnaxion_Agent_Security_Model.md
```

Agent rules:

```text
local-only API
no arbitrary shell execution
no arbitrary Docker execution
signed capsules only
allowed images only
allowed services only
blocked dangerous ports
no privileged containers
no host network
no Docker socket mounts
Security Gate before runtime
audit log for privileged operations
```

The Agent exists because previous deployment compromise involved malicious Docker containers, cron persistence, `/tmp/sshd`, a miner, and a sudo backdoor attempt; therefore deployment automation must be allowlist-driven and fail closed. 

---

## 10. Security rules for developers

## 10.1 Never commit secrets

Never commit or paste:

```text
DATABASE_URL
POSTGRES_PASSWORD
DJANGO_SECRET_KEY
API keys
tokens
private keys
SSH keys
provider credentials
Django admin passwords
```

If a secret appears in logs, docs, commits, screenshots, or chat, rotate it.

The VPS guide explicitly warns not to paste full `.env` files or logs containing database URLs, Postgres passwords, Django secret keys, API keys, tokens, or private keys. 

---

## 10.2 Never trust compromised artifacts

Developers must not reuse:

```text
old disk images
old Docker volumes
old crontabs
old authorized_keys
old sudoers files
old /tmp contents
old /dev/shm contents
unknown systemd services
unknown Docker images
```

Backups should include only:

```text
Postgres dump
media/uploads
configuration templates
```

The security recovery notes say backups must not preserve malware and should not restore whole old disks, `/tmp`, `/dev/shm`, old crontabs, unknown systemd services, old authorized keys, old sudoers files, or unverified Docker volumes. 

---

## 10.3 Local malware indicators

When investigating suspicious systems, look for:

```text
amco_*
negoroo/amco
supportxmr
rx/0
/tmp/sshd
pakchoi
/dev/shm executable files
unexpected crontabs
unexpected sudoers files
```

These match the previous compromise indicators and should be included in Security Gate checks and incident procedures. 

---

## 11. Testing expectations

## 11.1 Backend tests

Run backend tests from `backend/` using the existing project tooling.

Typical patterns:

```powershell
cd C:\mycode\Konnaxion\Konnaxion\backend
docker-compose -f docker-compose.local.yml run --rm django pytest
```

Before merging backend model changes:

```text
makemigrations succeeds
migrate succeeds
tests pass
API routes work
admin still loads
Celery tasks still import
```

---

## 11.2 Frontend tests and validation

Before merging frontend changes:

```powershell
cd C:\mycode\Konnaxion\Konnaxion\frontend
pnpm install --frozen-lockfile
pnpm exec tsc --noEmit --pretty false
$env:NODE_OPTIONS="--max-old-space-size=4096"
pnpm build
```

Required checks:

```text
typecheck passes
production build passes
reports routes still build
module routes still render
services use correct /api/... paths
no direct browser calls to internal ports
```

---

## 11.3 Capsule validation

Before publishing a capsule:

```bash
kx capsule verify konnaxion-v14-demo-2026.04.30.kxcap
kx security check --capsule konnaxion-v14-demo-2026.04.30.kxcap
```

Required result:

```text
capsule_signature: PASS
image_checksums: PASS
manifest_schema: PASS
secrets_embedded: PASS
dangerous_ports_blocked: PASS
allowed_images_only: PASS
no_privileged_containers: PASS
no_host_network: PASS
docker_socket_not_mounted: PASS
```

---

## 12. Documentation update rules

When a developer changes code, they must update the correct documentation.

Use the technical reference map:

```text
Need setting / env / route invariant:
  Global Parameter Reference

Need module architecture:
  Full-Stack Technical Specification

Need Reports / Insights frontend behavior:
  Insights Module UI Spec

Need Reports / Insights config:
  Insights Module Config Parameters

Need route ownership:
  Site Navigation Map

Need table/model ownership:
  Database Schema Reference

Need functional code-name mapping:
  Functional Code-Name Inventory
```

The documentation index states that these files are the sources of truth for architecture, routes, environment/configuration invariants, module specs, database tables, and functional code-name mapping. 

---

## 13. Branching and commit rules

Recommended branch naming:

```text
feature/<short-name>
fix/<short-name>
docs/<short-name>
security/<short-name>
infra/<short-name>
capsule/<short-name>
```

Commit message examples:

```text
feat(frontend): add Reports usage chart shell
fix(backend): correct Ethikos stance validation
docs(capsule): add network profile reference
security(agent): block Docker socket mounts
infra(runtime): add media-nginx healthcheck
```

Before commit:

```bash
git status
```

Do not commit:

```text
.env
.env.production with secrets
database dumps
media backups
node_modules
.next
__pycache__
deployment archives
*.tar.gz
*.zip
private keys
logs containing secrets
```

The deployment guide warns not to commit deployment archives such as `.tar.gz` or `.zip`, and recommends generating clean archives from Git when deploying. 

---

## 14. Pull request checklist

Every PR must answer:

```text
What module changed?
Did backend models change?
Were migrations generated?
Did API routes change?
Did frontend routes change?
Did environment variables change?
Did Docker/runtime behavior change?
Did any public exposure change?
Did docs need updating?
Did tests/build pass?
Are secrets absent?
```

Minimum PR checklist:

```text
[ ] Backend tests pass, if backend changed.
[ ] Migrations are included, if models changed.
[ ] Frontend typecheck passes, if frontend changed.
[ ] Frontend production build passes, if frontend changed.
[ ] Capsule manifest updated, if runtime changed.
[ ] Security Gate rules updated, if exposure changed.
[ ] Docs updated.
[ ] No secrets committed.
[ ] No dangerous ports exposed.
```

---

## 15. Release development workflow

## 15.1 Legacy safe archive flow

For non-capsule deployments, create clean archive from Git:

```powershell
cd C:\mycode\Konnaxion\Konnaxion
git status
git archive --format=tar.gz -o konnaxion-deploy.tar.gz HEAD
```

The Namecheap guide recommends clean Git archives when the VPS folder is not guaranteed to be a Git repository. 

## 15.2 Target capsule release flow

For capsule releases:

```bash
kx capsule build --profile demo --output konnaxion-v14-demo-2026.04.30.kxcap
kx capsule verify konnaxion-v14-demo-2026.04.30.kxcap
kx security check --capsule konnaxion-v14-demo-2026.04.30.kxcap
```

Then import on a Konnaxion Box:

```bash
kx capsule import konnaxion-v14-demo-2026.04.30.kxcap
kx instance create demo-001 --capsule konnaxion-v14-demo-2026.04.30
kx instance start demo-001 --network intranet_private
```

---

## 16. Environment variables

## 16.1 Backend production variables

Canonical backend variables include:

```env
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_SECRET_KEY=<GENERATED_ON_INSTALL>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=<GENERATED_FROM_PROFILE>
USE_DOCKER=yes
DATABASE_URL=postgres://konnaxion:<POSTGRES_PASSWORD>@postgres:5432/konnaxion
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
DJANGO_ADMIN_URL=admin/
SENTRY_DSN=
```

## 16.2 Database variables

```env
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=konnaxion
POSTGRES_USER=konnaxion
POSTGRES_PASSWORD=<GENERATED_ON_INSTALL>
```

## 16.3 Frontend variables

```env
NEXT_PUBLIC_API_BASE=https://<HOST>/api
NEXT_PUBLIC_BACKEND_BASE=https://<HOST>
NEXT_TELEMETRY_DISABLED=1
NODE_OPTIONS=--max-old-space-size=4096
```

## 16.4 Capsule/Manager variables

```env
KX_INSTANCE_ID=demo-001
KX_CAPSULE_ID=konnaxion-v14-demo-2026.04.30
KX_APP_VERSION=v14
KX_PARAM_VERSION=kx-param-2026.04.30
KX_NETWORK_PROFILE=intranet_private
KX_EXPOSURE_MODE=private
KX_PUBLIC_MODE_ENABLED=false
KX_REQUIRE_SIGNED_CAPSULE=true
KX_ALLOW_UNKNOWN_IMAGES=false
KX_ALLOW_PRIVILEGED_CONTAINERS=false
KX_ALLOW_DOCKER_SOCKET_MOUNT=false
KX_ALLOW_HOST_NETWORK=false
```

---

## 17. Common developer mistakes

## 17.1 Running frontend build from the wrong folder

Wrong:

```powershell
cd C:\mycode\Konnaxion\Konnaxion
pnpm build
```

Correct:

```powershell
cd C:\mycode\Konnaxion\Konnaxion\frontend
pnpm build
```

## 17.2 Forgetting memory option

Wrong:

```powershell
pnpm build
```

Correct for production build validation:

```powershell
$env:NODE_OPTIONS="--max-old-space-size=4096"
pnpm build
```

## 17.3 Exposing app internals

Wrong:

```text
http://server-ip:3000
http://server-ip:5555
http://server-ip:5432
http://server-ip:6379
```

Correct:

```text
https://<host>/
https://<host>/api/
https://<host>/admin/
https://<host>/media/
```

## 17.4 Reusing compromised deployment state

Wrong:

```text
clone old disk
reuse old authorized_keys
reuse old .env
reuse old Docker volumes
reuse old crontabs
```

Correct:

```text
clean source
verified DB dump
required media only
new secrets
new SSH keys
fresh runtime
Security Gate
```

---

## 18. Developer acceptance criteria

A development change is acceptable when:

```text
It preserves the canonical stack.
It respects module ownership.
It uses existing frontend layout and services patterns.
It uses canonical backend settings and apps.
It passes backend tests when backend changed.
It passes frontend typecheck/build when frontend changed.
It does not expose dangerous ports.
It does not include secrets.
It updates docs when contracts changed.
It remains compatible with Konnaxion Capsule packaging.
It does not weaken Security Gate or Agent policies.
```

---

## 19. Final rule

Konnaxion development must optimize for:

```text
clean architecture
module boundaries
repeatable builds
capsule packaging
private-by-default runtime
minimal configuration for operators
strong security defaults
```

Developers may add capability, but must not add ambiguity.

If a change makes Konnaxion harder to package, harder to secure, harder to run offline/intranet, or easier to misconfigure publicly, it must be redesigned before merge.

