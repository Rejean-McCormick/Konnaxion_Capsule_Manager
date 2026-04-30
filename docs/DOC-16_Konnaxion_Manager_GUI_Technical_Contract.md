doc_id: DOC-16
title: Konnaxion Capsule Manager GUI Technical Contract
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: technical-contract
owner: Konnaxion
last_updated: 2026-04-30
---

# DOC-16 — Konnaxion Capsule Manager GUI Technical Contract

## 1. Purpose

This document defines the fixed technical contract for the Konnaxion Capsule Manager GUI.

It aligns the frontend/UI files with the Manager, Agent, Builder, CLI, shared constants, and tests.

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
target local/intranet/droplet deployment
````

The GUI must not invent names, states, profiles, routes, actions, service names, or runtime variables.

Friendly labels are allowed for display only. Stored and exchanged values must remain canonical.

---

## 2. Runtime Topology

## 2.1 Local services

| Service           | Default URL                   | Purpose                                          |
| ----------------- | ----------------------------- | ------------------------------------------------ |
| Manager GUI/API   | `http://127.0.0.1:8714`       | Browser UI and Manager API                       |
| Agent API         | `http://127.0.0.1:8765/v1`    | Privileged local runtime actions                 |
| Konnaxion runtime | `C:\mycode\Konnaxion\runtime` | Local capsules, instances, backups, shared state |

## 2.2 Control flow

```text
Browser GUI
  -> kx_manager UI route/action
  -> kx_manager client or Manager route
  -> kx_agent API
  -> kx_agent action/runtime module
  -> Docker/filesystem/backup/network operation
```

The Manager GUI must not directly control Docker, firewall rules, host services, host networking, or backups except through approved Manager service wrappers or Agent calls.

---

## 3. Source File Ownership

## 3.1 Existing UI files

| File                          | Responsibility                                      |
| ----------------------------- | --------------------------------------------------- |
| `kx_manager/ui/__init__.py`   | UI package declaration                              |
| `kx_manager/ui/app.py`        | Actual FastAPI `/ui` GUI entrypoint                 |
| `kx_manager/ui/pages.py`      | Page IDs, page routes, UI action IDs, page metadata |
| `kx_manager/ui/state.py`      | Canonical UI display state and normalization        |
| `kx_manager/ui/components.py` | Safe reusable UI rendering helpers                  |

## 3.2 New UI files

| File                             | Responsibility                         |
| -------------------------------- | -------------------------------------- |
| `kx_manager/ui/actions.py`       | GUI action dispatcher                  |
| `kx_manager/ui/forms.py`         | Form parsing and validation            |
| `kx_manager/ui/render.py`        | Shared FastAPI HTML rendering helpers  |
| `kx_manager/ui/streamlit_app.py` | Optional preserved Streamlit prototype |

## 3.3 New Manager service files

| File                             | Responsibility                              |
| -------------------------------- | ------------------------------------------- |
| `kx_manager/services/builder.py` | Build/verify capsule service wrapper        |
| `kx_manager/services/targets.py` | Local/intranet/droplet target configuration |
| `kx_manager/services/deploy.py`  | Local/intranet/droplet deployment flow      |

## 3.4 Backend alignment files

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

---

## 4. Required UI Package Structure

The target UI package must be:

```text
kx_manager/ui/
  __init__.py
  app.py
  actions.py
  forms.py
  render.py
  pages.py
  state.py
  components.py
  streamlit_app.py
```

Rules:

```text
app.py must be FastAPI-compatible.
app.py must expose register(app).
app.py must not require Streamlit.
streamlit_app.py may require Streamlit.
pages.py owns UI page IDs and action names.
state.py owns normalized UI state.
components.py owns reusable rendering helpers.
actions.py owns GUI action dispatch.
forms.py owns input validation.
render.py owns shared HTML layout/rendering.
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

| Variable                 | Example                                     |    Required |
| ------------------------ | ------------------------------------------- | ----------: |
| `KX_DROPLET_NAME`        | `konnaxion-prod-01`                         |         yes |
| `KX_DROPLET_HOST`        | `203.0.113.10`                              |         yes |
| `KX_DROPLET_USER`        | `root`                                      |         yes |
| `KX_DROPLET_SSH_KEY`     | `C:\Users\user\.ssh\id_ed25519`             |         yes |
| `KX_DROPLET_KX_ROOT`     | `/opt/konnaxion`                            |         yes |
| `KX_DROPLET_AGENT_URL`   | `http://203.0.113.10:8765/v1` or tunnel URL |    optional |
| `KX_DROPLET_DOMAIN`      | `app.example.com`                           | recommended |
| `KX_DROPLET_CAPSULE_DIR` | `/opt/konnaxion/capsules`                   |         yes |

Droplet mode must not assume password SSH. Use SSH key path or an explicit configured credential mechanism.

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
public_vps requires explicit confirmation
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

| Page            | `PageId` value    | Route                  |
| --------------- | ----------------- | ---------------------- |
| Dashboard       | `dashboard`       | `/ui`                  |
| Capsules        | `capsules`        | `/ui/capsules`         |
| Capsule Import  | `capsule_import`  | `/ui/capsules/import`  |
| Instances       | `instances`       | `/ui/instances`        |
| Instance Detail | `instance_detail` | `/ui/instances/detail` |
| Instance Create | `instance_create` | `/ui/instances/create` |
| Security        | `security`        | `/ui/security`         |
| Network         | `network`         | `/ui/network`          |
| Backups         | `backups`         | `/ui/backups`          |
| Restore         | `restore`         | `/ui/restore`          |
| Logs            | `logs`            | `/ui/logs`             |
| Health          | `health`          | `/ui/health`           |
| Settings        | `settings`        | `/ui/settings`         |
| About           | `about`           | `/ui/about`            |
| Targets         | `targets`         | `/ui/targets`          |

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
| `deployment` | targets                               |

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

`kx_manager/ui/forms.py` must validate form data.

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
DropletTargetForm
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
public_temporary requires expiration
droplet mode requires host, user, ssh key, remote root
restore_data rollback requires backup_id
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
contact remote Agent or run approved remote bootstrap
import/update/start on remote target
run remote health/security checks
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

---

## 30. Required UI Labels

Use these exact main nav labels:

```text
Dashboard
Capsules
Instances
Targets
Security
Network
Backups
Logs
Settings
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
Deploy Local
Deploy Intranet
Deploy Droplet
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
Deploy Droplet Public
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
exposure_mode = temporary_tunnel
public_mode_expires_at is required
```

If:

```text
network_profile = public_vps
```

then:

```text
exposure_mode = public
explicit confirmation is required
domain or host must be configured
```

---

## 35. Required Tests

Create or update:

```text
tests/test_manager_ui_contract.py
tests/test_manager_ui_routes.py
tests/test_manager_ui_forms.py
tests/test_manager_ui_action_coverage.py
```

Required checks:

```text
GUI app exposes register(app)
FastAPI UI import does not require Streamlit
All UI page routes start with /ui
All action routes start with /ui/actions
All required labels exist
All form validators reject invalid canonical values
Droplet target requires host/user/ssh_key/remote_root
public_temporary requires expiration
rollback restore_data requires backup_id
command fallback uses shell=False
unknown action is rejected
all UiAction values are mapped
all mapped actions have buttons or links
```

Run:

```powershell
uv run python -m compileall kx_manager/ui kx_manager/services tests
uv run pytest -q
```

Baseline before GUI work:

```text
331 passed, 8 skipped, 1 warning
```

---

## 36. Launcher Contract

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

## 37. Anti-Drift Rules

## 37.1 Imports

UI files must import canonical values from:

```python
from kx_shared.konnaxion_constants import ...
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

## 37.2 No duplicated canonical enums

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

## 37.3 No unmapped buttons

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

---

## 38. Done Definition

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
start it,
view status/health/logs/security,
create backups,
restore or rollback when needed,
without typing CLI commands.
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


