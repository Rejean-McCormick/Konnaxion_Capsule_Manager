doc_id: DOC-06
title: Konnaxion Network Profiles
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: draft
depends_on:
  - DOC-00_Konnaxion_Canonical_Variables.md
  - DOC-04_Konnaxion_Manager_Architecture.md
  - DOC-05_Konnaxion_Agent_Security_Model.md
  - DOC-07_Konnaxion_Security_Gate.md
  - DOC-08_Konnaxion_Runtime_Docker_Compose.md
owner: Konnaxion Architecture
last_updated: 2026-05-05
default_network_profile: intranet_private
default_exposure_mode: private
```

# DOC-06 — Konnaxion Network Profiles

## 1. Purpose

This document defines the canonical network profiles used by the **Konnaxion Capsule Manager** and enforced by the **Konnaxion Agent**.

The goal is to make Konnaxion deployable as a plug-and-play capsule while keeping network exposure predictable, minimal, and secure.

Konnaxion must be **private-by-default**.

The user should not manually configure Docker ports, Traefik routers, Redis exposure, PostgreSQL exposure, Django binding, Next.js binding, firewall rules, or reverse proxy labels.

The user chooses a network profile. The Manager and Agent apply the correct network policy.

---

## 2. Grounding

Konnaxion v14 uses a **Next.js frontend**, **Django + DRF backend**, **PostgreSQL**, **Celery + Redis**, and Docker-oriented deployment infrastructure. The canonical runtime model is defined in `DOC-00_Konnaxion_Canonical_Variables.md` and `DOC-08_Konnaxion_Runtime_Docker_Compose.md`.

The canonical production topology includes Traefik as the only HTTP(S) entrypoint, with routing from `/` to `frontend-next`, `/api/` and `/admin/` to `django-api`, and `/media/` to `media-nginx`.

The security baseline is:

```text
Public users reach only Traefik on 80/443.
Internal services remain private on Docker networks.
Docker socket is not mounted.
Traefik routing uses file-provider dynamic configuration, not Docker socket labels.
```

Public users must not reach ports such as `3000`, `5000`, `5555`, `5432`, `6379`, `8000`, or Docker daemon ports.

For public VPS deployments, the selected public runtime hostname must be propagated consistently to:

```text
KX_HOST
KX_HOST_ALIASES
DJANGO_ALLOWED_HOSTS
DJANGO_CSRF_TRUSTED_ORIGINS
CSRF_TRUSTED_ORIGINS
CORS_ALLOWED_ORIGINS
NEXT_PUBLIC_API_BASE
NEXT_PUBLIC_BACKEND_BASE
Traefik Host(...) rules
```

A public domain that resolves to the VPS but returns Traefik’s plain `404 page not found` is a routing failure. It means the Traefik Host rule does not include the public domain.

---

## 3. Canonical Profiles

The only valid values for `KX_NETWORK_PROFILE` are:

```text
offline
local_only
intranet_private
private_tunnel
public_temporary
public_vps
```

Default:

```env
KX_NETWORK_PROFILE=intranet_private
KX_EXPOSURE_MODE=private
KX_PUBLIC_MODE_ENABLED=false
```

Public mode is never the default.

---

## 4. Canonical Exposure Modes

The only valid values for `KX_EXPOSURE_MODE` are:

```text
private
lan
vpn
temporary_tunnel
public
```

Profile-to-exposure mapping:

```text
offline           -> private
local_only        -> private
intranet_private  -> lan
private_tunnel    -> vpn
public_temporary  -> temporary_tunnel
public_vps        -> public
```

The Agent must reject invalid profile/exposure combinations.

---

## 5. Profile Summary Matrix

| Profile          | Variable           | Intended use             | Public internet | LAN      | VPN/Tunnel | Default |
| ---------------- | ------------------ | ------------------------ | --------------- | -------- | ---------- | ------- |
| Offline          | `offline`          | Fully isolated demo/test | no              | no       | no         | no      |
| Local only       | `local_only`       | Demo on same machine     | no              | no       | no         | no      |
| Intranet private | `intranet_private` | LAN/institution demo     | no              | yes      | no         | yes     |
| Private tunnel   | `private_tunnel`   | Trusted remote users     | no              | optional | yes        | no      |
| Public temporary | `public_temporary` | External demo link       | limited         | optional | tunnel     | no      |
| Public VPS       | `public_vps`       | Real public deployment   | yes             | n/a      | optional   | no      |

---

## 6. Shared Runtime Topology

All network profiles use the same internal service model.

```text
Client
  ↓
Traefik
  ├── /        -> frontend-next
  ├── /api/    -> django-api
  ├── /admin/  -> django-api
  └── /media/  -> media-nginx

Internal only:
  ├── postgres
  ├── redis
  ├── celeryworker
  ├── celerybeat
  └── flower
```

Only Traefik is allowed to be an external entrypoint.

Direct access to `frontend-next`, `django-api`, `postgres`, `redis`, `celeryworker`, `celerybeat`, `flower`, or Docker daemon is forbidden unless a future document explicitly defines an admin-only maintenance channel.

---

## 7. Global Forbidden Exposure

The following ports must never be exposed to the public internet:

```text
3000/tcp  Next.js direct access
5000/tcp  Django/Gunicorn internal service
5555/tcp  Flower or dashboard surface
5432/tcp  PostgreSQL
6379/tcp  Redis
8000/tcp  Django dev/server direct
2375/tcp  Docker daemon TCP without TLS
2376/tcp  Docker daemon TCP with TLS
```

The following services must always remain internal:

```text
postgres
redis
celeryworker
celerybeat
flower
django-api direct port
frontend-next direct port
Docker socket
```

The Docker socket must never be mounted into an application container or into Traefik.

```yaml
forbidden_mounts:
  - /var/run/docker.sock
  - /run/docker.sock
```

Traefik must use a file-provider dynamic configuration generated by the Agent.

---

## 8. Canonical Runtime Networks

The Agent-generated Compose runtime must define three networks:

```text
kx-public   external entrypoint network for Traefik only
kx-private  internal HTTP application network
kx-data     internal data network
```

Required network behavior:

```text
traefik       -> kx-public, kx-private
frontend-next -> kx-private
django-api    -> kx-private, kx-data
media-nginx   -> kx-private
postgres      -> kx-data
redis         -> kx-data
celeryworker  -> kx-private, kx-data
celerybeat    -> kx-private, kx-data
flower        -> kx-private, kx-data when enabled
```

`kx-private` and `kx-data` must be internal Docker networks.

---

## 9. Profile: `offline`

### 9.1 Purpose

`offline` is for isolated demos, testing, forensic inspection, or training where Konnaxion should not be reachable from any other device.

### 9.2 Exposure

```env
KX_NETWORK_PROFILE=offline
KX_EXPOSURE_MODE=private
KX_PUBLIC_MODE_ENABLED=false
KX_HOST=127.0.0.1
KX_HOST_ALIASES=
```

Allowed inbound:

```text
none
```

Allowed bind addresses:

```text
127.0.0.1 only
```

Network policy:

```text
No LAN exposure
No public exposure
No tunnel exposure
No router port forwarding
No external DNS dependency
```

### 9.3 URL

```text
https://localhost
```

Optional fallback:

```text
http://localhost
```

### 9.4 Firewall Policy

```text
deny incoming
allow outgoing only if required for updates
no inbound exception required
```

### 9.5 Security Gate Requirements

Required `PASS` checks:

```text
capsule_signature
image_checksums
manifest_schema
secrets_present
secrets_not_default
postgres_not_public
redis_not_public
docker_socket_not_mounted
no_privileged_containers
no_host_network
dangerous_ports_blocked
```

---

## 10. Profile: `local_only`

### 10.1 Purpose

`local_only` is for demos on the same machine where Konnaxion is opened from the host browser.

This profile is useful for developer machines, trade show laptops, and pre-demo validation.

### 10.2 Exposure

```env
KX_NETWORK_PROFILE=local_only
KX_EXPOSURE_MODE=private
KX_PUBLIC_MODE_ENABLED=false
KX_HOST=127.0.0.1
KX_HOST_ALIASES=localhost,konnaxion.localhost
```

Allowed inbound:

```text
127.0.0.1:443
127.0.0.1:80 optional redirect only
```

Forbidden:

```text
0.0.0.0:3000
0.0.0.0:5000
0.0.0.0:5555
0.0.0.0:5432
0.0.0.0:6379
0.0.0.0:8000
```

### 10.3 URL

Primary:

```text
https://localhost
```

Optional named local URL:

```text
https://konnaxion.localhost
```

### 10.4 TLS Strategy

Allowed:

```text
self-signed local certificate
locally trusted development certificate
HTTP fallback for controlled local-only demo
```

Let’s Encrypt must not be used for `.local` or other non-public hostnames.

### 10.5 Manager UI Label

```text
Local only
Accessible only from this computer.
Recommended for testing and private demos.
```

---

## 11. Profile: `intranet_private`

### 11.1 Purpose

`intranet_private` is the default profile.

It is used when a Konnaxion Box is plugged into a trusted private LAN such as:

```text
school network
community organization network
office LAN
demo room LAN
local lab network
```

### 11.2 Exposure

```env
KX_NETWORK_PROFILE=intranet_private
KX_EXPOSURE_MODE=lan
KX_PUBLIC_MODE_ENABLED=false
KX_HOST=<LAN_HOST_OR_DNS>
KX_HOST_ALIASES=<LAN_IP_OR_EMPTY>
```

Allowed inbound:

```text
LAN:443/tcp
LAN:80/tcp optional redirect only
```

Forbidden inbound:

```text
Internet:any
LAN:3000
LAN:5000
LAN:5555
LAN:5432
LAN:6379
LAN:8000
Docker daemon
```

### 11.3 Allowed Source Ranges

Allowed private source ranges:

```text
10.0.0.0/8
172.16.0.0/12
192.168.0.0/16
fd00::/8
fe80::/10
```

The Manager may detect the active LAN subnet and restrict access to that subnet only.

Example:

```env
KX_ALLOWED_LAN_CIDR=192.168.1.0/24
```

### 11.4 URL

Preferred:

```text
https://konnaxion.local
```

Fallback:

```text
https://<LAN_IP>
```

Optional organization-specific hostname:

```text
https://konnaxion.intranet
https://konnaxion.school.lan
```

### 11.5 TLS Strategy

Allowed:

```text
self-signed local CA
locally trusted intranet certificate
organization-provided certificate
HTTP only if explicitly accepted for temporary LAN demo
```

Not allowed:

```text
Let’s Encrypt for .local
public DNS requirement by default
```

### 11.6 Firewall Policy

The Konnaxion Agent must apply:

```text
deny incoming by default
allow 443/tcp from KX_ALLOWED_LAN_CIDR
allow 80/tcp from KX_ALLOWED_LAN_CIDR only if redirect is enabled
deny 3000/tcp
deny 5000/tcp
deny 5555/tcp
deny 5432/tcp
deny 6379/tcp
deny 8000/tcp
deny Docker daemon ports
```

### 11.7 Manager UI Label

```text
Intranet private
Accessible from this local network only.
Recommended default.
```

### 11.8 Security Gate Requirements

Required `PASS` checks:

```text
firewall_enabled
lan_scope_detected
public_ip_not_exposed
dangerous_ports_blocked
postgres_not_public
redis_not_public
docker_socket_not_mounted
admin_surface_private
```

---

## 12. Profile: `private_tunnel`

### 12.1 Purpose

`private_tunnel` is for remote access by trusted users without opening router ports.

Examples:

```text
Tailscale
WireGuard
ZeroTier
organization VPN
```

### 12.2 Exposure

```env
KX_NETWORK_PROFILE=private_tunnel
KX_EXPOSURE_MODE=vpn
KX_PUBLIC_MODE_ENABLED=false
KX_HOST=<PRIVATE_TUNNEL_HOST>
KX_HOST_ALIASES=
```

Allowed inbound:

```text
VPN/tunnel interface:443/tcp
VPN/tunnel interface:80/tcp optional redirect only
```

Forbidden:

```text
public internet direct access
router port forwarding
public 3000
public 5000
public 5555
public 5432
public 6379
public 8000
```

### 12.3 URL

Example:

```text
https://konnaxion-demo.<tailnet>.ts.net
```

Generic:

```text
https://<PRIVATE_TUNNEL_HOST>
```

### 12.4 Required Variables

```env
KX_NETWORK_PROFILE=private_tunnel
KX_EXPOSURE_MODE=vpn
KX_TUNNEL_PROVIDER=tailscale
KX_TUNNEL_HOST=<generated_or_configured_host>
KX_PUBLIC_MODE_ENABLED=false
KX_HOST=<PRIVATE_TUNNEL_HOST>
KX_HOST_ALIASES=
```

### 12.5 Firewall Policy

```text
deny incoming by default
allow 443/tcp only on tunnel interface
allow 80/tcp only on tunnel interface if redirect enabled
deny 443/tcp on public interface
deny 80/tcp on public interface unless explicitly required
deny all dangerous ports on all interfaces
```

### 12.6 Manager UI Label

```text
Private tunnel
Accessible only to approved tunnel/VPN users.
No router port forwarding required.
```

---

## 13. Profile: `public_temporary`

### 13.1 Purpose

`public_temporary` is for short-lived external demos.

It allows a public link without converting the Konnaxion Box into a permanent public server.

Examples:

```text
client demo
investor demo
partner walkthrough
remote presentation
```

### 13.2 Exposure

```env
KX_NETWORK_PROFILE=public_temporary
KX_EXPOSURE_MODE=temporary_tunnel
KX_PUBLIC_MODE_ENABLED=true
KX_HOST=<TEMPORARY_PUBLIC_HOST>
KX_HOST_ALIASES=
```

Required:

```env
KX_PUBLIC_MODE_DURATION_HOURS=<1|2|4|8>
KX_PUBLIC_MODE_EXPIRES_AT=<ISO8601_TIMESTAMP>
```

The Manager must refuse this profile if `KX_PUBLIC_MODE_EXPIRES_AT` is empty.

### 13.3 Allowed Public Entry

Allowed:

```text
443/tcp through managed tunnel
```

Optional:

```text
80/tcp only for provider-managed HTTPS redirect
```

Forbidden:

```text
direct router port forwarding by default
permanent public exposure
public SSH
public Postgres
public Redis
public Flower
public Docker
public Next.js direct
public Django direct
```

### 13.4 Auth Requirement

At least one of the following must be enabled:

```text
tunnel provider access policy
one-time demo password
basic auth at proxy layer
email allowlist
temporary invite token
```

Default:

```env
KX_PUBLIC_TEMPORARY_AUTH_REQUIRED=true
```

### 13.5 Expiration

When the expiration time is reached, the Manager must:

```text
close tunnel
revoke temporary URL
remove temporary auth tokens
return KX_PUBLIC_MODE_ENABLED=false
return profile to intranet_private or local_only
write audit log entry
```

### 13.6 Manager UI Label

```text
Public temporary demo
Creates a time-limited public link.
Requires authentication.
Automatically expires.
```

### 13.7 Security Gate Requirements

Required `PASS` checks:

```text
public_mode_expiration_present
public_mode_auth_enabled
tunnel_provider_configured
direct_public_ports_blocked
dangerous_ports_blocked
admin_surface_private_or_auth_protected
postgres_not_public
redis_not_public
docker_socket_not_mounted
```

Blocking failure if:

```text
KX_PUBLIC_MODE_EXPIRES_AT is empty
KX_PUBLIC_TEMPORARY_AUTH_REQUIRED=false
public 3000 detected
public 5000 detected
public 5555 detected
public 5432 detected
public 6379 detected
public Docker daemon detected
```

---

## 14. Profile: `public_vps`

### 14.1 Purpose

`public_vps` is for a real public production deployment.

This profile is not the default and should not be used for demo boxes unless the host has been hardened as a public server.

### 14.2 Exposure

```env
KX_NETWORK_PROFILE=public_vps
KX_EXPOSURE_MODE=public
KX_PUBLIC_MODE_ENABLED=true
KX_PUBLIC_MODE_EXPIRES_AT=
KX_HOST=<PUBLIC_DNS_OR_SSLIP_HOST>
KX_HOST_ALIASES=<OPTIONAL_PUBLIC_HOST_ALIASES>
```

Allowed public inbound:

```text
80/tcp
443/tcp
```

SSH:

```text
22/tcp only from admin IP or VPN
```

Forbidden public inbound:

```text
3000/tcp
5000/tcp
5555/tcp
5432/tcp
6379/tcp
8000/tcp
Docker daemon TCP ports
```

The production baseline is:

```text
Expose only 22, 80, and 443.
Restrict SSH to administrator IP or VPN where possible.
Do not expose Next.js direct.
Do not expose Django/Gunicorn direct.
Do not expose Flower/dashboard.
Do not expose Postgres.
Do not expose Redis.
Do not expose Docker daemon.
```

### 14.3 Host Requirement

`public_vps` requires a non-empty public host.

The host must not be:

```text
127.0.0.1
localhost
konnaxion.local
```

Allowed examples:

```text
konnaxion.com
www.konnaxion.com
demo.konnaxion.com
138.197.174.76.sslip.io
```

`sslip.io` or equivalent public wildcard DNS may be used for development or demo VPS deployments when no production domain is available.

The canonical public runtime host is `KX_HOST`.

Optional additional public names must be stored in `KX_HOST_ALIASES`.

Example:

```env
KX_HOST=konnxion.com
KX_HOST_ALIASES=www.konnxion.com,138.197.174.76.sslip.io
```

The Agent must normalize all host values by removing schemes, paths, userinfo, trailing slashes, empty values, and duplicates.

Valid:

```text
konnxion.com
www.konnxion.com
138.197.174.76.sslip.io
```

Invalid:

```text
https://konnxion.com/api/
user:pass@konnxion.com
127.0.0.1
localhost
```

For `public_vps`, `KX_PUBLIC_MODE_EXPIRES_AT` must not be required. Expiration is required only for `public_temporary`.

### 14.4 URL

Example:

```text
https://konnxion.com
https://www.konnxion.com
https://138.197.174.76.sslip.io
```

The canonical public URL shown by the Manager should use `KX_HOST`.

Aliases may be shown as secondary diagnostic URLs.

### 14.5 TLS Strategy

Use public certificate automation only for valid public DNS names.

Allowed:

```text
Let’s Encrypt for valid public domain
provider-managed certificate
organization-managed certificate
temporary self-signed certificate for controlled VPS demo only
```

Forbidden:

```text
Let’s Encrypt for .local
self-signed certificate for public production
```

When multiple public hostnames are configured, certificate automation must either cover all names or clearly indicate which names are covered.

### 14.6 Firewall Policy

Cloud firewall:

```text
allow 80/tcp from anywhere
allow 443/tcp from anywhere
allow 22/tcp only from admin IP or VPN
deny everything else
```

Host firewall:

```text
deny incoming by default
allow 80/tcp
allow 443/tcp
allow 22/tcp only from admin IP or VPN
deny dangerous ports
```

### 14.7 Manager UI Label

```text
Public VPS
Permanent public web deployment.
Requires hardened server and restricted SSH.
```

### 14.8 Droplet/VPS Agent Transport

For a public VPS or Droplet target, the Konnaxion Agent should remain private on the VPS loopback interface:

```text
127.0.0.1:8765
```

The Manager must not require a local tunnel such as:

```text
127.0.0.1:<local-forwarded-port> -> 127.0.0.1:8765
```

Canonical Manager-to-Agent transport for private VPS Agent:

```text
Manager on operator machine
  -> SSH
    -> curl http://127.0.0.1:8765/v1/... on the VPS
      -> Konnaxion Agent
```

The Manager must use SSH-local Agent calls when:

```text
target_mode=droplet
remote_agent_url is empty
remote_agent_url is localhost/127.0.0.1 and represents a local tunnel workaround
```

Direct HTTP to `remote_agent_url` is allowed only when the operator explicitly configures a real non-loopback Agent endpoint.

The Agent API must remain private unless a future document defines a hardened authenticated remote Agent endpoint.

### 14.9 Durable Custom Domain Rule

For `public_vps`, the Manager and Agent must keep two concepts separate:

```text
Public runtime host:
  KX_HOST / host / domain / public_host / droplet_domain
  Example: konnxion.com

SSH target:
  droplet_host / target_host
  Example: 138.197.174.76
```

The public runtime host is what Traefik, Django, and frontend URLs must use.

The SSH target is only for SSH/SCP/SSH-local curl transport.

The Agent must not silently replace a selected custom domain with the Droplet IP or with an old `sslip.io` fallback.

The Manager must send `host` to the Agent during both:

```text
/instances/create
/network/set-profile
```

`/network/set-profile` must persist the host change by regenerating:

```text
/opt/konnaxion/instances/<INSTANCE_ID>/env/kx.env
/opt/konnaxion/instances/<INSTANCE_ID>/env/django.env
/opt/konnaxion/instances/<INSTANCE_ID>/env/frontend.env
/opt/konnaxion/instances/<INSTANCE_ID>/state/docker-compose.runtime.yml
/opt/konnaxion/instances/<INSTANCE_ID>/state/traefik-dynamic.yml
```

`/network/set-profile` must not be validation-only.

It must preserve generated secrets while rewriting host-derived values.

Preserve:

```text
DJANGO_SECRET_KEY
POSTGRES_PASSWORD
DATABASE_URL password component
other generated secrets
```

Rewrite:

```text
KX_HOST
KX_HOST_ALIASES
KX_NETWORK_PROFILE
KX_EXPOSURE_MODE
KX_PUBLIC_MODE_ENABLED
KX_PUBLIC_MODE_EXPIRES_AT
DJANGO_ALLOWED_HOSTS
DJANGO_CSRF_TRUSTED_ORIGINS
CSRF_TRUSTED_ORIGINS
CORS_ALLOWED_ORIGINS
NEXT_PUBLIC_API_BASE
NEXT_PUBLIC_BACKEND_BASE
Traefik Host(...) rules
```

---

## 15. Traefik Routing Contract

All profiles must use this canonical route map:

```text
/        -> frontend-next
/api/    -> django-api
/admin/  -> django-api
/media/  -> media-nginx
```

No profile may expose:

```text
http://<host>:3000
http://<host>:5000
http://<host>:5555
http://<host>:5432
http://<host>:6379
http://<host>:8000
```

The frontend may be reachable internally at:

```text
frontend-next:3000
kx-<instance_id>-frontend-next:3000
```

The Django API may be reachable internally at:

```text
django-api:5000
kx-<instance_id>-django-api:5000
```

PostgreSQL and Redis must be reachable only through Docker private networks.

The Agent must render every public router using the same host rule built from:

```text
KX_HOST
KX_HOST_ALIASES
```

Example for a custom domain with aliases:

```text
(Host(`konnxion.com`) || Host(`www.konnxion.com`) || Host(`138.197.174.76.sslip.io`)) && PathPrefix(`/api/`)
```

For public VPS, a Traefik plain response of:

```text
404 page not found
```

for `https://<KX_HOST>/` or `https://<KX_HOST>/api/` is a blocking routing failure. It means Traefik did not match the public Host header.

---

## 16. Traefik File-Provider Contract

The Agent-generated runtime must use Traefik file-provider dynamic configuration.

Required Traefik static command:

```yaml
command:
  - --providers.file.filename=/etc/traefik/dynamic/traefik-dynamic.yml
  - --providers.file.watch=true
  - --entrypoints.web.address=:80
  - --entrypoints.websecure.address=:443
  - --entrypoints.web.http.redirections.entrypoint.to=websecure
  - --entrypoints.web.http.redirections.entrypoint.scheme=https
  - --api.dashboard=false
```

Required mount:

```yaml
volumes:
  - /opt/konnaxion/instances/<INSTANCE_ID>/state/traefik-dynamic.yml:/etc/traefik/dynamic/traefik-dynamic.yml:ro
```

Forbidden:

```text
Docker socket mount
Traefik Docker provider as required runtime dependency
Public routing implemented only through Docker labels
```

Docker labels may exist for inspection or tests, but they must not be required for production routing.

Canonical dynamic config shape:

```yaml
http:
  routers:
    kx-frontend:
      rule: "(Host(`<KX_HOST>`) || Host(`<KX_HOST_ALIAS>`)) && PathPrefix(`/`)"
      entryPoints:
        - websecure
      tls: {}
      service: frontend-next
      priority: 10

    kx-api:
      rule: "(Host(`<KX_HOST>`) || Host(`<KX_HOST_ALIAS>`)) && PathPrefix(`/api/`)"
      entryPoints:
        - websecure
      tls: {}
      service: django-api
      priority: 100

    kx-admin:
      rule: "(Host(`<KX_HOST>`) || Host(`<KX_HOST_ALIAS>`)) && PathPrefix(`/admin/`)"
      entryPoints:
        - websecure
      tls: {}
      service: django-api
      priority: 100

    kx-media:
      rule: "(Host(`<KX_HOST>`) || Host(`<KX_HOST_ALIAS>`)) && PathPrefix(`/media/`)"
      entryPoints:
        - websecure
      tls: {}
      service: media-nginx
      priority: 100

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
```

The example above is schematic. The Agent must expand aliases into valid Traefik syntax.

If there is only one host, render:

```text
Host(`<KX_HOST>`)
```

If there are multiple hosts, render:

```text
(Host(`<KX_HOST>`) || Host(`<ALIAS_1>`) || Host(`<ALIAS_2>`))
```

All routers must use the same host rule.

---

## 17. Hostname Policy

### 17.1 Local Hostnames

Allowed for `local_only`:

```text
localhost
127.0.0.1
konnaxion.localhost
```

### 17.2 Intranet Hostnames

Allowed for `intranet_private`:

```text
konnaxion.local
konnaxion.lan
custom organization LAN hostname
LAN IP fallback
```

### 17.3 Tunnel Hostnames

Allowed for `private_tunnel`:

```text
provider-generated private hostname
tailnet hostname
organization VPN DNS name
```

### 17.4 Public Hostnames

Allowed for `public_temporary`:

```text
temporary tunnel hostname
controlled demo subdomain
```

Allowed for `public_vps`:

```text
valid public DNS hostname
public wildcard DNS development hostname such as <IP>.sslip.io
```

Examples:

```text
konnaxion.com
www.konnaxion.com
demo.konnaxion.com
138.197.174.76.sslip.io
```

### 17.5 Alias Policy

`KX_HOST_ALIASES` may contain additional public names that should route to the same instance.

Examples:

```text
www.konnaxion.com
138.197.174.76.sslip.io
demo.konnaxion.com
```

Aliases must not include:

```text
empty values
duplicate values
URL schemes
paths
userinfo
localhost values for public_vps
127.0.0.1 for public_vps
```

The Agent must deduplicate aliases and must not include `KX_HOST` again in `KX_HOST_ALIASES`.

---

## 18. Profile Payload Contract

### 18.1 Manager-to-Agent Payload

The Manager must normalize all UI/public-host fields into the Agent field named:

```text
host
```

Accepted Manager-side source fields:

```text
domain
droplet_domain
public_host
public_url
url
host
kx_host
KX_HOST
droplet_host
target_host
```

Normalization order:

```text
host = domain
    or droplet_domain
    or public_host
    or public_url
    or url
    or host
    or kx_host
    or KX_HOST
    or droplet_host
    or target_host
```

The Manager must prefer operator-facing public domain fields before the Droplet IP.

The Manager must keep these meanings distinct:

```text
host / public_host / domain / droplet_domain:
  public runtime host, e.g. konnxion.com

droplet_host / target_host:
  SSH target, e.g. 138.197.174.76
```

The Manager must not send unsupported fields to the Agent profile endpoint.

Do not send:

```text
domain
public_host
droplet_domain
public_url
url
```

unless the Agent schema explicitly supports them.

For `public_vps`, the Manager must send:

```json
{
  "instance_id": "demo-001",
  "network_profile": "public_vps",
  "exposure_mode": "public",
  "host": "konnxion.com",
  "host_aliases": [
    "www.konnxion.com",
    "138.197.174.76.sslip.io"
  ],
  "public_mode_enabled": true,
  "public_mode_expires_at": null
}
```

If the Agent schema does not yet support `host_aliases`, the Manager must still send `host` and the Agent may derive aliases from known Droplet metadata.

### 18.2 Agent Schema

The Agent network profile request must accept:

```text
instance_id
network_profile
exposure_mode
host
host_aliases
public_mode_enabled
public_mode_expires_at
```

`host_aliases` may be optional.

The Agent must reject unknown extra fields unless the API contract is intentionally extended.

### 18.3 Public VPS Validation

For `public_vps`, the Agent must reject:

```text
empty host
localhost
127.0.0.1
.local hostnames
```

unless explicitly running a local-only test fixture.

For `public_vps`, the Agent must not require `public_mode_expires_at`.

Expiration is required only for:

```text
network_profile=public_temporary
exposure_mode=temporary_tunnel
```

### 18.4 Instance Creation Payload

For `public_vps`, the Manager must send `host` during instance creation, not only during a later network-profile update.

Required `/instances/create` behavior:

```json
{
  "instance_id": "demo-001",
  "capsule_id": "konnaxion-v14-demo-2026.04.30",
  "network_profile": "public_vps",
  "exposure_mode": "public",
  "host": "konnxion.com",
  "generate_secrets": true
}
```

This prevents first-rendered env and Traefik files from freezing an old fallback host.

---

## 19. Environment Output Contract

When a profile is applied, the Agent must generate environment values for backend, frontend, and runtime metadata.

### 19.1 Runtime

```env
KX_NETWORK_PROFILE=<profile>
KX_EXPOSURE_MODE=<mode>
KX_PUBLIC_MODE_ENABLED=<true|false>
KX_PUBLIC_MODE_EXPIRES_AT=<timestamp_or_empty>
KX_HOST=<PROFILE_HOST>
KX_HOST_ALIASES=<comma_separated_aliases_or_empty>
KX_ALLOWED_LAN_CIDR=<cidr_or_empty>
KX_TUNNEL_PROVIDER=<provider_or_empty>
KX_TUNNEL_HOST=<hostname_or_empty>
```

For `public_vps`:

```env
KX_NETWORK_PROFILE=public_vps
KX_EXPOSURE_MODE=public
KX_PUBLIC_MODE_ENABLED=true
KX_PUBLIC_MODE_EXPIRES_AT=
KX_HOST=konnxion.com
KX_HOST_ALIASES=www.konnxion.com,138.197.174.76.sslip.io
```

`KX_HOST` must not be `127.0.0.1` for `public_vps`.

### 19.2 Django

```env
DJANGO_ALLOWED_HOSTS=<generated_from_profile>
DJANGO_CSRF_TRUSTED_ORIGINS=<generated_from_profile>
CSRF_TRUSTED_ORIGINS=<generated_from_profile>
CORS_ALLOWED_ORIGINS=<generated_from_profile>
```

For `public_vps`, `DJANGO_ALLOWED_HOSTS` must include:

```text
127.0.0.1
localhost
<PUBLIC_HOST>
<PUBLIC_HOST_ALIASES>
django-api
kx-<INSTANCE_ID>-django-api
```

For `public_vps`, CSRF/CORS trusted origins must include:

```text
https://<PUBLIC_HOST>
http://<PUBLIC_HOST>
https://<PUBLIC_HOST_ALIAS>
http://<PUBLIC_HOST_ALIAS>
```

Example:

```env
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,konnxion.com,www.konnxion.com,138.197.174.76.sslip.io,django-api,kx-demo-001-django-api
DJANGO_CSRF_TRUSTED_ORIGINS=https://konnxion.com,http://konnxion.com,https://www.konnxion.com,http://www.konnxion.com,https://138.197.174.76.sslip.io,http://138.197.174.76.sslip.io
CSRF_TRUSTED_ORIGINS=https://konnxion.com,http://konnxion.com,https://www.konnxion.com,http://www.konnxion.com,https://138.197.174.76.sslip.io,http://138.197.174.76.sslip.io
CORS_ALLOWED_ORIGINS=https://konnxion.com,http://konnxion.com,https://www.konnxion.com,http://www.konnxion.com,https://138.197.174.76.sslip.io,http://138.197.174.76.sslip.io
```

### 19.3 Frontend

```env
NEXT_PUBLIC_API_BASE=https://<PROFILE_HOST>/api
NEXT_PUBLIC_BACKEND_BASE=https://<PROFILE_HOST>
NEXT_TELEMETRY_DISABLED=1
```

The frontend must use canonical `KX_HOST`, not an arbitrary alias.

Because Next.js may bake public environment values at build time, a profile change that modifies public frontend URLs requires one of:

```text
frontend image rebuild
runtime configuration injection strategy
frontend environment file regenerated before build/export
```

For the Konnaxion capsule runtime, the accepted durable behavior is:

```text
Agent regenerates frontend.env before runtime start.
Frontend runtime reads the generated runtime configuration.
```

### 19.4 Secret Preservation

When the profile host changes, the Agent must update host-derived values without rotating secrets.

Preserve existing values for:

```text
DJANGO_SECRET_KEY
POSTGRES_PASSWORD
DATABASE_URL password component
other generated secrets
```

Regenerate or update values for:

```text
KX_HOST
KX_HOST_ALIASES
DJANGO_ALLOWED_HOSTS
DJANGO_CSRF_TRUSTED_ORIGINS
CSRF_TRUSTED_ORIGINS
CORS_ALLOWED_ORIGINS
NEXT_PUBLIC_API_BASE
NEXT_PUBLIC_BACKEND_BASE
Traefik Host() rules
```

---

## 20. Runtime Healthcheck Contract

Healthchecks must not rely on tools missing from stock runtime images.

### 20.1 Django

Django healthcheck must not require `wget`.

Preferred check:

```yaml
healthcheck:
  test:
    - CMD-SHELL
    - python -c "import socket; sock=socket.create_connection(('127.0.0.1',5000),5); sock.close()"
  interval: 30s
  timeout: 5s
  retries: 10
```

The Django API route `/api/health/` may exist in future, but Compose health must not depend on it unless the image reliably contains a client tool and the route is guaranteed.

### 20.2 Media Nginx

For stock `nginx:stable`, healthcheck should use a command available in the image.

Allowed:

```yaml
healthcheck:
  test:
    - CMD-SHELL
    - nginx -t >/dev/null 2>&1
  interval: 30s
  timeout: 5s
  retries: 5
```

Do not use `wget` unless the selected media image includes `wget`.

### 20.3 Frontend

Frontend readiness may be validated by container status and Traefik route test.

Allowed internal check:

```text
node-based HTTP probe
```

Forbidden:

```text
runtime Corepack download
runtime pnpm download
network dependency to start Next.js
```

### 20.4 Public Host Route Checks

For `public_vps`, external checks must include the canonical host and configured aliases.

Canonical host checks:

```text
https://<KX_HOST>/
https://<KX_HOST>/api/
https://<KX_HOST>/admin/
https://<KX_HOST>/media/
```

Alias checks when aliases exist:

```text
https://<KX_HOST_ALIAS>/
https://<KX_HOST_ALIAS>/api/
```

A Django application `404` from `/api/` may be acceptable if the path does not exist.

A Traefik plain `404 page not found` is not acceptable for `public_vps`.

---

## 21. Frontend Runtime Image Contract

The production frontend image must not require network access to start.

The runtime layer must include:

```text
package.json
node_modules
.next
public
next.config.*
env.mjs
```

The runtime command must not be:

```text
pnpm start
corepack pnpm start
```

Canonical runtime command:

```text
node node_modules/next/dist/bin/next start -H 0.0.0.0 -p 3000
```

Required environment:

```env
NODE_ENV=production
PORT=3000
HOSTNAME=0.0.0.0
NEXT_TELEMETRY_DISABLED=1
```

---

## 22. Profile Switching Rules

Allowed transitions:

```text
offline -> local_only
offline -> intranet_private
local_only -> intranet_private
intranet_private -> private_tunnel
intranet_private -> public_temporary
private_tunnel -> intranet_private
public_temporary -> intranet_private
public_vps -> public_vps
```

Restricted transitions:

```text
any -> public_vps
```

`public_vps` requires explicit operator confirmation and a successful hardening check.

Automatic transition:

```text
public_temporary -> intranet_private
```

This happens when `KX_PUBLIC_MODE_EXPIRES_AT` is reached.

When switching host or profile, the Agent must regenerate runtime files. The change is not complete until the following are consistent:

```text
kx.env
django.env
frontend.env
docker-compose.runtime.yml
traefik-dynamic.yml
Security Gate result
```

---

## 23. Backup, Restore and Rollback Network Behavior

Backup, restore and rollback workflows are defined in `DOC-09_Konnaxion_Backup_Restore_Rollback.md`, but network behavior is governed by this document.

The network profile selected during restore must never weaken the Security Gate.

Default restore target:

```env
KX_RESTORE_DEFAULT_NETWORK_PROFILE=local_only
```

The safest restore target is `local_only` because it allows validation before LAN, tunnel, or public exposure.

### 23.1 Restore Behavior by Profile

| Target profile     | Restore behavior                                                                                           |
| ------------------ | ---------------------------------------------------------------------------------------------------------- |
| `offline`          | Allowed only for isolated validation. No network exposure.                                                 |
| `local_only`       | Default and safest restore target. Used for restore tests and high-risk recovery.                          |
| `intranet_private` | Allowed after Security Gate `PASS`; exposes Traefik to LAN only.                                           |
| `private_tunnel`   | Allowed only after tunnel configuration is validated. No router port forwarding.                           |
| `public_temporary` | Must not auto-enable public access after restore. Requires explicit operator action, auth, and expiration. |
| `public_vps`       | Requires explicit approval, hardened firewall, SSH hardening, backups enabled, and Security Gate `PASS`.   |

### 23.2 Restore Into New Instance

A restore into a new instance must default to:

```env
KX_NETWORK_PROFILE=local_only
KX_EXPOSURE_MODE=private
KX_PUBLIC_MODE_ENABLED=false
```

The operator may switch the restored instance to `intranet_private`, `private_tunnel`, `public_temporary`, or `public_vps` only after:

```text
backup verification passed
restore preflight passed
restore postflight passed
Security Gate passed
healthchecks passed
dangerous ports remain blocked
```

### 23.3 Restore Into Existing Instance

A restore into an existing instance must preserve the current network profile only if the profile is still valid and safe.

If the current profile is unsafe, unknown, expired, or incompatible, the Agent must fall back to:

```env
KX_NETWORK_PROFILE=local_only
KX_EXPOSURE_MODE=private
KX_PUBLIC_MODE_ENABLED=false
```

### 23.4 Public Temporary Restore Rule

A restored instance must never automatically reopen a previous `public_temporary` URL.

If the backup manifest contains:

```env
KX_NETWORK_PROFILE=public_temporary
KX_PUBLIC_MODE_ENABLED=true
```

the restored instance must start as:

```env
KX_NETWORK_PROFILE=local_only
KX_EXPOSURE_MODE=private
KX_PUBLIC_MODE_ENABLED=false
KX_PUBLIC_MODE_EXPIRES_AT=
```

The operator may create a new temporary public URL only through the Manager UI or canonical CLI, with authentication and expiration.

### 23.5 Public VPS Restore Rule

A restored `public_vps` instance must not become public until the following checks pass:

```text
firewall_enabled
dangerous_ports_blocked
postgres_not_public
redis_not_public
docker_socket_not_mounted
admin_surface_private
ssh_restricted
root_ssh_disabled
password_ssh_disabled
backups_enabled
public_host_present
public_host_not_localhost
traefik_host_rules_contain_kx_host
```

If any check fails, the instance must remain in `local_only` or `intranet_private`.

### 23.6 Rollback Network Rule

Rollback must not increase exposure.

Allowed automatic rollback transitions:

```text
public_temporary -> intranet_private
private_tunnel -> intranet_private
public_vps -> public_vps only if Security Gate PASS
any profile -> local_only
```

Forbidden automatic rollback transitions:

```text
local_only -> public_temporary
intranet_private -> public_temporary
private_tunnel -> public_temporary
any profile -> public_vps
```

### 23.7 Backup Metadata for Network Profiles

Every backup manifest must record the active network profile as metadata:

```yaml
network:
  kx_network_profile: intranet_private
  kx_exposure_mode: private
  kx_public_mode_enabled: false
  kx_public_mode_expires_at: null
  kx_host: konnaxion.local
  kx_host_aliases: []
```

This metadata is used to propose a restore profile, but it must not override current Security Gate policy.

### 23.8 Manager UX Requirement

During restore, the Manager must show:

```text
Backup source profile: <PROFILE_FROM_BACKUP>
Restore target profile: <SELECTED_SAFE_PROFILE>
Public exposure after restore: disabled by default
```

For `public_temporary` and `public_vps`, the Manager must require explicit confirmation before any public exposure is enabled.

---

## 24. Security Gate Integration

Before applying any profile, the Manager must call:

```bash
kx security check <INSTANCE_ID> --profile <KX_NETWORK_PROFILE>
```

The profile may be applied only if all blocking checks return `PASS`.

Canonical blocking checks:

```text
capsule_signature
image_checksums
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
runtime_env_host_matches_profile
traefik_dynamic_host_matches_profile
frontend_public_env_matches_profile
```

Additional checks for `public_temporary`:

```text
public_mode_expiration_present
public_mode_auth_enabled
tunnel_provider_configured
```

Additional checks for `public_vps`:

```text
public_host_present
public_host_not_localhost
public_host_not_loopback
ssh_restricted
root_ssh_disabled
password_ssh_disabled
cloud_firewall_present_or_acknowledged
backups_enabled
django_allowed_hosts_contains_kx_host
django_allowed_hosts_contains_kx_host_aliases
frontend_public_urls_match_kx_host
traefik_host_rules_contain_kx_host
traefik_host_rules_contain_kx_host_aliases
```

Blocking failure if `public_vps` generates:

```text
KX_HOST=127.0.0.1
KX_HOST=localhost
DJANGO_ALLOWED_HOSTS without public host
NEXT_PUBLIC_API_BASE=https://127.0.0.1/api
Traefik Host(`127.0.0.1`)
Traefik dynamic config missing KX_HOST
Docker socket mount
public direct 3000/5000/5432/6379/5555/8000
```

Blocking failure if a custom domain is selected but only the fallback `sslip.io` hostname appears in Traefik Host rules.

---

## 25. Manager UX Contract

The user must not see raw Docker or firewall details during normal operation.

The user sees:

```text
Mode réseau:
- Local seulement
- Intranet privé
- Tunnel privé
- Public temporaire
- Public VPS
```

The user sees the result:

```text
Current mode: Intranet private
Access URL: https://konnaxion.local
Internet exposure: Disabled
Security status: OK
```

Advanced details may be available under:

```text
Security details
Network diagnostics
Logs
```

For `public_vps`, the Manager must clearly show:

```text
Public host: <KX_HOST>
Public URL: https://<KX_HOST>
Public aliases: <KX_HOST_ALIASES or none>
Agent transport: SSH-local private Agent
Published ports: 80/443 only
SSH: operator-managed
```

The Manager must not confuse the public runtime host with the SSH target.

Example:

```text
Public host: konnxion.com
Public aliases: www.konnxion.com, 138.197.174.76.sslip.io
SSH target: 138.197.174.76
```

---

## 26. Agent Implementation Contract

The Konnaxion Agent is responsible for applying profile rules.

Allowed actions:

```text
create Docker networks
start/stop allowed services
bind Traefik to approved interfaces
generate Traefik file-provider dynamic config
generate profile-specific environment files
configure tunnel provider
close expired tunnel
run Security Gate checks
write audit logs
```

Forbidden actions:

```text
run arbitrary shell commands from capsule manifest
start unknown containers
pull unsigned images
mount Docker socket into containers
enable privileged containers
bind forbidden ports
open public router ports automatically
disable firewall
silently replace public_vps host with 127.0.0.1
silently replace selected custom domain with Droplet IP
silently keep stale Traefik Host rules after network profile change
```

When applying a profile, the Agent must persist runtime changes.

Required persistent outputs:

```text
env/kx.env
env/django.env
env/frontend.env
state/docker-compose.runtime.yml
state/traefik-dynamic.yml
```

A successful `network.set_profile` action must return enough metadata to diagnose what changed:

```text
instance_id
network_profile
exposure_mode
host
host_aliases
public_mode_enabled
public_mode_expires_at
env files written
compose file path
traefik dynamic file path
```

---

## 27. Manager Implementation Contract

For Droplet/VPS deployments, the Manager must:

```text
keep remote Agent private on 127.0.0.1:8765
use SSH-local curl for Agent API calls
copy capsule artifacts over SSH/SCP
normalize domain/public_host/droplet_host to Agent host
not require a temporary local tunnel
not call http://127.0.0.1:<forwarded-port>/v1 as the permanent transport
```

The following Agent calls must use the same Droplet transport:

```text
health
agent info
capsule import
instance create/update
network set-profile
security check
instance start
logs/status
```

For Droplet/VPS deployments, the Manager must keep these fields distinct:

```text
domain / public_host / droplet_domain / host:
  public runtime host

droplet_host / target_host:
  SSH/SCP target
```

The Manager must send `host` to:

```text
/instances/create
/network/set-profile
```

The Manager should send or derive aliases for:

```text
www.<domain>
<droplet_ip>.sslip.io
```

when these are known and valid.

---

## 28. Audit Log Requirements

Every profile change must create an audit event.

Canonical event fields:

```yaml
event_type: network_profile_changed
instance_id: <INSTANCE_ID>
old_profile: <OLD_PROFILE>
new_profile: <NEW_PROFILE>
host: <PROFILE_HOST>
host_aliases:
  - <ALIAS_1>
  - <ALIAS_2>
exposure_mode: <KX_EXPOSURE_MODE>
public_mode_enabled: <true|false>
public_mode_expires_at: <timestamp_or_empty>
actor: <local_user_or_system>
timestamp: <ISO8601>
security_gate_result: <PASS|FAIL_BLOCKING>
runtime_files_regenerated: <true|false>
```

Public temporary expiration must create:

```yaml
event_type: public_temporary_expired
instance_id: <INSTANCE_ID>
previous_profile: public_temporary
new_profile: intranet_private
timestamp: <ISO8601>
```

Public VPS host changes must create:

```yaml
event_type: public_vps_host_changed
instance_id: <INSTANCE_ID>
old_host: <OLD_KX_HOST>
new_host: <NEW_KX_HOST>
old_aliases:
  - <OLD_ALIAS>
new_aliases:
  - <NEW_ALIAS>
timestamp: <ISO8601>
runtime_files_regenerated: true
```

---

## 29. Acceptance Tests

### 29.1 `local_only`

Expected:

```text
curl -k https://localhost/ returns 200 or redirect
LAN device cannot reach Konnaxion
public internet cannot reach Konnaxion
ports 3000/5000/5432/6379/5555 are not externally reachable
```

### 29.2 `intranet_private`

Expected:

```text
LAN device can reach https://konnaxion.local or https://<LAN_IP>
public internet cannot reach Konnaxion
router has no required port forwarding
Postgres is not reachable from LAN
Redis is not reachable from LAN
Flower is not reachable from LAN unless explicitly protected and enabled
```

### 29.3 `private_tunnel`

Expected:

```text
approved tunnel user can reach Konnaxion
non-approved user cannot reach Konnaxion
no public router port is open
dangerous ports are blocked
```

### 29.4 `public_temporary`

Expected:

```text
public demo URL works
authentication is required
expiration is set
after expiration URL no longer works
profile returns to intranet_private or local_only
dangerous ports remain blocked
```

### 29.5 `public_vps`

Expected:

```text
https://public-host/ returns 200 or redirect
https://public-host/api/ reaches Django, even if the exact path returns application 404
https://public-host/admin/ reaches Django admin
https://public-host/media/ reaches media service or controlled 404
ports 3000/5000/5555/5432/6379/8000 are not public
SSH is key-only and restricted where possible
Traefik listens on 80/443
Traefik dynamic config contains Host(`<public-host>`)
Traefik dynamic config contains Host(`<public-alias>`) when aliases are configured
Django ALLOWED_HOSTS includes <public-host>
Django ALLOWED_HOSTS includes aliases when aliases are configured
frontend public API base uses https://<public-host>/api
Agent remains private on 127.0.0.1:8765
```

Infrastructure success criteria:

```text
frontend-next container is up
django-api container is healthy
postgres container is healthy
redis container is healthy
celeryworker is running
celerybeat is running
traefik is running
```

Host-rule diagnostic checks:

```bash
curl -k -i -H 'Host: <KX_HOST>' https://127.0.0.1/
curl -k -i -H 'Host: <KX_HOST>' https://127.0.0.1/api/
curl -k -i -H 'Host: <KX_HOST_ALIAS>' https://127.0.0.1/
curl -k -i -H 'Host: <KX_HOST_ALIAS>' https://127.0.0.1/api/
```

Local DNS bypass checks:

```bash
curl -k -i --resolve <KX_HOST>:443:<DROPLET_IP> https://<KX_HOST>/
curl -k -i --resolve <KX_HOST>:443:<DROPLET_IP> https://<KX_HOST>/api/
```

Expected failure classification:

```text
curl: could not resolve host
  -> DNS problem

Traefik plain "404 page not found"
  -> Traefik Host rule problem

Django/Uvicorn 404
  -> application route exists through proxy; infrastructure routing is working

Next.js HTML response
  -> frontend route is working
```

---

## 30. Non-Goals

This document does not define:

```text
Docker Compose service implementation
Capsule file format
Agent privilege model
Backup/restore archive format
Backup retention policy
Database restore procedure
GUI screen design beyond network-profile requirements
Cloud provider provisioning
Full threat model
```

Those are defined in separate documents.

---

## 31. Final Rule

Konnaxion networking must be:

```text
private by default
deny by default
Traefik-only at the edge
Traefik file-provider routing, no Docker socket
temporary public access only with expiration
no public database
no public Redis
no public Docker
no public Next.js direct port
no public Django direct port
public_vps must use a real public host
public_vps must not generate localhost-only runtime env
public_vps must propagate KX_HOST to Traefik, Django, and frontend env
public_vps must propagate KX_HOST_ALIASES to Traefik and Django when configured
network.set_profile must regenerate runtime files and must not be validation-only
Manager must preserve the distinction between public runtime host and SSH target
```

If a profile requires exposing an internal service directly, the profile is invalid.
