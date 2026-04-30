# DOC-08 — Konnaxion Runtime Docker Compose

```yaml
doc_id: DOC-08
filename: DOC-08_Konnaxion_Runtime_Docker_Compose.md
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: draft
depends_on:
  - DOC-00_Konnaxion_Canonical_Variables.md
  - DOC-03_Konnaxion_Capsule_Format.md
  - DOC-04_Konnaxion_Manager_Architecture.md
  - DOC-05_Konnaxion_Agent_Security_Model.md
  - DOC-06_Konnaxion_Network_Profiles.md
  - DOC-07_Konnaxion_Security_Gate.md
````

## 1. Purpose

This document defines the canonical **Docker Compose runtime** for a `Konnaxion Instance`.

It describes:

```text
- canonical Docker services
- container names
- networks
- volumes
- ports
- healthchecks
- runtime environment variables
- startup order
- security constraints
- compose profiles
- operational commands
```

This document does **not** define the capsule format itself. The capsule format is defined in `DOC-03_Konnaxion_Capsule_Format.md`.

This document does **not** define the graphical manager. The manager is defined in `DOC-04_Konnaxion_Manager_Architecture.md`.

---

## 2. Runtime decision

The target runtime for a Konnaxion Instance is:

```text
Docker Compose
```

Konnaxion v14 already uses a Docker-compatible production stack around Django, PostgreSQL, Redis, Celery, Traefik, Flower, and Nginx/media, while the current legacy VPS keeps the frontend as a separate Node/pnpm service on port `3000`.  

For the new capsule/appliance model, the target runtime must containerize the frontend too.

Canonical target:

```text
Traefik
  ├── frontend-next
  ├── django-api
  └── media-nginx

Internal services
  ├── postgres
  ├── redis
  ├── celeryworker
  ├── celerybeat
  └── flower, optional/private only
```

Kubernetes is explicitly out of scope for the plug-and-play runtime. The codebase already has Docker, Redis, Celery, Traefik, and Sentry-related infrastructure, and project guidance says not to introduce new infrastructure layers casually. 

---

## 3. Runtime goals

The Docker Compose runtime must satisfy these goals:

```text
1. Start Konnaxion with one controlled command.
2. Keep all internal services off the public network.
3. Expose only Traefik.
4. Support local, intranet, tunnel, and VPS profiles.
5. Generate secrets at install time, not capsule build time.
6. Preserve instance data outside the capsule.
7. Support backup, restore, update, and rollback.
8. Be readable and debuggable by an operator.
9. Be enforceable by Konnaxion Agent.
```

---

## 4. Canonical service names

All Compose files must use these service names.

| Service              | Canonical name  | Required |             Public port allowed |
| -------------------- | --------------- | -------: | ------------------------------: |
| Reverse proxy        | `traefik`       |      yes | yes, `80/443` depending profile |
| Frontend             | `frontend-next` |      yes |                              no |
| Backend API          | `django-api`    |      yes |                              no |
| Database             | `postgres`      |      yes |                              no |
| Redis broker         | `redis`         |      yes |                              no |
| Celery worker        | `celeryworker`  |      yes |                              no |
| Celery beat          | `celerybeat`    |      yes |                              no |
| Media/static service | `media-nginx`   |      yes |                              no |
| Celery dashboard     | `flower`        | optional |                              no |
| Runtime init job     | `kx-init`       | optional |                              no |
| Migration job        | `kx-migrate`    | optional |                              no |

Do not use alternate names such as:

```text
backend
api
web
next
frontend
db
cache
worker
beat
nginx
```

unless they are aliases inside comments only.

---

## 5. Canonical routing

Traefik is the only HTTP entrypoint.

```text
https://<KX_HOST>/          -> frontend-next
https://<KX_HOST>/api/      -> django-api
https://<KX_HOST>/admin/    -> django-api
https://<KX_HOST>/media/    -> media-nginx
```

This preserves the routing already validated in the legacy deployment: `/` routes to Next.js, `/api/` and `/admin/` route to Django, and `/media/` routes to the media service. 

---

## 6. Canonical ports

### 6.1 Allowed published ports

|            Port | Service   | Profiles                                                               |
| --------------: | --------- | ---------------------------------------------------------------------- |
|           `443` | `traefik` | `intranet_private`, `private_tunnel`, `public_temporary`, `public_vps` |
|            `80` | `traefik` | optional redirect, mostly `public_vps`                                 |
| `127.0.0.1:443` | `traefik` | `local_only`                                                           |
|  `127.0.0.1:80` | `traefik` | optional local redirect                                                |

### 6.2 Forbidden published ports

The following ports must never be published directly:

|       Port | Service                 | Rule                       |
| ---------: | ----------------------- | -------------------------- |
|     `3000` | `frontend-next`         | internal only              |
|     `5000` | `django-api` / Gunicorn | internal only              |
|     `5555` | `flower`                | private only, never public |
|     `5432` | `postgres`              | internal only              |
|     `6379` | `redis`                 | internal only              |
|     `8000` | Django dev server       | forbidden in runtime       |
| Docker TCP | Docker daemon           | forbidden                  |

The previous security review explicitly warns not to expose `3000`, `5555`, `5432`, `6379`, `8000`, or Docker daemon ports, and recommends validating the app only through `80/443`.  

---

## 7. Network model

The runtime uses two Docker networks.

```text
kx_edge
  - Traefik only
  - Receives published ports from host

kx_app
  - Internal app network
  - frontend-next
  - django-api
  - media-nginx
  - postgres
  - redis
  - celeryworker
  - celerybeat
  - flower
```

Traefik attaches to both networks.

```text
Host/LAN/Internet
  ↓
traefik on kx_edge
  ↓
frontend-next / django-api / media-nginx on kx_app
  ↓
postgres / redis internal services on kx_app
```

No container except `traefik` may publish ports.

---

## 8. Volume model

Instance data must live outside the capsule.

Canonical volume mapping:

| Volume                | Purpose           |        Persistent |
| --------------------- | ----------------- | ----------------: |
| `kx_postgres_data`    | PostgreSQL data   |               yes |
| `kx_postgres_backups` | PostgreSQL dumps  |               yes |
| `kx_redis_data`       | Redis persistence |               yes |
| `kx_django_media`     | Uploaded media    |               yes |
| `kx_traefik_acme`     | TLS certificates  | profile-dependent |
| `kx_logs`             | Runtime logs      |               yes |
| `kx_state`            | Instance state    |               yes |

The current production stack already uses persistent volumes for PostgreSQL data/backups, Django media, Traefik ACME state, and Redis data. 

---

## 9. Environment file model

Runtime env files live in the instance directory, not inside the capsule.

Canonical location:

```text
/opt/konnaxion/instances/<INSTANCE_ID>/env/
├── django.env
├── postgres.env
├── redis.env
├── frontend.env
├── traefik.env
└── kx-runtime.env
```

The capsule may contain templates, but never real secrets.

The legacy deployment requires `.django`, `.postgres`, and `.env.production` files, and has already shown pitfalls such as missing env files, `$` inside `DJANGO_SECRET_KEY`, and production frontend env values being baked into the Next.js build. 

---

## 10. Required runtime variables

### 10.1 `kx-runtime.env`

```env
KX_INSTANCE_ID=demo-001
KX_CAPSULE_ID=konnaxion-v14-demo-2026.04.30
KX_CAPSULE_VERSION=2026.04.30-demo.1
KX_APP_VERSION=v14
KX_NETWORK_PROFILE=intranet_private
KX_EXPOSURE_MODE=private
KX_PUBLIC_MODE_ENABLED=false
KX_PUBLIC_MODE_EXPIRES_AT=
```

### 10.2 `django.env`

```env
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_SECRET_KEY=<GENERATED_ON_INSTALL>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=<GENERATED_FROM_NETWORK_PROFILE>

USE_DOCKER=yes

DATABASE_URL=postgres://konnaxion:<POSTGRES_PASSWORD>@postgres:5432/konnaxion
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0

DJANGO_ADMIN_URL=admin/
SENTRY_DSN=
```

### 10.3 `postgres.env`

```env
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=konnaxion
POSTGRES_USER=konnaxion
POSTGRES_PASSWORD=<GENERATED_ON_INSTALL>
```

### 10.4 `frontend.env`

```env
NODE_ENV=production
NEXT_TELEMETRY_DISABLED=1
NEXT_PUBLIC_API_BASE=https://<KX_HOST>/api
NEXT_PUBLIC_BACKEND_BASE=https://<KX_HOST>
```

For build-time frontend generation, the builder must use:

```env
NODE_OPTIONS=--max-old-space-size=4096
```

The frontend deployment runbook says `NODE_OPTIONS="--max-old-space-size=4096"` was needed to avoid Next.js heap out-of-memory failures on limited-RAM VPS builds. 

---

## 11. Canonical Compose file

File name:

```text
docker-compose.capsule.yml
```

Canonical location inside capsule:

```text
/.kxcap/docker-compose.capsule.yml
```

Canonical rendered location after import:

```text
/opt/konnaxion/instances/<INSTANCE_ID>/runtime/docker-compose.yml
```

Reference Compose:

```yaml
name: konnaxion-${KX_INSTANCE_ID}

services:
  traefik:
    image: ${KX_IMAGE_TRAEFIK}
    container_name: kx-${KX_INSTANCE_ID}-traefik
    restart: unless-stopped
    depends_on:
      django-api:
        condition: service_healthy
      frontend-next:
        condition: service_healthy
      media-nginx:
        condition: service_started
    env_file:
      - ../env/kx-runtime.env
      - ../env/traefik.env
    ports:
      - "${KX_BIND_HTTP:-127.0.0.1:80}:80"
      - "${KX_BIND_HTTPS:-127.0.0.1:443}:443"
    volumes:
      - kx_traefik_acme:/etc/traefik/acme
      - ./traefik/traefik.yml:/etc/traefik/traefik.yml:ro
    networks:
      - kx_edge
      - kx_app
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp
    healthcheck:
      test: ["CMD", "traefik", "healthcheck", "--ping"]
      interval: 30s
      timeout: 5s
      retries: 5

  frontend-next:
    image: ${KX_IMAGE_FRONTEND}
    container_name: kx-${KX_INSTANCE_ID}-frontend-next
    restart: unless-stopped
    env_file:
      - ../env/kx-runtime.env
      - ../env/frontend.env
    expose:
      - "3000"
    networks:
      - kx_app
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp
      - /app/.next/cache
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:3000/ >/dev/null || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 10

  django-api:
    image: ${KX_IMAGE_BACKEND}
    container_name: kx-${KX_INSTANCE_ID}-django-api
    restart: unless-stopped
    command: /start
    env_file:
      - ../env/kx-runtime.env
      - ../env/django.env
      - ../env/postgres.env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    expose:
      - "5000"
    volumes:
      - kx_django_media:/app/konnaxion/media
      - kx_logs:/app/logs
    networks:
      - kx_app
    security_opt:
      - no-new-privileges:true
    healthcheck:
      test: ["CMD-SHELL", "python manage.py check --deploy >/dev/null 2>&1 || exit 1"]
      interval: 60s
      timeout: 15s
      retries: 5

  media-nginx:
    image: ${KX_IMAGE_MEDIA_NGINX}
    container_name: kx-${KX_INSTANCE_ID}-media-nginx
    restart: unless-stopped
    depends_on:
      - django-api
    expose:
      - "80"
    volumes:
      - kx_django_media:/usr/share/nginx/media:ro
    networks:
      - kx_app
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /var/cache/nginx
      - /var/run
      - /tmp

  postgres:
    image: ${KX_IMAGE_POSTGRES:-postgres:16}
    container_name: kx-${KX_INSTANCE_ID}-postgres
    restart: unless-stopped
    env_file:
      - ../env/postgres.env
    volumes:
      - kx_postgres_data:/var/lib/postgresql/data
      - kx_postgres_backups:/backups
    expose:
      - "5432"
    networks:
      - kx_app
    security_opt:
      - no-new-privileges:true
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 30s
      timeout: 5s
      retries: 10

  redis:
    image: ${KX_IMAGE_REDIS:-redis:7-alpine}
    container_name: kx-${KX_INSTANCE_ID}-redis
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - kx_redis_data:/data
    expose:
      - "6379"
    networks:
      - kx_app
    security_opt:
      - no-new-privileges:true
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 5s
      retries: 10

  celeryworker:
    image: ${KX_IMAGE_BACKEND}
    container_name: kx-${KX_INSTANCE_ID}-celeryworker
    restart: unless-stopped
    command: /start-celeryworker
    env_file:
      - ../env/kx-runtime.env
      - ../env/django.env
      - ../env/postgres.env
    depends_on:
      django-api:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - kx_django_media:/app/konnaxion/media
      - kx_logs:/app/logs
    networks:
      - kx_app
    security_opt:
      - no-new-privileges:true

  celerybeat:
    image: ${KX_IMAGE_BACKEND}
    container_name: kx-${KX_INSTANCE_ID}-celerybeat
    restart: unless-stopped
    command: /start-celerybeat
    env_file:
      - ../env/kx-runtime.env
      - ../env/django.env
      - ../env/postgres.env
    depends_on:
      django-api:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - kx_logs:/app/logs
    networks:
      - kx_app
    security_opt:
      - no-new-privileges:true

  flower:
    image: ${KX_IMAGE_BACKEND}
    container_name: kx-${KX_INSTANCE_ID}-flower
    restart: unless-stopped
    command: /start-flower
    profiles:
      - observability
    env_file:
      - ../env/kx-runtime.env
      - ../env/django.env
      - ../env/postgres.env
    depends_on:
      redis:
        condition: service_healthy
    expose:
      - "5555"
    networks:
      - kx_app
    security_opt:
      - no-new-privileges:true

  kx-migrate:
    image: ${KX_IMAGE_BACKEND}
    container_name: kx-${KX_INSTANCE_ID}-kx-migrate
    profiles:
      - jobs
    command: python manage.py migrate
    env_file:
      - ../env/kx-runtime.env
      - ../env/django.env
      - ../env/postgres.env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - kx_app
    security_opt:
      - no-new-privileges:true

volumes:
  kx_postgres_data:
  kx_postgres_backups:
  kx_redis_data:
  kx_django_media:
  kx_traefik_acme:
  kx_logs:
  kx_state:

networks:
  kx_edge:
    name: kx-${KX_INSTANCE_ID}-edge
  kx_app:
    name: kx-${KX_INSTANCE_ID}-app
```

---

## 12. Traefik runtime file

File name:

```text
traefik.yml
```

Rendered location:

```text
/opt/konnaxion/instances/<INSTANCE_ID>/runtime/traefik/traefik.yml
```

Reference:

```yaml
log:
  level: INFO

api:
  dashboard: false

ping: {}

entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entryPoint:
          to: web-secure
          scheme: https

  web-secure:
    address: ":443"

http:
  routers:
    frontend-router:
      rule: "HostRegexp(`{host:.+}`) && PathPrefix(`/`)"
      entryPoints:
        - web-secure
      service: frontend-next
      priority: 1

    api-router:
      rule: "HostRegexp(`{host:.+}`) && (PathPrefix(`/api/`) || PathPrefix(`/admin/`))"
      entryPoints:
        - web-secure
      service: django-api
      priority: 100
      middlewares:
        - csrf

    media-router:
      rule: "HostRegexp(`{host:.+}`) && PathPrefix(`/media/`)"
      entryPoints:
        - web-secure
      service: media-nginx
      priority: 100

  middlewares:
    csrf:
      headers:
        hostsProxyHeaders:
          - X-CSRFToken

  services:
    frontend-next:
      loadBalancer:
        servers:
          - url: "http://frontend-next:3000"

    django-api:
      loadBalancer:
        servers:
          - url: "http://django-api:5000"

    media-nginx:
      loadBalancer:
        servers:
          - url: "http://media-nginx:80"

providers:
  file:
    filename: /etc/traefik/traefik.yml
    watch: true
```

For `public_vps`, the rendered Traefik file may add Let’s Encrypt.

For `.local` or intranet hostnames, do not configure Let’s Encrypt. The legacy deployment already failed when `.local` was included in Let’s Encrypt routing, because public ACME certificates cannot be issued for `.local`. 

---

## 13. Network profile bindings

The Manager must render `KX_BIND_HTTP` and `KX_BIND_HTTPS` based on `KX_NETWORK_PROFILE`.

### 13.1 `local_only`

```env
KX_NETWORK_PROFILE=local_only
KX_BIND_HTTP=127.0.0.1:80
KX_BIND_HTTPS=127.0.0.1:443
```

### 13.2 `intranet_private`

```env
KX_NETWORK_PROFILE=intranet_private
KX_BIND_HTTP=0.0.0.0:80
KX_BIND_HTTPS=0.0.0.0:443
KX_EXPOSURE_MODE=lan
```

Firewall must restrict exposure to LAN/private ranges.

### 13.3 `private_tunnel`

```env
KX_NETWORK_PROFILE=private_tunnel
KX_BIND_HTTP=127.0.0.1:80
KX_BIND_HTTPS=127.0.0.1:443
KX_EXPOSURE_MODE=vpn
```

The tunnel agent exposes the service; Docker does not publish public ports.

### 13.4 `public_temporary`

```env
KX_NETWORK_PROFILE=public_temporary
KX_BIND_HTTP=127.0.0.1:80
KX_BIND_HTTPS=127.0.0.1:443
KX_EXPOSURE_MODE=temporary_tunnel
KX_PUBLIC_MODE_ENABLED=true
KX_PUBLIC_MODE_EXPIRES_AT=<REQUIRED>
```

Expiration is mandatory.

### 13.5 `public_vps`

```env
KX_NETWORK_PROFILE=public_vps
KX_BIND_HTTP=0.0.0.0:80
KX_BIND_HTTPS=0.0.0.0:443
KX_EXPOSURE_MODE=public
```

Firewall must allow only:

```text
80/tcp
443/tcp
22/tcp from admin IP or VPN only
```

---

## 14. Startup sequence

Konnaxion Agent must start services in this order:

```text
1. Verify capsule signature.
2. Render runtime env files.
3. Render docker-compose.yml.
4. Render traefik.yml.
5. Run Security Gate.
6. Start postgres and redis.
7. Run migrations.
8. Start django-api.
9. Start frontend-next.
10. Start media-nginx.
11. Start celeryworker and celerybeat.
12. Start traefik.
13. Run healthchecks.
14. Mark instance as running.
```

Equivalent CLI flow:

```bash
kx capsule verify konnaxion-v14-demo-2026.04.30.kxcap
kx instance create demo-001 --capsule konnaxion-v14-demo-2026.04.30.kxcap
kx security check demo-001
kx instance start demo-001 --network intranet_private
kx instance status demo-001
```

---

## 15. Migration flow

Migrations must run as a one-off job.

```bash
docker compose --profile jobs run --rm kx-migrate
```

Equivalent manager command:

```bash
kx instance migrate demo-001
```

Django model changes require migrations before the schema is considered valid. The existing backend workflow already requires `makemigrations`, `migrate`, and service verification through Docker Compose. 

---

## 16. Backup flow

The runtime must support PostgreSQL backups through the `postgres` service.

Canonical command:

```bash
docker compose exec -T postgres \
  pg_dump -U konnaxion -d konnaxion \
  > ../backups/postgres/konnaxion_${KX_INSTANCE_ID}_$(date +%Y%m%d_%H%M%S).sql
```

Equivalent manager command:

```bash
kx instance backup demo-001
```

Backups must include:

```text
PostgreSQL dump
media volume
runtime manifest
capsule reference
safe env metadata without secrets
```

Backups must not include:

```text
old full disk image
/tmp
/dev/shm
unknown crontabs
unknown systemd units
unknown Docker volumes
old authorized_keys
old sudoers fragments
```

Incident recovery notes specifically warn against restoring full compromised disks, `/tmp`, `/dev/shm`, crontabs, old authorized keys, old sudoers files, unknown systemd services, or unverified Docker volumes. 

---

## 17. Update and rollback flow

Each update uses a new immutable capsule.

```text
current capsule:  konnaxion-v14-demo-2026.04.30.kxcap
next capsule:     konnaxion-v14-demo-2026.05.07.kxcap
```

Update sequence:

```text
1. Verify new capsule.
2. Backup current instance.
3. Stop frontend-next, celeryworker, celerybeat.
4. Pull/load new images.
5. Run migrations.
6. Start new services.
7. Run healthchecks.
8. If healthy, mark new capsule current.
9. If unhealthy, rollback to previous capsule.
```

Rollback command:

```bash
kx instance rollback demo-001
```

---

## 18. Security requirements

The runtime must enforce:

```text
- no privileged containers
- no host network mode
- no Docker socket mount
- no unknown images
- no public database
- no public Redis
- no public frontend direct port
- no public Django direct port
- no public Flower dashboard
- no secrets in image layers
- no secrets inside .kxcap
```

The previous incident involved malicious Docker containers, cron persistence, `/tmp/sshd`, and attempted sudo backdoor creation; therefore the runtime must treat Docker permissions and container image allowlisting as security-critical.  

---

## 19. Security Gate checks

Before `docker compose up`, Konnaxion Agent must run:

```text
capsule_signature
image_checksums
manifest_schema
compose_schema
forbidden_ports_not_published
docker_socket_not_mounted
no_privileged_containers
no_host_network
postgres_not_public
redis_not_public
frontend_not_public
django_not_public
flower_not_public
allowed_images_only
env_files_permissions
secrets_not_default
network_profile_valid
public_mode_expiration_valid
```

Blocking failures:

```text
FAIL_BLOCKING if port 3000 is published
FAIL_BLOCKING if port 5432 is published
FAIL_BLOCKING if port 6379 is published
FAIL_BLOCKING if Docker socket is mounted
FAIL_BLOCKING if privileged: true exists
FAIL_BLOCKING if network_mode: host exists
FAIL_BLOCKING if public mode has no expiration
FAIL_BLOCKING if capsule signature is invalid
FAIL_BLOCKING if image checksum mismatch
```

---

## 20. Compose validation command

Konnaxion Agent must validate the rendered Compose file before starting.

```bash
docker compose -f docker-compose.yml config
```

Then inspect published ports:

```bash
docker compose -f docker-compose.yml config | grep -n "published\|target\|ports" || true
```

The final validation must prove that only Traefik publishes ports.

---

## 21. Healthcheck matrix

| Service         | Healthcheck                                  |
| --------------- | -------------------------------------------- |
| `traefik`       | Traefik ping                                 |
| `frontend-next` | HTTP GET `/` on port `3000` inside container |
| `django-api`    | `python manage.py check --deploy`            |
| `postgres`      | `pg_isready`                                 |
| `redis`         | `redis-cli ping`                             |
| `media-nginx`   | HTTP GET `/media/` or container running      |
| `celeryworker`  | Celery inspect ping, optional                |
| `celerybeat`    | process running                              |
| `flower`        | private HTTP health, optional                |

External healthcheck must use only:

```text
https://<KX_HOST>/
https://<KX_HOST>/api/
https://<KX_HOST>/admin/
https://<KX_HOST>/media/
```

Never:

```text
http://<HOST>:3000
http://<HOST>:5000
http://<HOST>:5555
http://<HOST>:5432
http://<HOST>:6379
```

---

## 22. Observability

Minimum commands:

```bash
docker compose ps
docker compose logs --tail=100 traefik
docker compose logs --tail=100 django-api
docker compose logs --tail=100 frontend-next
docker compose logs --tail=100 celeryworker
docker compose logs --tail=100 postgres
docker compose logs --tail=100 redis
```

Canonical manager commands:

```bash
kx instance status demo-001
kx instance logs demo-001 --service traefik
kx instance logs demo-001 --service django-api
kx instance logs demo-001 --service frontend-next
kx security check demo-001
```

---

## 23. Host-level runtime requirements

Minimum host:

```text
Linux host
Docker Engine
Docker Compose v2
4 GB RAM minimum
8 GB RAM recommended
SSD storage
Firewall available
```

For capsule/appliance deployment, recommended:

```text
Ubuntu Server LTS or Debian minimal
Docker from official repository
Konnaxion Agent installed as system service
Konnaxion Manager local UI
UFW or equivalent firewall
Tailscale or tunnel agent optional
```

---

## 24. Forbidden runtime patterns

Do not use:

```text
frontend on host systemd as target architecture
public port 3000
public port 5555
public PostgreSQL
public Redis
Docker socket mounted into app containers
deployment user in docker group by default
unverified images
unknown containers
host network mode
privileged containers
manual edits inside running containers
```

The current validated VPS runbook uses a systemd frontend on port `3000`; this remains a legacy deployment detail, not the capsule runtime target. 

---

## 25. Compatibility with legacy deployment

Legacy production shape:

```text
Backend: Docker Compose
Frontend: Node.js / pnpm
Database: Docker Postgres
Redis: Docker Redis
Proxy: Docker Traefik
```

Target capsule runtime:

```text
Frontend: Docker container
Backend: Docker container
Database: Docker Postgres
Redis: Docker Redis
Proxy: Docker Traefik
Media: Docker Nginx
Workers: Docker Celery
```

Migration from legacy to capsule requires:

```text
1. Build frontend image.
2. Add frontend-next service to docker-compose.capsule.yml.
3. Route Traefik to frontend-next:3000 instead of host.docker.internal:3000.
4. Remove public host exposure of port 3000.
5. Preserve /api/, /admin/, and /media/ routing.
```

---

## 26. Acceptance criteria

`DOC-08` is implemented correctly when:

```text
[PASS] docker compose config succeeds
[PASS] only traefik publishes ports
[PASS] postgres has no published port
[PASS] redis has no published port
[PASS] frontend-next has no published port
[PASS] django-api has no published port
[PASS] flower has no published port
[PASS] / routes to frontend-next
[PASS] /api/ routes to django-api
[PASS] /admin/ routes to django-api
[PASS] /media/ routes to media-nginx
[PASS] migrations run through kx-migrate
[PASS] backups can be created from postgres
[PASS] Security Gate blocks dangerous compose changes
[PASS] local_only profile binds to localhost
[PASS] intranet_private profile exposes only 80/443 to LAN
[PASS] public_temporary requires expiration
[PASS] public_vps exposes only 80/443 publicly
```

---

## 27. Out of scope

This document does not define:

```text
Konnaxion Capsule file signing
Konnaxion Manager UI screens
Konnaxion Agent privilege boundary
Threat model details
Backup retention policy
Full VPS hardening guide
Frontend application architecture
Backend model architecture
```

Those belong to:

```text
DOC-03_Konnaxion_Capsule_Format.md
DOC-04_Konnaxion_Manager_Architecture.md
DOC-05_Konnaxion_Agent_Security_Model.md
DOC-07_Konnaxion_Security_Gate.md
DOC-09_Konnaxion_Backup_Restore_Rollback.md
DOC-13_Konnaxion_Threat_Model.md
```

---

## 28. Final decision

The canonical Konnaxion runtime is:

```text
Docker Compose
Traefik as only entrypoint
Next.js frontend in container
Django/Gunicorn backend in container
PostgreSQL internal only
Redis internal only
Celery internal only
Nginx/media internal only
Flower optional and private only
Security Gate before start
Network profiles rendered by Konnaxion Agent
No public app internals
```

This replaces the legacy hybrid VPS model for future Konnaxion Capsule and Konnaxion Box deployments.


