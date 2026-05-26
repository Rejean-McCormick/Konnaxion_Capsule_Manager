````markdown
doc_id: DOC-16
title: Konnaxion Capsule Manager GUI Technical Contract
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: technical-contract
owner: Konnaxion
last_updated: 2026-05-03
---

# DOC-16 — Konnaxion Capsule Manager GUI Technical Contract

## 1. Purpose

This document defines the fixed technical contract for the Konnaxion Capsule Manager GUI.

It aligns the frontend/UI files with the Manager, Agent, Builder, CLI, shared constants, runtime generation, network profiles, Droplet deployment, and tests.

The GUI must let an operator use Konnaxion from a local browser without manually typing normal lifecycle commands.

The GUI must support:

```text
select Konnaxion source folder
select capsule output folder
build capsule
verify capsule
import capsule
create instance
update instance
start instance
stop instance
restart instance
view status
view health
view logs
run Security Gate
set network profile
disable public mode
create backup
list backups
verify backup
restore backup
restore backup into new instance
test restore backup
rollback instance
configure local/intranet/temporary-public/droplet targets
deploy local/intranet/droplet
````

The GUI must not invent names, states, profiles, routes, actions, service names, runtime variables, or transport modes.

Friendly labels are allowed for display only. Stored and exchanged values must remain canonical.

---

## 2. Runtime Topology

## 2.1 Local services

| Service           | Default URL                   | Purpose                                          |
| ----------------- | ----------------------------- | ------------------------------------------------ |
| Manager GUI/API   | `http://127.0.0.1:8714`       | Browser UI and Manager API                       |
| Agent API         | `http://127.0.0.1:8765/v1`    | Privileged local runtime actions                 |
| Konnaxion runtime | `C:\mycode\Konnaxion\runtime` | Local capsules, instances, backups, shared state |

## 2.2 Local control flow

```text
Browser GUI
  -> kx_manager UI route/action
  -> kx_manager service/client
  -> kx_agent API
  -> kx_agent action/runtime module
  -> Docker/filesystem/backup/network operation
```

The Manager GUI must not directly control Docker, firewall rules, host services, host networking, or backups except through approved Manager service wrappers or Agent calls.

## 2.3 Droplet/VPS control flow

Droplet mode keeps the Agent private on the Droplet by default.

Correct Droplet control flow:

```text
Browser GUI on Windows
  -> local Manager
    -> Manager deploy/action backend
      -> SSH root@droplet
        -> curl http://127.0.0.1:8765/v1/... on the Droplet
          -> Droplet Agent
            -> Docker/runtime operation on the Droplet
```

The Manager must not require a local SSH tunnel such as:

```text
http://127.0.0.1:18765/v1
```

for normal Droplet deployment.

Loopback `remote_agent_url` values in Droplet mode are treated as stale tunnel URLs and must force SSH-local Agent transport.

Allowed Droplet transports:

```text
default:
  ssh-local Agent transport
  ssh root@host "curl http://127.0.0.1:8765/v1/..."

optional:
  direct HTTP only when remote_agent_url is non-loopback
  and points at the selected Droplet host
```

---

## 3. Source File Ownership

## 3.1 Core UI files

| File                            | Responsibility                                      |
| ------------------------------- | --------------------------------------------------- |
| `kx_manager/ui/__init__.py`     | UI package declaration                              |
| `kx_manager/ui/app.py`          | FastAPI `/ui` GUI route registration                |
| `kx_manager/ui/static.py`       | Canonical UI routes, action names, labels, aliases  |
| `kx_manager/ui/pages.py`        | Page IDs, page routes, UI action IDs, page metadata |
| `kx_manager/ui/state.py`        | Canonical UI display state and normalization        |
| `kx_manager/ui/components.py`   | Safe reusable UI rendering helpers                  |
| `kx_manager/ui/render.py`       | Shared FastAPI HTML rendering helpers               |
| `kx_manager/ui/actions.py`      | GUI action dispatcher                               |
| `kx_manager/ui/action_views.py` | GUI action catalog and result rendering             |
| `kx_manager/ui/forms.py`        | Public form parsing and validation facade           |
| `kx_manager/ui/page_views.py`   | Thin page orchestrator and HTMLResponse owner       |
| `kx_manager/ui/page_forms.py`   | Compatibility facade for older page form imports    |

## 3.2 Page body files

Actual page body ownership lives under `kx_manager/ui/page_parts/`.

| File                                    | Responsibility                           |
| --------------------------------------- | ---------------------------------------- |
| `kx_manager/ui/page_parts/__init__.py`  | Flat page-body renderer registry         |
| `kx_manager/ui/page_parts/common.py`    | Shared form, button, and payload helpers |
| `kx_manager/ui/page_parts/dashboard.py` | Dashboard page body                      |
| `kx_manager/ui/page_parts/capsules.py`  | Capsule page body                        |
| `kx_manager/ui/page_parts/instances.py` | Instance page body                       |
| `kx_manager/ui/page_parts/security.py`  | Security Gate page body                  |
| `kx_manager/ui/page_parts/network.py`   | Network page body                        |
| `kx_manager/ui/page_parts/backups.py`   | Backups page body                        |
| `kx_manager/ui/page_parts/restore.py`   | Restore page body                        |
| `kx_manager/ui/page_parts/logs.py`      | Logs page body                           |
| `kx_manager/ui/page_parts/health.py`    | Health page body                         |
| `kx_manager/ui/page_parts/settings.py`  | Settings page body                       |
| `kx_manager/ui/page_parts/targets.py`   | Target configuration page body           |
| `kx_manager/ui/page_parts/deploy.py`    | Deployment action page body              |
| `kx_manager/ui/page_parts/about.py`     | About page body                          |

Rules:

```text
page_views.py is the only page orchestrator.
page_views.py owns route normalization, PageView lookup, and HTMLResponse construction.
page_parts/*.py render page body fragments only.
page_parts/*.py must not call html_response(...).
page_parts/*.py must export render(context: Mapping[str, Any]) -> str.
page_parts/targets.py must render target selection/configuration forms only.
page_parts/deploy.py must render deployment operation forms only.
page_forms.py must remain a compatibility facade only.
Do not create kx_manager/ui/pages/ because kx_manager/ui/pages.py already exists.
```

## 3.3 Form files

| File                              | Responsibility                    |
| --------------------------------- | --------------------------------- |
| `kx_manager/ui/form_registry.py`  | Action-to-form model registry     |
| `kx_manager/ui/form_targets.py`   | Target/deployment form validation |
| `kx_manager/ui/form_network.py`   | Network profile form validation   |
| `kx_manager/ui/form_capsules.py`  | Capsule form validation           |
| `kx_manager/ui/form_instances.py` | Instance form validation          |
| `kx_manager/ui/form_backups.py`   | Backup/restore form validation    |
| `kx_manager/ui/form_core.py`      | Core source/output folder forms   |
| `kx_manager/ui/form_helpers.py`   | Shared validation helpers         |
| `kx_manager/ui/form_constants.py` | UI form defaults and enum imports |
| `kx_manager/ui/form_errors.py`    | Form validation exception         |

## 3.4 Manager service files

| File                             | Responsibility                                               |
| -------------------------------- | ------------------------------------------------------------ |
| `kx_manager/services/builder.py` | Build/verify capsule service wrapper                         |
| `kx_manager/services/targets.py` | Local/intranet/temporary-public/droplet target configuration |
| `kx_manager/services/deploy.py`  | Local/intranet/temporary-public/droplet deployment flow      |

## 3.5 Backend alignment files

| File                               | Responsibility                          |
| ---------------------------------- | --------------------------------------- |
| `kx_manager/client.py`             | Agent API client                        |
| `kx_manager/main.py`               | Manager FastAPI app and UI registration |
| `kx_manager/models.py`             | Manager internal/view models            |
| `kx_manager/schemas.py`            | Manager route schemas                   |
| `kx_manager/routes/capsules.py`    | Capsule Manager routes                  |
| `kx_manager/routes/instances.py`   | Instance Manager routes                 |
| `kx_manager/routes/backups.py`     | Backup/restore routes                   |
| `kx_manager/routes/security.py`    | Security Gate routes                    |
| `kx_manager/routes/network.py`     | Network profile routes                  |
| `kx_manager/routes/logs.py`        | Logs routes                             |
| `kx_agent/api.py`                  | Agent API contracts                     |
| `kx_builder/main.py`               | Builder CLI entrypoint                  |
| `kx_shared/konnaxion_constants.py` | Canonical constants/enums/defaults      |

## 3.6 Droplet deployment critical files

These files enforce the Droplet deploy contract:

| File                                      | Required responsibility                                               |
| ----------------------------------------- | --------------------------------------------------------------------- |
| `kx_manager/ui/agent_execution_client.py` | HTTP/SCP/SSH execution adapter; SSH-local Agent transport for Droplet |
| `kx_manager/services/deploy.py`           | Deployment orchestration; canonical public host normalization         |
| `kx_agent/api.py`                         | Agent request schemas; network profile request contract               |
| `kx_agent/network/profiles.py`            | Profile state application and validation                              |
| `kx_agent/instances/env_writer.py`        | Runtime env generation                                                |
| `kx_agent/instances/secrets.py`           | Env/secrets persistence without freezing public host values forever   |
| `kx_agent/runtime/compose.py`             | Runtime Compose and Traefik file-provider generation                  |
| `kx_agent/runtime/healthchecks.py`        | Container healthcheck commands                                        |
| `kx_builder/images.py`                    | Build/export runtime images                                           |
| `kx_builder/package.py`                   | Include runtime image archives in `.kxcap`                            |
| `kx_builder/verify.py`                    | Fail verification when required image archives are missing            |

---

## 4. Required UI Package Structure

The target UI package must be:

```text
kx_manager/ui/
  __init__.py
  app.py
  actions.py
  action_views.py
  components.py
  forms.py
  form_backups.py
  form_capsules.py
  form_constants.py
  form_core.py
  form_errors.py
  form_helpers.py
  form_instances.py
  form_network.py
  form_registry.py
  form_targets.py
  page_forms.py
  page_views.py
  pages.py
  render.py
  state.py
  static.py
  streamlit_app.py

  page_parts/
    __init__.py
    common.py
    dashboard.py
    capsules.py
    instances.py
    security.py
    network.py
    backups.py
    restore.py
    logs.py
    health.py
    settings.py
    targets.py
    deploy.py
    about.py
```

Rules:

```text
app.py must be FastAPI-compatible.
app.py must expose register(app).
app.py must not require Streamlit.
streamlit_app.py may require Streamlit.
pages.py owns PageId and UiAction identity.
static.py owns UI routes, action routes, labels, browser-only action links, and alias normalization.
state.py owns normalized UI state.
components.py and render.py own reusable rendering helpers.
actions.py owns GUI action dispatch.
action_views.py owns action catalog and result rendering.
forms.py owns the public validation facade.
form_registry.py maps canonical action names to form models.
page_views.py owns page orchestration and HTMLResponse construction.
page_parts/*.py own page bodies only.
page_forms.py exists only for backward-compatible imports.
```

---

## 5. Canonical Environment Variables

| Variable                   | Default                                                                    | Owner                    | Used by                 |
| -------------------------- | -------------------------------------------------------------------------- | ------------------------ | ----------------------- |
| `KX_ROOT`                  | `C:\mycode\Konnaxion\runtime` on Windows dev                               | Shared / Agent / Manager | Runtime root            |
| `KX_SOURCE_DIR`            | `C:\mycode\Konnaxion\Konnaxion`                                            | GUI / Builder            | App source to package   |
| `KX_CAPSULE_OUTPUT_DIR`    | `C:\mycode\Konnaxion\runtime\capsules`                                     | GUI / Builder            | Capsule output folder   |
| `KX_CAPSULE_FILE`          | `C:\mycode\Konnaxion\runtime\capsules\konnaxion-v14-demo-2026.04.30.kxcap` | GUI / Builder            | Capsule output file     |
| `KX_AGENT_HOST`            | `127.0.0.1`                                                                | Agent / Manager client   | Agent bind/connect host |
| `KX_AGENT_PORT`            | `8765`                                                                     | Agent / Manager client   | Agent bind/connect port |
| `KX_AGENT_SCHEME`          | `http`                                                                     | Manager client           | Agent URL scheme        |
| `KX_AGENT_API_PREFIX`      | `/v1`                                                                      | Manager client           | Agent API prefix        |
| `KX_AGENT_URL`             | `http://127.0.0.1:8765/v1`                                                 | Manager client           | Agent base URL          |
| `KX_AGENT_TIMEOUT_SECONDS` | `30.0`                                                                     | Manager client           | Agent request timeout   |
| `KX_AGENT_TOKEN`           | empty                                                                      | Manager client           | Optional auth token     |
| `KX_MANAGER_HOST`          | `127.0.0.1`                                                                | Manager                  | Manager bind host       |
| `KX_MANAGER_PORT`          | `8714`                                                                     | Manager                  | Manager bind port       |
| `KX_MANAGER_URL`           | `http://127.0.0.1:8714`                                                    | GUI / scripts            | Manager base URL        |

## 5.1 Public runtime env contract

For `public_vps`, generated runtime env must use the canonical public host.

Example:

```text
host = 138.197.174.76.sslip.io
```

Required generated values:

```text
KX_HOST=138.197.174.76.sslip.io
KX_NETWORK_PROFILE=public_vps
KX_EXPOSURE_MODE=public
KX_PUBLIC_MODE_ENABLED=true

DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,138.197.174.76.sslip.io,django-api,kx-demo-001-django-api
DJANGO_CSRF_TRUSTED_ORIGINS=https://138.197.174.76.sslip.io,http://138.197.174.76.sslip.io

NEXT_PUBLIC_API_BASE=https://138.197.174.76.sslip.io/api
NEXT_PUBLIC_BACKEND_BASE=https://138.197.174.76.sslip.io
```

Forbidden for `public_vps` generated public runtime env:

```text
KX_HOST=127.0.0.1
DJANGO_ALLOWED_HOSTS=127.0.0.1 only
NEXT_PUBLIC_API_BASE=https://127.0.0.1/api
NEXT_PUBLIC_BACKEND_BASE=https://127.0.0.1
Traefik Host(`127.0.0.1`)
```

---

## 6. Canonical Development Paths

| Name             | Value                                           |
| ---------------- | ----------------------------------------------- |
| Manager repo     | `C:\mycode\Konnaxion\Konnaxion_Capsule_Manager` |
| Konnaxion source | `C:\mycode\Konnaxion\Konnaxion`                 |
| Runtime root     | `C:\mycode\Konnaxion\runtime`                   |
| Capsules dir     | `C:\mycode\Konnaxion\runtime\capsules`          |
| Instances dir    | `C:\mycode\Konnaxion\runtime\instances`         |
| Backups dir      | `C:\mycode\Konnaxion\runtime\backups`           |
| Shared dir       | `C:\mycode\Konnaxion\runtime\shared`            |

Canonical Linux runtime values remain:

```text
/opt/konnaxion
/opt/konnaxion/capsules
/opt/konnaxion/instances
/opt/konnaxion/backups
/opt/konnaxion/shared
```

Windows development may set `KX_ROOT` to a Windows path. Canonical serialized appliance paths must remain POSIX where the runtime contract requires them.

---

## 7. Canonical Product Variables

These values must come from `kx_shared.konnaxion_constants`.

| Variable        | Canonical value             |
| --------------- | --------------------------- |
| `PRODUCT_NAME`  | `Konnaxion`                 |
| `APP_VERSION`   | `v14`                       |
| `PARAM_VERSION` | `kx-param-2026.04.30`       |
| `MANAGER_NAME`  | `Konnaxion Capsule Manager` |
| `AGENT_NAME`    | `Konnaxion Agent`           |
| `BUILDER_NAME`  | `Konnaxion Capsule Builder` |
| `CLI_NAME`      | `kx`                        |

Do not redefine these in UI files.

---

## 8. Canonical Capsule Variables

| Variable                  | Canonical value                       |
| ------------------------- | ------------------------------------- |
| `CAPSULE_EXTENSION`       | `.kxcap`                              |
| `DEFAULT_CHANNEL`         | `demo`                                |
| `DEFAULT_INSTANCE_ID`     | `demo-001`                            |
| `DEFAULT_CAPSULE_ID`      | `konnaxion-v14-demo-2026.04.30`       |
| `DEFAULT_CAPSULE_VERSION` | `2026.04.30-demo.1`                   |
| Default capsule filename  | `konnaxion-v14-demo-2026.04.30.kxcap` |

Default dev capsule output:

```text
C:\mycode\Konnaxion\runtime\capsules\konnaxion-v14-demo-2026.04.30.kxcap
```

## 8.1 Capsule image archive contract

A capsule intended to start a runtime must include image archives under:

```text
images/*.oci.tar
```

Required application image archives for the v14 demo runtime:

```text
images/django-api.oci.tar
images/frontend-next.oci.tar
```

The capsule may either include third-party images as OCI archives or explicitly declare them as allowed external base images, depending on security policy.

At minimum, verification must fail when the manifest/runtime declares app services but `images/` contains only:

```text
images/README.json
```

Builder verify must not return OK for a deployable public_vps capsule missing required runtime image archives.

---

## 9. Target Modes

The GUI must support these target modes.

| Target mode      | Value              | Profile            | Exposure           | Purpose               |
| ---------------- | ------------------ | ------------------ | ------------------ | --------------------- |
| Local only       | `local`            | `local_only`       | `private`          | Same-machine dev/demo |
| Intranet         | `intranet`         | `intranet_private` | `private` or `lan` | LAN/private use       |
| Droplet/VPS      | `droplet`          | `public_vps`       | `public`           | Remote public VPS     |
| Temporary public | `temporary_public` | `public_temporary` | `temporary_tunnel` | Time-limited demo     |

Target mode variables:

| Variable             | Allowed values                                     |
| -------------------- | -------------------------------------------------- |
| `KX_TARGET_MODE`     | `local`, `intranet`, `droplet`, `temporary_public` |
| `KX_TARGET_PROFILE`  | canonical `NetworkProfile` value                   |
| `KX_TARGET_EXPOSURE` | canonical `ExposureMode` value                     |

---

## 10. Droplet Target Variables

Droplet mode requires these values.

| Variable                  | Example                         | Required |
| ------------------------- | ------------------------------- | -------: |
| `KX_DROPLET_NAME`         | `konnaxion-prod-01`             |      yes |
| `KX_DROPLET_HOST`         | `203.0.113.10`                  |      yes |
| `KX_DROPLET_USER`         | `root`                          |      yes |
| `KX_DROPLET_SSH_KEY_PATH` | `C:\Users\user\.ssh\id_ed25519` |      yes |
| `KX_DROPLET_KX_ROOT`      | `/opt/konnaxion`                |      yes |
| `KX_DROPLET_CAPSULE_DIR`  | `/opt/konnaxion/capsules`       |      yes |
| `KX_DROPLET_DOMAIN`       | `app.example.com`               |      yes |
| `KX_DROPLET_AGENT_URL`    | non-loopback Agent URL only     | optional |
| `KX_DROPLET_SSH_PORT`     | `22`                            | optional |

Droplet mode must not assume password SSH. Use SSH key path or an explicit configured credential mechanism.

Droplet GUI forms and buttons must submit:

```text
target_mode = droplet
network_profile = public_vps
exposure_mode = public
confirmed = true
```

Droplet operations must never inherit the private/intranet default payload.

## 10.1 Droplet Agent URL rules

The Droplet Agent is private by default:

```text
http://127.0.0.1:8765/v1
```

This address is private to the Droplet.

The Manager on Windows must reach it by SSH-local curl:

```powershell
ssh root@<droplet_host> "curl http://127.0.0.1:8765/v1/health"
```

A loopback `KX_DROPLET_AGENT_URL` such as:

```text
http://127.0.0.1:18765/v1
http://localhost:18765/v1
```

must be treated as stale tunnel/localhost configuration and must not be used for direct Manager HTTP calls.

In Droplet mode:

```text
remote_agent_url blank                  -> SSH-local Agent transport
remote_agent_url loopback               -> SSH-local Agent transport
remote_agent_url host != droplet_host   -> SSH-local Agent transport
remote_agent_url host == droplet_host   -> direct HTTP allowed only if explicitly configured
```

## 10.2 Droplet host normalization

Manager and UI may collect the public host under names such as:

```text
domain
droplet_domain
public_host
host
```

Before calling Agent network APIs, Manager must normalize these to:

```text
host
```

The Agent network profile API must not require or accept `domain` as the canonical runtime field.

Correct mapping:

```text
domain / droplet_domain / public_host / droplet_host
  -> host
```

---

## 11. Canonical Docker Service Names

Only these service names are valid:

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

Forbidden aliases:

```text
backend
api
web
next
frontend
db
database
cache
worker
scheduler
media
agent
```

---

## 12. Canonical Network Profiles

| Profile          | Value              | Public by default |
| ---------------- | ------------------ | ----------------: |
| Local only       | `local_only`       |                no |
| Intranet private | `intranet_private` |                no |
| Private tunnel   | `private_tunnel`   |                no |
| Public temporary | `public_temporary` | no, explicit only |
| Public VPS       | `public_vps`       | no, explicit only |
| Offline          | `offline`          |                no |

Default:

```text
DEFAULT_NETWORK_PROFILE = intranet_private
```

Public VPS rules:

```text
public_vps requires explicit confirmation
public_vps requires explicit public host
public_vps must not default KX_HOST to 127.0.0.1
public_vps must not default Traefik Host() to 127.0.0.1
public_vps must not default Django allowed hosts to 127.0.0.1 only
```

---

## 13. Canonical Exposure Modes

| Mode             | Value              |
| ---------------- | ------------------ |
| Private          | `private`          |
| LAN              | `lan`              |
| VPN              | `vpn`              |
| Temporary tunnel | `temporary_tunnel` |
| Public           | `public`           |

Default:

```text
DEFAULT_EXPOSURE_MODE = private
```

Allowed profile/exposure combinations:

```text
local_only -> private
intranet_private -> private or lan
private_tunnel -> private or vpn
public_temporary -> temporary_tunnel
public_vps -> public
offline -> private
```

Rules:

```text
public_temporary requires public_mode_expires_at
public_temporary requires confirmation
public_vps requires explicit confirmation
public_vps requires host
public exposure must never be default
```

---

## 14. Canonical Instance States

Only these values are valid:

```text
created
importing
verifying
ready
starting
running
stopping
stopped
updating
rolling_back
degraded
failed
security_blocked
```

UI labels may be friendly. Stored values must remain canonical.

---

## 15. Canonical Security Gate Statuses

Only these values are valid:

```text
PASS
WARN
FAIL_BLOCKING
SKIPPED
UNKNOWN
```

Start gating must respect Security Gate status.

---

## 16. Canonical Backup Statuses

Only these values are valid:

```text
created
running
verifying
verified
failed
expired
deleted
quarantined
```

---

## 17. Canonical Restore Statuses

Only these values are valid:

```text
planned
preflight
creating_pre_restore_backup
restoring_database
restoring_media
running_migrations
running_security_gate
running_healthchecks
restored
degraded
failed
rolled_back
```

---

## 18. Canonical Rollback Statuses

Only these values are valid:

```text
planned
running
capsule_repointed
data_restored
healthchecking
completed
failed
```

---

## 19. UI Page IDs

`kx_manager/ui/pages.py` owns page IDs.

The active FastAPI page route surface is:

| Page      | `PageId` value | Route           |
| --------- | -------------- | --------------- |
| Dashboard | `dashboard`    | `/ui`           |
| Capsules  | `capsules`     | `/ui/capsules`  |
| Instances | `instances`    | `/ui/instances` |
| Security  | `security`     | `/ui/security`  |
| Network   | `network`      | `/ui/network`   |
| Backups   | `backups`      | `/ui/backups`   |
| Restore   | `restore`      | `/ui/restore`   |
| Logs      | `logs`         | `/ui/logs`      |
| Health    | `health`       | `/ui/health`    |
| Settings  | `settings`     | `/ui/settings`  |
| Targets   | `targets`      | `/ui/targets`   |
| Deploy    | `deploy`       | `/ui/deploy`    |
| About     | `about`        | `/ui/about`     |

Subroutes such as `/ui/capsules/import`, `/ui/instances/detail`, and `/ui/instances/create` are not part of the current required FastAPI page route surface unless explicitly added later.

Page responsibility split:

```text
/ui/targets
  target configuration only
  set_target_local
  set_target_intranet
  set_target_temporary_public
  set_target_droplet

/ui/deploy
  deployment operations only
  deploy_local
  deploy_intranet
  deploy_droplet
  check_droplet_agent
  copy_capsule_to_droplet
  start_droplet_instance
```

---

## 20. UI Page Groups

Only these page groups are valid:

```text
overview
operations
safety
system
deployment
```

Mapping:

| Group        | Pages                                 |
| ------------ | ------------------------------------- |
| `overview`   | dashboard                             |
| `operations` | capsules, instances, backups, restore |
| `safety`     | security, network                     |
| `system`     | logs, health, settings, about         |
| `deployment` | targets, deploy                       |

---

## 21. GUI FastAPI Route Contract

`kx_manager/ui/app.py` must expose:

```python
def register(app: FastAPI) -> None:
    ...
```

It must register:

```text
GET  /ui
GET  /ui/capsules
GET  /ui/instances
GET  /ui/security
GET  /ui/network
GET  /ui/backups
GET  /ui/restore
GET  /ui/logs
GET  /ui/health
GET  /ui/settings
GET  /ui/about
GET  /ui/targets
GET  /ui/deploy
```

Action routes are defined in DOC-17.

---

## 22. UI State Models

`kx_manager/ui/state.py` owns display state normalization.

Do not duplicate these models elsewhere.

| UI model               | Purpose                           |
| ---------------------- | --------------------------------- |
| `CapsuleUiState`       | Capsule summary display           |
| `SecurityCheckUiState` | One Security Gate check           |
| `SecurityUiState`      | Aggregate Security Gate state     |
| `NetworkUiState`       | Network/exposure/public URL state |
| `BackupUiState`        | Latest backup summary             |
| `InstanceUiState`      | Instance display summary          |
| `ManagerUiState`       | Top-level UI state                |

Add target state models:

| UI model               | Purpose                            |
| ---------------------- | ---------------------------------- |
| `TargetModeUiState`    | Selected target mode               |
| `DropletTargetUiState` | Droplet host/SSH/domain config     |
| `BuildTargetUiState`   | Source/output/capsule build config |

---

## 23. UI Component Rules

`kx_manager/ui/components.py` owns reusable UI fragments.

Components may render:

```text
badges
cards
metrics
tables
buttons
links
empty states
definition lists
action bars
forms
result panels
log blocks
```

Component rules:

```text
HTML output must be escaped by default.
Stored values remain canonical.
Display labels may be friendly.
Components must not invent canonical values.
Components must not execute actions.
```

---

## 24. GUI Forms

`kx_manager/ui/forms.py` must expose the public form validation API.

Required form models:

```text
BuildCapsuleForm
VerifyCapsuleForm
ImportCapsuleForm
CreateInstanceForm
UpdateInstanceForm
InstanceActionForm
LogsForm
BackupForm
RestoreForm
RollbackForm
NetworkProfileForm
TargetModeForm
LocalTargetForm
IntranetTargetForm
TemporaryPublicTargetForm
DropletTargetForm
DeployLocalForm
DeployIntranetForm
DeployDropletForm
CheckDropletAgentForm
CopyCapsuleToDropletForm
StartDropletInstanceForm
```

Rules:

```text
source_dir must exist
capsule_output_dir must exist or be creatable
capsule_file must end with .kxcap
instance_id must be safe
service must be canonical DockerService
network_profile must be canonical NetworkProfile
exposure_mode must be canonical ExposureMode
public_temporary requires public_mode_expires_at
public_temporary requires confirmation
droplet mode requires droplet_host
droplet mode requires droplet_user
droplet mode requires ssh_key_path
droplet mode requires remote_kx_root
droplet mode requires remote_capsule_dir
droplet mode requires domain
droplet mode requires confirmation
deploy_droplet requires capsule_file
copy_capsule_to_droplet requires capsule_file
start_droplet_instance requires instance_id
restore_data rollback requires backup_id
```

Droplet form normalization:

```text
domain / droplet_domain / public_host -> host for Agent network payloads
remote_agent_url blank or loopback -> SSH-local Agent transport
```

---

## 25. GUI Action Dispatcher

`kx_manager/ui/actions.py` must own the action dispatcher.

Required shape:

```python
class GuiActionResult:
    ok: bool
    action: str
    message: str
    instance_id: str | None
    data: dict[str, Any]
    stdout: str | None
    stderr: str | None
    returncode: int | None
```

Required dispatcher function:

```python
async def dispatch_gui_action(action: UiAction, payload: Mapping[str, Any]) -> GuiActionResult:
    ...
```

Rules:

```text
Every action must be allowlisted.
Unknown actions must be rejected.
No shell=True.
No arbitrary command text.
All output must be captured and rendered safely.
```

---

## 26. Builder Service

`kx_manager/services/builder.py` owns local build/verify capsule operations.

Required functions:

```python
def build_capsule(request: BuildCapsuleRequest) -> BuildCapsuleResult:
    ...

def verify_capsule(capsule_file: Path) -> VerifyCapsuleResult:
    ...
```

Temporary backend may call:

```text
uv run kx-builder capsule build ...
uv run kx-builder capsule verify ...
```

Final backend should call `kx_builder` Python APIs directly.

## 26.1 Builder image export contract

Builder must be able to build/export runtime images needed by the capsule.

For the v14 demo runtime, Builder must support at least:

```text
konnaxion/django-api:v14
konnaxion/frontend-next:v14
```

Frontend runtime image must not require network access at container start.

Frontend image runtime command must be equivalent to:

```text
node node_modules/next/dist/bin/next start -H 0.0.0.0 -p 3000
```

Frontend runtime image must include:

```text
package.json
node_modules
.next
public
next.config.*
env.mjs
```

Forbidden frontend runtime behavior:

```text
pnpm start that triggers Corepack download
runtime fetch from registry.npmjs.org
missing env.mjs
```

---

## 27. Target Service

`kx_manager/services/targets.py` owns target configuration.

Required target modes:

```text
local
intranet
droplet
temporary_public
```

Required functions:

```python
def validate_target_config(config: TargetConfig) -> None:
    ...

def network_profile_for_target(target_mode: str) -> NetworkProfile:
    ...

def exposure_mode_for_target(target_mode: str) -> ExposureMode:
    ...
```

---

## 28. Deploy Service

`kx_manager/services/deploy.py` owns deployment flows.

Required functions:

```python
def deploy_local(request: LocalDeployRequest) -> DeployResult:
    ...

def deploy_intranet(request: IntranetDeployRequest) -> DeployResult:
    ...

def deploy_droplet(request: DropletDeployRequest) -> DeployResult:
    ...
```

Deployment responsibilities:

```text
build capsule
verify capsule
copy capsule if remote
import capsule
create or update instance
set network profile
start instance
run Security Gate
return status/health/log links
```

Droplet deployment responsibilities:

```text
validate SSH config
copy capsule to remote /opt/konnaxion/capsules
ensure remote runtime folders
contact private remote Agent through SSH-local curl by default
import/update/start on remote target
run remote health/security checks
normalize domain/public_host/droplet_host into host for Agent network profile
never send domain to Agent network profile unless Agent schema explicitly supports it
```

Deployment order:

```text
validate request
prepare capsule
copy capsule to Droplet
ensure remote runtime
check Droplet Agent through SSH-local health
probe Agent contract
import capsule
create/update instance
set network profile with host
run Security Gate
start instance
```

---

## 29. Normalized GUI Action Result

Every GUI action must normalize to:

```json
{
  "ok": true,
  "action": "start_instance",
  "instance_id": "demo-001",
  "message": "Instance started.",
  "state": "running",
  "security_status": "PASS",
  "restore_status": null,
  "rollback_status": null,
  "data": {}
}
```

Command fallback result:

```json
{
  "ok": false,
  "action": "build_capsule",
  "instance_id": null,
  "message": "Command failed.",
  "data": {
    "argv": ["uv", "run", "kx-builder", "capsule", "build"],
    "returncode": 1,
    "stdout": "...",
    "stderr": "..."
  }
}
```

Droplet transport result data must include:

```json
{
  "agent_transport": "ssh",
  "agent_health_url": "http://127.0.0.1:8765/v1/health",
  "remote_agent_url": "",
  "host": "138.197.174.76.sslip.io",
  "public_url": "https://138.197.174.76.sslip.io"
}
```

when the Agent is private on the Droplet.

---

## 30. Required UI Labels

Use these exact main nav labels:

```text
Dashboard
Capsules
Instances
Targets
Deploy
Security
Network
Backups
Restore
Logs
Health
Settings
About
```

Use these exact primary labels:

```text
Check Manager
Check Agent
Select Source Folder
Select Output Folder
Build Capsule
Rebuild Capsule
Verify Capsule
Import Capsule
List Capsules
View Capsule
Create Instance
Update Instance
Start Instance
Stop Instance
Restart Instance
Instance Status
View Logs
Instance Health
Open Instance
Run Security Check
Set Network Profile
Disable Public Mode
Create Backup
List Backups
Verify Backup
Restore Backup
Restore Backup New
Test Restore Backup
Rollback
Set Local Target
Set Intranet Target
Set Droplet Target
Set Temporary Public Target
Deploy Local
Deploy Intranet
Deploy Droplet
Check Droplet Agent
Copy Capsule to Droplet
Start Droplet Instance
Open Manager Docs
Open Agent Docs
```

Danger labels:

```text
Stop Instance
Restore Backup
Restore Backup New
Rollback
Disable Public Mode
Set Droplet Target
Deploy Droplet
Start Droplet Instance
```

---

## 31. Browser Folder Selection Rule

A local web GUI cannot reliably browse the full local filesystem like a native desktop app.

Phase 1 must use:

```text
text input for source folder
text input for output folder
validation that path exists or is creatable
clear error messages
```

A future desktop wrapper may add native folder pickers.

---

## 32. Start Gating

The GUI must not enable Start when:

```text
state in importing, verifying, starting, stopping, updating, rolling_back, security_blocked
security_status = FAIL_BLOCKING
```

Start may be enabled when:

```text
state in created, ready, stopped, degraded
security_status in PASS, WARN, UNKNOWN
```

If `security_status = UNKNOWN`, clicking Start must run Security Gate first or show a confirmation requiring Security Gate.

---

## 33. Restore / Rollback Gating

These actions require confirmation:

```text
restore_backup
restore_backup_new
rollback_instance
```

Rollback with data restore requires:

```text
backup_id
```

---

## 34. Public Exposure Gating

If:

```text
network_profile = public_temporary
```

then:

```text
target_mode = temporary_public
exposure_mode = temporary_tunnel
public_mode_expires_at is required
explicit confirmation is required
```

If:

```text
network_profile = public_vps
```

then:

```text
target_mode = droplet
exposure_mode = public
droplet_host is required
droplet_user is required
ssh_key_path is required
remote_kx_root is required
remote_capsule_dir is required
domain is required
host must resolve from domain/public_host/droplet_host
explicit confirmation is required
```

The GUI must never allow this drift:

```text
target_mode = intranet
network_profile = public_vps
exposure_mode = public
```

or:

```text
target_mode = droplet
network_profile = intranet_private
exposure_mode = private
```

or:

```text
target_mode = droplet
network_profile = public_vps
exposure_mode = public
KX_HOST = 127.0.0.1
```

---

## 35. Runtime Compose and Traefik Contract

Droplet/public_vps runtime must generate public routing through Traefik file provider.

Traefik static command must enable file provider:

```text
--providers.file.filename=/etc/traefik/dynamic/traefik-dynamic.yml
--providers.file.watch=true
--entrypoints.web.address=:80
--entrypoints.websecure.address=:443
--entrypoints.web.http.redirections.entrypoint.to=websecure
--entrypoints.web.http.redirections.entrypoint.scheme=https
```

Generated dynamic file must route using the public host:

```yaml
http:
  routers:
    kx-frontend:
      rule: "Host(`<public-host>`) && PathPrefix(`/`)"
      entryPoints:
        - websecure
      tls: {}
      service: kx-frontend
      priority: 1

    kx-api:
      rule: "Host(`<public-host>`) && PathPrefix(`/api/`)"
      entryPoints:
        - websecure
      tls: {}
      service: kx-api
      priority: 100

    kx-admin:
      rule: "Host(`<public-host>`) && PathPrefix(`/admin/`)"
      entryPoints:
        - websecure
      tls: {}
      service: kx-api
      priority: 100

  services:
    kx-frontend:
      loadBalancer:
        servers:
          - url: "http://kx-demo-001-frontend-next:3000"

    kx-api:
      loadBalancer:
        servers:
          - url: "http://kx-demo-001-django-api:5000"
```

Traefik Docker labels may exist, but public_vps correctness must not depend only on labels if the runtime is using file provider.

---

## 36. Runtime Healthcheck Contract

Healthchecks must use tools available inside the relevant container.

Django/Gunicorn healthcheck must not require `wget` or `curl`.

Allowed Django healthcheck:

```text
python -c "import socket; sock=socket.create_connection(('127.0.0.1',5000),5); sock.close()"
```

Forbidden malformed healthcheck:

```text
python -c "... sock.close()"api/health/ >/dev/null 2>&1 || exit 1
```

Forbidden unless the image includes the tool:

```text
wget -qO- http://127.0.0.1:5000/api/health/
curl http://127.0.0.1:5000/api/health/
```

Media nginx healthcheck must either use an available tool/path or be disabled for stock `nginx:stable` if no reliable health endpoint/tool exists.

Compose must not block frontend/celery startup because Django is marked unhealthy by a broken healthcheck while Gunicorn is running.

---

## 37. Required Tests

Create or update:

```text
tests/test_manager_ui_contract.py
tests/test_manager_ui_routes.py
tests/test_manager_ui_forms.py
tests/test_manager_ui_action_coverage.py
tests/test_manager_ui_target_modes.py
tests/test_fastapi_ui_page_split.py
tests/test_fastapi_ui_routes.py
tests/test_ui_form_targets.py
tests/test_ui_page_targets.py
tests/test_ui_page_deploy.py
tests/test_network_profiles.py
tests/test_compose_generation.py
tests/test_capsule_verify.py
```

Required checks:

```text
GUI app exposes register(app)
FastAPI UI import does not require Streamlit
All UI page routes start with /ui
All action routes start with /ui/actions
All required labels exist
All form validators reject invalid canonical values
page_views.py is a thin page orchestrator
page_parts/*.py export render(context) -> str
page_parts/*.py do not call html_response(...)
Droplet payload forces target_mode=droplet
Droplet payload forces network_profile=public_vps
Droplet payload forces exposure_mode=public
Droplet target requires host/user/ssh_key/remote_root/remote_capsule_dir/domain
Droplet domain/public_host is normalized to host for Agent network profile
Droplet remote_agent_url blank uses SSH transport
Droplet remote_agent_url loopback uses SSH transport
Targets page does not render deployment action forms
Deploy page renders deployment action forms
Droplet operation buttons do not submit intranet payloads
public_temporary requires expiration
public_vps requires explicit public host
public_vps never defaults KX_HOST to 127.0.0.1
public_vps never defaults Traefik Host() to 127.0.0.1
public_vps generated Django allowed hosts include public host
public_vps generated frontend env points at public host
Django healthcheck does not use missing wget/curl
Django healthcheck is not malformed
Builder capsule includes required app image archives
Verify fails if required app image archives are missing
rollback restore_data requires backup_id
command fallback uses shell=False
unknown action is rejected
all UiAction values are mapped
all mapped actions have buttons or links
browser-only actions are links, not POST routes
```

Run:

```powershell
uv run python -m compileall kx_manager/ui kx_manager/services kx_agent kx_builder tests
uv run pytest -q
```

Current expected full-suite baseline after the GUI/page split and Droplet deploy fixes:

```text
548+ passed
```

The exact number may increase as new Droplet/image/runtime regression tests are added.

---

## 38. Launcher Contract

`start_konnaxion_gui.bat` must set:

```bat
set "KX_MANAGER_REPO=C:\mycode\Konnaxion\Konnaxion_Capsule_Manager"
set "KX_RUNTIME_ROOT=C:\mycode\Konnaxion\runtime"
set "KX_SOURCE_DIR=C:\mycode\Konnaxion\Konnaxion"

set "KX_ROOT=%KX_RUNTIME_ROOT%"
set "KX_AGENT_HOST=127.0.0.1"
set "KX_AGENT_PORT=8765"
set "KX_AGENT_URL=http://127.0.0.1:8765/v1"
set "KX_MANAGER_HOST=127.0.0.1"
set "KX_MANAGER_PORT=8714"
set "KX_MANAGER_URL=http://127.0.0.1:8714"
```

It must open:

```text
http://127.0.0.1:8714/ui
```

---

## 39. Anti-Drift Rules

## 39.1 Imports

Canonical product, profile, exposure, service, state, and default values should come from:

```python
from kx_shared.konnaxion_constants import ...
```

Target-mode logic must come from:

```python
from kx_manager.services.targets import ...
```

UI route, action, label, and alias constants must come from:

```python
from kx_manager.ui.static import ...
```

Page body helpers should come from:

```python
from kx_manager.ui.page_parts.common import ...
```

UI state/view files may import DTOs from:

```python
from kx_manager.models import ...
from kx_manager.schemas import ...
```

UI action execution must call:

```python
from kx_manager.client import KonnaxionAgentClient
```

or a Manager service wrapper that uses this client.

Droplet action execution may use:

```python
from kx_manager.ui.agent_execution_client import ...
```

as the approved HTTP/SCP/SSH execution adapter.

## 39.2 No duplicated canonical enums

Do not hardcode these outside their owner modules:

```text
InstanceState values
NetworkProfile values
ExposureMode values
SecurityGateStatus values
BackupStatus values
RestoreStatus values
RollbackStatus values
DockerService values
UiAction values
PageId values
TargetMode values
```

## 39.3 No unmapped buttons

Every GUI button must resolve to exactly one of:

```text
UiAction
Manager route
KonnaxionAgentClient method
Agent API endpoint
Builder service function
Deploy service function
approved CLI fallback
browser link
```

If a button cannot be traced through that chain, it must not exist.

## 39.4 Page split rule

The page split must remain flat:

```text
page_views.py
  thin orchestrator only

page_parts/*.py
  page body builders only

page_parts/common.py
  shared form/button/payload helpers

page_parts/targets.py
  target configuration forms only

page_parts/deploy.py
  deployment operation forms only

form_targets.py
  POST validation and target/deploy normalization

static.py
  route/action/alias constants
```

Targets/deploy split invariant:

```text
/ui/targets must not render Deploy Local, Deploy Intranet, Deploy Droplet,
Check Droplet Agent, Copy Capsule to Droplet, or Start Droplet Instance forms.

/ui/deploy must render those deployment forms and must reuse the same canonical
payload helpers used by target validation.
```

Do not add `kx_manager/ui/pages/` because `kx_manager/ui/pages.py` already exists.

## 39.5 Droplet anti-drift rules

Never allow these generated runtime states for `public_vps`:

```text
KX_HOST=127.0.0.1
Traefik Host(`127.0.0.1`)
DJANGO_ALLOWED_HOSTS=127.0.0.1 only
NEXT_PUBLIC_API_BASE=https://127.0.0.1/api
NEXT_PUBLIC_BACKEND_BASE=https://127.0.0.1
frontend runtime command that downloads pnpm
capsule with images/README.json only
Docker image where source files are overwritten by migration files
Django healthcheck using unavailable wget/curl
```

---

## 40. Done Definition

The GUI technical contract is satisfied when:

```text
A user can open http://127.0.0.1:8714/ui,
select the Konnaxion source folder,
select the capsule output folder,
build a .kxcap,
verify it,
import it,
create or update an instance,
set local/intranet/droplet target,
deploy local/intranet/droplet from /ui/deploy,
start it,
view status/health/logs/security,
create backups,
restore or rollback when needed,
without typing CLI commands.
```

Droplet/public_vps done condition:

```text
Droplet Agent remains private on 127.0.0.1:8765.
Manager reaches Droplet Agent through SSH-local curl.
No temporary tunnel is required.
Capsule includes required app image archives.
Runtime images load on the Droplet.
Generated env uses public host.
Generated Traefik routes use public host.
Frontend returns HTTP 200 at https://<public-host>.
Django is reachable through Traefik.
Django is healthy.
Postgres and Redis are healthy.
Celery worker and beat run.
No internal app/db/cache ports are publicly exposed.
```

Production-safe condition:

```text
All privileged actions go through Manager/Agent APIs or approved service wrappers.
No arbitrary shell execution exists.
No public exposure is allowed without explicit confirmation.
Temporary public mode requires expiration.
Security Gate failures block startup.
All UI routes remain local-only by default.
Full pytest passes.
```

```
```
