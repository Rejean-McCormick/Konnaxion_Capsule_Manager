doc_id: DOC-17
title: Konnaxion GUI Action Coverage Contract
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: technical-contract
owner: Konnaxion
last_updated: 2026-05-01
depends_on:
  - DOC-16_Konnaxion_Manager_GUI_Technical_Contract.md
  - DOC-17A_Konnaxion_GUI_Action_Payload_Contract.md
  - DOC-17B_Konnaxion_GUI_Action_UI_Test_Contract.md
  - DOC-18_Konnaxion_GUI_Target_Modes.md
---

# DOC-17 — Konnaxion GUI Action Coverage Contract

## 1. Purpose

This document defines the complete GUI action coverage contract for the Konnaxion Capsule Manager.

It exists to prevent drift between:

```text
kx_manager/ui/pages.py
kx_manager/ui/app.py
kx_manager/ui/actions.py
kx_manager/ui/action_models.py
kx_manager/ui/action_constants.py
kx_manager/ui/action_helpers.py
kx_manager/ui/action_backends.py
kx_manager/ui/action_dispatch.py
kx_manager/ui/forms.py
kx_manager/ui/form_targets.py
kx_manager/ui/form_registry.py
kx_manager/ui/static.py
kx_manager/ui/page_views.py
kx_manager/ui/page_forms.py
kx_manager/ui/page_parts/*
kx_manager/ui/action_views.py
kx_manager/ui/render.py
kx_manager/ui/state.py
kx_manager/ui/components.py
kx_manager/client.py
kx_manager/services/builder.py
kx_manager/services/targets.py
kx_manager/services/deploy.py
kx_manager/routes/*
kx_agent/api.py
kx_cli/*
kx_builder/*
tests/test_manager_ui_contract.py
tests/test_manager_ui_action_coverage.py
tests/test_manager_ui_routes.py
tests/test_manager_ui_forms.py
tests/test_fastapi_ui_page_split.py
tests/test_manager_ui_target_modes.py
tests/test_ui_form_targets.py
tests/test_ui_page_targets.py
tests/test_ui_page_deploy.py
````

Every GUI button must map to a known action.

Every action must map to one of:

```text
Manager route
Manager service wrapper
KonnaxionAgentClient method
Agent API endpoint
Builder operation
Deploy operation
approved CLI fallback
browser link
```

If a GUI button cannot be traced through this contract, it must not exist.

Payload shape, alias normalization, Droplet action normalization, and normalized result shape live in:

```text
DOC-17A_Konnaxion_GUI_Action_Payload_Contract.md
```

UI button placement, safety gating, labels, tests, and acceptance criteria live in:

```text
DOC-17B_Konnaxion_GUI_Action_UI_Test_Contract.md
```

---

## 2. Coverage Rule

The GUI must cover the complete operator workflow:

```text
check services
select Konnaxion source folder
select capsule output folder
build capsule
rebuild capsule
verify capsule
import capsule
inspect capsules
create instance
update instance
start instance
stop instance
restart instance
inspect status
inspect logs
inspect health
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
set local target
set intranet target
set temporary public target
set Droplet target
deploy local
deploy intranet
bootstrap Droplet Agent
check Droplet Agent
copy capsule to Droplet
deploy Droplet
start Droplet instance
open docs
open runtime
```

The GUI must not be a visual-only scaffold.

It must be usable instead of normal operator commands for the supported workflow.

Droplet deployment has a first-time bootstrap prerequisite:

```text
If the target Droplet does not already have Konnaxion Agent installed and running,
the GUI must offer bootstrap_droplet_agent before check_droplet_agent.
```

---

## 3. Canonical GUI Action Names

`kx_manager/ui/pages.py` owns GUI action identity.

Replace or align `UiAction` with the following complete action set:

```python
class UiAction(StrEnum):
    CHECK_MANAGER = "check_manager"
    CHECK_AGENT = "check_agent"

    SELECT_SOURCE_FOLDER = "select_source_folder"
    SELECT_CAPSULE_OUTPUT_FOLDER = "select_capsule_output_folder"

    BUILD_CAPSULE = "build_capsule"
    REBUILD_CAPSULE = "rebuild_capsule"
    VERIFY_CAPSULE = "verify_capsule"
    IMPORT_CAPSULE = "import_capsule"
    LIST_CAPSULES = "list_capsules"
    VIEW_CAPSULE = "view_capsule"

    CREATE_INSTANCE = "create_instance"
    UPDATE_INSTANCE = "update_instance"
    START_INSTANCE = "start_instance"
    STOP_INSTANCE = "stop_instance"
    RESTART_INSTANCE = "restart_instance"
    INSTANCE_STATUS = "instance_status"
    VIEW_LOGS = "view_logs"
    VIEW_HEALTH = "view_health"
    OPEN_INSTANCE = "open_instance"
    ROLLBACK_INSTANCE = "rollback_instance"

    CREATE_BACKUP = "create_backup"
    LIST_BACKUPS = "list_backups"
    VERIFY_BACKUP = "verify_backup"
    RESTORE_BACKUP = "restore_backup"
    RESTORE_BACKUP_NEW = "restore_backup_new"
    TEST_RESTORE_BACKUP = "test_restore_backup"

    RUN_SECURITY_CHECK = "run_security_check"

    SET_NETWORK_PROFILE = "set_network_profile"
    DISABLE_PUBLIC_MODE = "disable_public_mode"

    SET_TARGET_LOCAL = "set_target_local"
    SET_TARGET_INTRANET = "set_target_intranet"
    SET_TARGET_DROPLET = "set_target_droplet"
    SET_TARGET_TEMPORARY_PUBLIC = "set_target_temporary_public"

    DEPLOY_LOCAL = "deploy_local"
    DEPLOY_INTRANET = "deploy_intranet"
    DEPLOY_DROPLET = "deploy_droplet"

    BOOTSTRAP_DROPLET_AGENT = "bootstrap_droplet_agent"
    CHECK_DROPLET_AGENT = "check_droplet_agent"
    COPY_CAPSULE_TO_DROPLET = "copy_capsule_to_droplet"
    START_DROPLET_INSTANCE = "start_droplet_instance"

    OPEN_MANAGER_DOCS = "open_manager_docs"
    OPEN_AGENT_DOCS = "open_agent_docs"
```

Required GUI action count:

```text
42
```

Required non-browser POST action count:

```text
39
```

Required browser-only action count:

```text
3
```

Browser-only actions:

```text
open_instance
open_manager_docs
open_agent_docs
```

---

## 4. Action Coverage Matrix

| GUI Action                     | Required | Primary Backend            | Agent Endpoint                      | CLI / External Fallback                              |
| ------------------------------ | -------: | -------------------------- | ----------------------------------- | ---------------------------------------------------- |
| `check_manager`                |      yes | Manager health route       | none                                | HTTP GET `/health`                                   |
| `check_agent`                  |      yes | Manager client health call | `GET /v1/health`                    | HTTP GET Agent health                                |
| `select_source_folder`         |      yes | UI form value              | none                                | text input validation                                |
| `select_capsule_output_folder` |      yes | UI form value              | none                                | text input validation                                |
| `build_capsule`                |      yes | Builder service            | none                                | `uv run kx-builder capsule build ...`                |
| `rebuild_capsule`              |      yes | Builder service            | none                                | remove old + build                                   |
| `verify_capsule`               |      yes | Builder or Agent verify    | `POST /v1/capsules/verify`          | `uv run kx-builder capsule verify <capsule>`         |
| `import_capsule`               |      yes | Manager client             | `POST /v1/capsules/import`          | `uv run kx capsule import <capsule>`                 |
| `list_capsules`                |      yes | Manager capsule route      | none                                | `uv run kx capsule list` if available                |
| `view_capsule`                 |      yes | Manager capsule route      | none                                | `uv run kx capsule status <capsule>` if available    |
| `create_instance`              |      yes | Manager client             | `POST /v1/instances/create`         | `uv run kx instance create <instance>`               |
| `update_instance`              |      yes | Manager client             | `POST /v1/instances/update`         | `uv run kx instance update <instance>`               |
| `start_instance`               |      yes | Manager client             | `POST /v1/instances/start`          | `uv run kx instance start <instance>`                |
| `stop_instance`                |      yes | Manager client             | `POST /v1/instances/stop`           | `uv run kx instance stop <instance>`                 |
| `restart_instance`             |      yes | composed action            | stop + start                        | stop then start                                      |
| `instance_status`              |      yes | Manager client             | `POST /v1/instances/status`         | `uv run kx instance status <instance>`               |
| `view_logs`                    |      yes | Manager client             | `POST /v1/instances/logs`           | `uv run kx instance logs <instance>`                 |
| `view_health`                  |      yes | Manager client             | `POST /v1/instances/health`         | `uv run kx instance health <instance>`               |
| `open_instance`                |      yes | browser link               | none                                | open runtime URL                                     |
| `rollback_instance`            |      yes | Manager client             | `POST /v1/instances/rollback`       | `uv run kx instance rollback <instance>`             |
| `create_backup`                |      yes | Manager client             | `POST /v1/instances/backup`         | `uv run kx instance backup <instance>`               |
| `list_backups`                 |      yes | Manager backup route       | none                                | `uv run kx backup list`                              |
| `verify_backup`                |      yes | Manager backup route       | none                                | `uv run kx backup verify <backup>`                   |
| `restore_backup`               |      yes | Manager client             | `POST /v1/instances/restore`        | `uv run kx instance restore <instance>`              |
| `restore_backup_new`           |      yes | Manager client             | `POST /v1/instances/restore-new`    | `uv run kx instance restore-new ...`                 |
| `test_restore_backup`          |      yes | Manager backup route       | none                                | `uv run kx backup test-restore <backup>`             |
| `run_security_check`           |      yes | Manager client             | `POST /v1/security/check`           | `uv run kx security check <instance>`                |
| `set_network_profile`          |      yes | Manager client             | `POST /v1/network/set-profile`      | `uv run kx network set-profile <instance> <profile>` |
| `disable_public_mode`          |      yes | Manager client             | `POST /v1/network/set-profile`      | set private/intranet profile                         |
| `set_target_local`             |      yes | Target service             | none                                | local config write                                   |
| `set_target_intranet`          |      yes | Target service             | none                                | intranet config write                                |
| `set_target_droplet`           |      yes | Target service             | none                                | Droplet config write                                 |
| `set_target_temporary_public`  |      yes | Target service             | none                                | temporary public config write                        |
| `deploy_local`                 |      yes | Deploy service             | Manager/Agent sequence              | approved CLI sequence                                |
| `deploy_intranet`              |      yes | Deploy service             | Manager/Agent sequence              | approved CLI sequence                                |
| `deploy_droplet`               |      yes | Deploy service             | remote Agent / approved remote path | `scp`/SFTP + approved remote operation               |
| `bootstrap_droplet_agent`      |      yes | Deploy service             | none before bootstrap               | approved SSH/SCP bootstrap only                      |
| `check_droplet_agent`          |      yes | Deploy service             | remote Agent health                 | SSH-local health check or HTTP health check          |
| `copy_capsule_to_droplet`      |      yes | Deploy service             | none                                | `scp` or SFTP library                                |
| `start_droplet_instance`       |      yes | Deploy service             | remote Agent start                  | remote approved operation                            |
| `open_manager_docs`            |      yes | browser link               | none                                | open Manager `/docs`                                 |
| `open_agent_docs`              |      yes | browser link               | none                                | open Agent `/docs`                                   |

---

## 5. Backend Priority

Each GUI action must use the strongest available backend in this order:

```text
1. Manager API / service call
2. KonnaxionAgentClient method
3. Agent API endpoint
4. Builder Python API
5. Deploy service / target service
6. Approved CLI fallback
7. Browser link
```

CLI fallback is allowed only as a temporary bridge.

CLI fallback rules:

```text
shell=False
fixed command executable
fixed subcommand list
validated user input only
no arbitrary shell text
no arbitrary Docker command
no arbitrary service name
no arbitrary host path except approved source/capsule/runtime paths
stdout captured
stderr captured
returncode captured
result normalized
```

Remote fallback rules for Droplet:

```text
no password in command string
SSH key path must be validated
remote host must be explicit
remote user must be explicit
remote root must be explicit
remote capsule directory must be under remote root
remote command must be allowlisted
capsule copy target must be remote capsule directory
no arbitrary remote command text
no shell=True with untrusted input
```

Bootstrap fallback rules for Droplet:

```text
bootstrap_droplet_agent must require explicit Droplet confirmation
bootstrap_droplet_agent must use the configured droplet_host
bootstrap_droplet_agent must use the configured droplet_user
bootstrap_droplet_agent must use the configured ssh_key_path
bootstrap_droplet_agent must use the configured ssh_port
bootstrap_droplet_agent must use the configured remote_kx_root
bootstrap_droplet_agent must create only approved Konnaxion runtime directories
bootstrap_droplet_agent must install/start only the Konnaxion Agent service
bootstrap_droplet_agent must bind the Agent to 127.0.0.1:8765 by default
bootstrap_droplet_agent must not expose Agent port 8765 publicly
bootstrap_droplet_agent must verify Agent health through SSH-local loopback
bootstrap_droplet_agent must return stdout, stderr, returncode, and normalized result data
```

---

## 6. Required FastAPI GUI Routes

`kx_manager/ui/app.py` must expose:

```python
def register(app: FastAPI) -> Any:
    ...
```

The function must register all routes below.

---

## 6.1 Page routes

| Method | Route           | Purpose                                     |
| ------ | --------------- | ------------------------------------------- |
| `GET`  | `/ui`           | Dashboard                                   |
| `GET`  | `/ui/capsules`  | Capsule operations                          |
| `GET`  | `/ui/instances` | Instance operations                         |
| `GET`  | `/ui/security`  | Security Gate                               |
| `GET`  | `/ui/network`   | Network profiles                            |
| `GET`  | `/ui/backups`   | Backup operations                           |
| `GET`  | `/ui/restore`   | Restore/rollback                            |
| `GET`  | `/ui/logs`      | Logs                                        |
| `GET`  | `/ui/health`    | Health                                      |
| `GET`  | `/ui/settings`  | Settings                                    |
| `GET`  | `/ui/targets`   | Local/intranet/public/Droplet target config |
| `GET`  | `/ui/deploy`    | Local/intranet/Droplet deployment actions   |
| `GET`  | `/ui/about`     | Product/about page                          |

---

## 6.2 Action routes

| Method | Route                                      | GUI Action                     |
| ------ | ------------------------------------------ | ------------------------------ |
| `POST` | `/ui/actions/check-manager`                | `check_manager`                |
| `POST` | `/ui/actions/check-agent`                  | `check_agent`                  |
| `POST` | `/ui/actions/select-source-folder`         | `select_source_folder`         |
| `POST` | `/ui/actions/select-capsule-output-folder` | `select_capsule_output_folder` |
| `POST` | `/ui/actions/build-capsule`                | `build_capsule`                |
| `POST` | `/ui/actions/rebuild-capsule`              | `rebuild_capsule`              |
| `POST` | `/ui/actions/verify-capsule`               | `verify_capsule`               |
| `POST` | `/ui/actions/import-capsule`               | `import_capsule`               |
| `POST` | `/ui/actions/list-capsules`                | `list_capsules`                |
| `POST` | `/ui/actions/view-capsule`                 | `view_capsule`                 |
| `POST` | `/ui/actions/create-instance`              | `create_instance`              |
| `POST` | `/ui/actions/update-instance`              | `update_instance`              |
| `POST` | `/ui/actions/start-instance`               | `start_instance`               |
| `POST` | `/ui/actions/stop-instance`                | `stop_instance`                |
| `POST` | `/ui/actions/restart-instance`             | `restart_instance`             |
| `POST` | `/ui/actions/instance-status`              | `instance_status`              |
| `POST` | `/ui/actions/view-logs`                    | `view_logs`                    |
| `POST` | `/ui/actions/view-health`                  | `view_health`                  |
| `POST` | `/ui/actions/rollback-instance`            | `rollback_instance`            |
| `POST` | `/ui/actions/create-backup`                | `create_backup`                |
| `POST` | `/ui/actions/list-backups`                 | `list_backups`                 |
| `POST` | `/ui/actions/verify-backup`                | `verify_backup`                |
| `POST` | `/ui/actions/restore-backup`               | `restore_backup`               |
| `POST` | `/ui/actions/restore-backup-new`           | `restore_backup_new`           |
| `POST` | `/ui/actions/test-restore-backup`          | `test_restore_backup`          |
| `POST` | `/ui/actions/run-security-check`           | `run_security_check`           |
| `POST` | `/ui/actions/set-network-profile`          | `set_network_profile`          |
| `POST` | `/ui/actions/disable-public-mode`          | `disable_public_mode`          |
| `POST` | `/ui/actions/set-target-local`             | `set_target_local`             |
| `POST` | `/ui/actions/set-target-intranet`          | `set_target_intranet`          |
| `POST` | `/ui/actions/set-target-droplet`           | `set_target_droplet`           |
| `POST` | `/ui/actions/set-target-temporary-public`  | `set_target_temporary_public`  |
| `POST` | `/ui/actions/deploy-local`                 | `deploy_local`                 |
| `POST` | `/ui/actions/deploy-intranet`              | `deploy_intranet`              |
| `POST` | `/ui/actions/deploy-droplet`               | `deploy_droplet`               |
| `POST` | `/ui/actions/bootstrap-droplet-agent`      | `bootstrap_droplet_agent`      |
| `POST` | `/ui/actions/check-droplet-agent`          | `check_droplet_agent`          |
| `POST` | `/ui/actions/copy-capsule-to-droplet`      | `copy_capsule_to_droplet`      |
| `POST` | `/ui/actions/start-droplet-instance`       | `start_droplet_instance`       |

Browser-only actions:

| GUI Action          | Route / URL source                                    |
| ------------------- | ----------------------------------------------------- |
| `open_instance`     | Runtime URL from payload/result                       |
| `open_manager_docs` | Manager `/docs`                                       |
| `open_agent_docs`   | Agent docs URL, normally `http://127.0.0.1:8765/docs` |

Browser-only actions must not register POST `/ui/actions/...` routes.

---

## 6.3 Page/action ownership

Target selection and deployment execution must be separated.

`/ui/targets` owns only target configuration forms:

```text
set_target_local
set_target_intranet
set_target_droplet
set_target_temporary_public
```

`/ui/deploy` owns deployment and Droplet operation forms:

```text
deploy_local
deploy_intranet
deploy_droplet
bootstrap_droplet_agent
check_droplet_agent
copy_capsule_to_droplet
start_droplet_instance
```

The POST action routes do not change. Deployment actions still submit to canonical `/ui/actions/...` routes.

`/ui/targets` must not render the deployment action grid.

`/ui/deploy` may reuse the same canonical payload helpers as `/ui/targets`, but it must preserve these invariants:

```text
local deployment submits target_mode=local
intranet deployment submits target_mode=intranet
Droplet deployment submits target_mode=droplet
Droplet deployment submits network_profile=public_vps
Droplet deployment submits exposure_mode=public
Droplet deployment submits confirmed=true
Droplet deployment requires domain
Droplet domain is not silently invented from droplet_host
bootstrap_droplet_agent does not require or submit capsule_file
check_droplet_agent does not require or submit capsule_file
```

Droplet operation order on `/ui/deploy` must be:

```text
1. Bootstrap Droplet Agent
2. Check Droplet Agent
3. Copy Capsule to Droplet
4. Deploy Droplet
5. Start Droplet Instance
```

`Start Droplet Instance` is a recovery/follow-up action and is not the primary first-time deployment path.

---

## 7. Required Agent Endpoints

Agent API base:

```text
http://127.0.0.1:8765/v1
```

| Method | Path                     | Action                                       |
| ------ | ------------------------ | -------------------------------------------- |
| `GET`  | `/health`                | `check_agent`                                |
| `GET`  | `/agent/info`            | Agent metadata                               |
| `POST` | `/capsules/import`       | `import_capsule`                             |
| `POST` | `/capsules/verify`       | `verify_capsule`                             |
| `POST` | `/instances/create`      | `create_instance`                            |
| `POST` | `/instances/start`       | `start_instance`                             |
| `POST` | `/instances/stop`        | `stop_instance`                              |
| `POST` | `/instances/status`      | `instance_status`                            |
| `POST` | `/instances/logs`        | `view_logs`                                  |
| `POST` | `/instances/backup`      | `create_backup`                              |
| `POST` | `/instances/restore`     | `restore_backup`                             |
| `POST` | `/instances/restore-new` | `restore_backup_new`                         |
| `POST` | `/instances/update`      | `update_instance`                            |
| `POST` | `/instances/rollback`    | `rollback_instance`                          |
| `POST` | `/instances/health`      | `view_health`                                |
| `POST` | `/security/check`        | `run_security_check`                         |
| `POST` | `/network/set-profile`   | `set_network_profile`, `disable_public_mode` |

Remote Droplet Agent endpoints use the same API path with the remote Agent base URL after the remote Agent has been bootstrapped.

`bootstrap_droplet_agent` is a pre-Agent operation. It must not require a working remote Agent endpoint before it runs.

---

## 8. Required Client Methods

`kx_manager/client.py` must expose or keep equivalent methods:

```text
health()
agent_info()

import_capsule()
verify_capsule()

create_instance()
start_instance()
stop_instance()
instance_status()
instance_logs()
backup_instance()
restore_instance()
restore_new_instance()
update_instance()
rollback_instance()
instance_health()

security_check()
set_network_profile()
```

Additional Manager-local methods or service wrappers required by GUI:

```text
build_capsule()
rebuild_capsule()
list_capsules()
view_capsule()
list_backups()
verify_backup()
test_restore_backup()
restart_instance()
disable_public_mode()
select_source_folder()
select_capsule_output_folder()
set_target_local()
set_target_intranet()
set_target_droplet()
set_target_temporary_public()
deploy_local()
deploy_intranet()
deploy_droplet()
bootstrap_droplet_agent()
check_droplet_agent()
copy_capsule_to_droplet()
start_droplet_instance()
```

If these are not part of `KonnaxionAgentClient`, they must be implemented as Manager-local services or route helpers.

`bootstrap_droplet_agent()` must be implemented as a Manager-local deploy service/helper because it runs before the remote Agent exists.

---

## 9. Companion Contracts

Payload and normalization rules:

```text
DOC-17A_Konnaxion_GUI_Action_Payload_Contract.md
```

UI button coverage, safety rules, labels, tests, and acceptance:

```text
DOC-17B_Konnaxion_GUI_Action_UI_Test_Contract.md
```

---

## 10. Final Rule

Every GUI action must be traceable through this chain:

```text
button/label
  -> UiAction
  -> form model
  -> action route or browser link
  -> action dispatcher
  -> Manager service / client / route
  -> Agent endpoint / Builder service / Deploy service / CLI fallback
  -> normalized GuiActionResult
  -> rendered result panel
```

If any link in that chain is missing, the action is incomplete.

Droplet actions have one extra invariant:

```text
button/form
  -> Droplet payload builder
  -> target_mode=droplet
  -> network_profile=public_vps
  -> exposure_mode=public
  -> confirmed=true
  -> required Droplet fields
  -> validated action payload
  -> dispatch
```

Droplet actions must never inherit the private/intranet default payload.

Droplet bootstrap has one extra invariant:

```text
button/form
  -> bootstrap_droplet_agent
  -> target_mode=droplet
  -> network_profile=public_vps
  -> exposure_mode=public
  -> confirmed=true
  -> required Droplet SSH fields
  -> no capsule_file required
  -> SSH/SCP allowlisted bootstrap
  -> install/start Konnaxion Agent on 127.0.0.1:8765
  -> verify remote Agent health through SSH-local loopback
  -> normalized GuiActionResult
```

`bootstrap_droplet_agent` must not open the Agent API publicly.


