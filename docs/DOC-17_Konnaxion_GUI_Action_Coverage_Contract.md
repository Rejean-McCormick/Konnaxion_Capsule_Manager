doc_id: DOC-17
title: Konnaxion Capsule Manager GUI Action Coverage Contract
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: technical-contract
owner: Konnaxion
last_updated: 2026-04-30
depends_on:
  - DOC-16_Konnaxion_Manager_GUI_Technical_Contract.md
---

# DOC-17 — Konnaxion Capsule Manager GUI Action Coverage Contract

## 1. Purpose

This document defines the complete GUI action coverage contract for the Konnaxion Capsule Manager.

It exists to prevent drift between:

```text
kx_manager/ui/pages.py
kx_manager/ui/app.py
kx_manager/ui/actions.py
kx_manager/ui/forms.py
kx_manager/ui/state.py
kx_manager/ui/components.py
kx_manager/ui/render.py
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

---

## 2. Coverage Rule

The GUI must cover the complete operator workflow:

```text
check services
select Konnaxion source folder
select capsule output folder
build capsule
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
deploy local
deploy intranet
deploy droplet
open docs
open runtime
```

The GUI must not be a visual-only scaffold.

It must be usable instead of normal operator commands for the supported workflow.

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
    SET_TARGET_INTRAnET = "set_target_intranet"
    SET_TARGET_DROPLET = "set_target_droplet"
    SET_TARGET_TEMPORARY_PUBLIC = "set_target_temporary_public"

    DEPLOY_LOCAL = "deploy_local"
    DEPLOY_INTRAnET = "deploy_intranet"
    DEPLOY_DROPLET = "deploy_droplet"

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

---

## 4. Action Coverage Matrix

| GUI Action                     | Required | Primary Backend            | Agent Endpoint                   | CLI / External Fallback                              |
| ------------------------------ | -------: | -------------------------- | -------------------------------- | ---------------------------------------------------- |
| `check_manager`                |      yes | Manager health route       | none                             | HTTP GET `/health`                                   |
| `check_agent`                  |      yes | Manager client health call | `GET /v1/health`                 | HTTP GET Agent health                                |
| `select_source_folder`         |      yes | UI form value              | none                             | text input validation                                |
| `select_capsule_output_folder` |      yes | UI form value              | none                             | text input validation                                |
| `build_capsule`                |      yes | Builder service            | none                             | `uv run kx-builder capsule build ...`                |
| `rebuild_capsule`              |      yes | Builder service            | none                             | remove old + build                                   |
| `verify_capsule`               |      yes | Builder or Agent verify    | `POST /v1/capsules/verify`       | `uv run kx-builder capsule verify <capsule>`         |
| `import_capsule`               |      yes | Manager client             | `POST /v1/capsules/import`       | `uv run kx capsule import <capsule>`                 |
| `list_capsules`                |      yes | Manager capsule route      | none                             | `uv run kx capsule list` if available                |
| `view_capsule`                 |      yes | Manager capsule route      | none                             | `uv run kx capsule status <capsule>` if available    |
| `create_instance`              |      yes | Manager client             | `POST /v1/instances/create`      | `uv run kx instance create <instance>`               |
| `update_instance`              |      yes | Manager client             | `POST /v1/instances/update`      | `uv run kx instance update <instance>`               |
| `start_instance`               |      yes | Manager client             | `POST /v1/instances/start`       | `uv run kx instance start <instance>`                |
| `stop_instance`                |      yes | Manager client             | `POST /v1/instances/stop`        | `uv run kx instance stop <instance>`                 |
| `restart_instance`             |      yes | composed action            | stop + start                     | stop then start                                      |
| `instance_status`              |      yes | Manager client             | `POST /v1/instances/status`      | `uv run kx instance status <instance>`               |
| `view_logs`                    |      yes | Manager client             | `POST /v1/instances/logs`        | `uv run kx instance logs <instance>`                 |
| `view_health`                  |      yes | Manager client             | `POST /v1/instances/health`      | `uv run kx instance health <instance>`               |
| `open_instance`                |      yes | browser link               | none                             | open runtime URL                                     |
| `rollback_instance`            |      yes | Manager client             | `POST /v1/instances/rollback`    | `uv run kx instance rollback <instance>`             |
| `create_backup`                |      yes | Manager client             | `POST /v1/instances/backup`      | `uv run kx instance backup <instance>`               |
| `list_backups`                 |      yes | Manager backup route       | none                             | `uv run kx backup list`                              |
| `verify_backup`                |      yes | Manager backup route       | none                             | `uv run kx backup verify <backup>`                   |
| `restore_backup`               |      yes | Manager client             | `POST /v1/instances/restore`     | `uv run kx instance restore <instance>`              |
| `restore_backup_new`           |      yes | Manager client             | `POST /v1/instances/restore-new` | `uv run kx instance restore-new ...`                 |
| `test_restore_backup`          |      yes | Manager backup route       | none                             | `uv run kx backup test-restore <backup>`             |
| `run_security_check`           |      yes | Manager client             | `POST /v1/security/check`        | `uv run kx security check <instance>`                |
| `set_network_profile`          |      yes | Manager client             | `POST /v1/network/set-profile`   | `uv run kx network set-profile <instance> <profile>` |
| `disable_public_mode`          |      yes | Manager client             | `POST /v1/network/set-profile`   | set private/intranet profile                         |
| `set_target_local`             |      yes | Target service             | none                             | local config write                                   |
| `set_target_intranet`          |      yes | Target service             | none                             | intranet config write                                |
| `set_target_droplet`           |      yes | Target service             | none                             | droplet config write                                 |
| `set_target_temporary_public`  |      yes | Target service             | none                             | temporary public config write                        |
| `deploy_local`                 |      yes | Deploy service             | Manager/Agent sequence           | approved CLI sequence                                |
| `deploy_intranet`              |      yes | Deploy service             | Manager/Agent sequence           | approved CLI sequence                                |
| `deploy_droplet`               |      yes | Deploy service             | remote Agent / SSH               | `scp` + approved remote command                      |
| `check_droplet_agent`          |      yes | Deploy/target service      | remote Agent health              | HTTP GET remote Agent                                |
| `copy_capsule_to_droplet`      |      yes | Deploy service             | none                             | `scp` or SFTP library                                |
| `start_droplet_instance`       |      yes | Deploy service             | remote Agent start               | remote approved command                              |
| `open_manager_docs`            |      yes | browser link               | none                             | open `/docs`                                         |
| `open_agent_docs`              |      yes | browser link               | none                             | open Agent `/docs`                                   |

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
stdout/stderr captured
returncode captured
result normalized
```

Remote fallback rules for Droplet:

```text
no password in command string
SSH key path must be validated
remote host must be explicit
remote user must be explicit
remote root must be /opt/konnaxion unless overridden by trusted config
remote command must be allowlisted
capsule copy target must be remote capsules dir
```

---

## 6. Required FastAPI GUI Routes

`kx_manager/ui/app.py` must expose:

```python
def register(app: FastAPI) -> None:
    ...
```

The function must register all routes below.

## 6.1 Page routes

| Method | Route           | Purpose                        |
| ------ | --------------- | ------------------------------ |
| `GET`  | `/ui`           | Dashboard                      |
| `GET`  | `/ui/capsules`  | Capsule operations             |
| `GET`  | `/ui/instances` | Instance operations            |
| `GET`  | `/ui/security`  | Security Gate                  |
| `GET`  | `/ui/network`   | Network profiles               |
| `GET`  | `/ui/backups`   | Backup/restore                 |
| `GET`  | `/ui/restore`   | Restore/rollback               |
| `GET`  | `/ui/logs`      | Logs                           |
| `GET`  | `/ui/health`    | Health                         |
| `GET`  | `/ui/settings`  | Settings                       |
| `GET`  | `/ui/targets`   | Local/intranet/droplet targets |
| `GET`  | `/ui/about`     | Product/about page             |

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
| `POST` | `/ui/actions/check-droplet-agent`          | `check_droplet_agent`          |
| `POST` | `/ui/actions/copy-capsule-to-droplet`      | `copy_capsule_to_droplet`      |
| `POST` | `/ui/actions/start-droplet-instance`       | `start_droplet_instance`       |

Browser-only actions:

| GUI Action          | Route                        |
| ------------------- | ---------------------------- |
| `open_instance`     | runtime URL                  |
| `open_manager_docs` | `/docs`                      |
| `open_agent_docs`   | `http://127.0.0.1:8765/docs` |

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

Remote Droplet Agent endpoints use the same API path with the remote Agent base URL.

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
check_droplet_agent()
copy_capsule_to_droplet()
start_droplet_instance()
```

If these are not part of `KonnaxionAgentClient`, they must be implemented as Manager-local services or route helpers.

---

## 9. Required Request Payloads

## 9.1 Select source folder

```json
{
  "source_dir": "C:\\mycode\\Konnaxion\\Konnaxion"
}
```

## 9.2 Select capsule output folder

```json
{
  "capsule_output_dir": "C:\\mycode\\Konnaxion\\runtime\\capsules"
}
```

## 9.3 Build capsule

```json
{
  "source_dir": "C:\\mycode\\Konnaxion\\Konnaxion",
  "output": "C:\\mycode\\Konnaxion\\runtime\\capsules\\konnaxion-v14-demo-2026.04.30.kxcap",
  "channel": "demo",
  "capsule_id": "konnaxion-v14-demo-2026.04.30",
  "version": "2026.04.30-demo.1",
  "profile": "intranet_private",
  "force": true
}
```

## 9.4 Rebuild capsule

```json
{
  "source_dir": "C:\\mycode\\Konnaxion\\Konnaxion",
  "output": "C:\\mycode\\Konnaxion\\runtime\\capsules\\konnaxion-v14-demo-2026.04.30.kxcap",
  "delete_existing": true,
  "verify_after_build": true,
  "channel": "demo",
  "capsule_id": "konnaxion-v14-demo-2026.04.30",
  "version": "2026.04.30-demo.1",
  "profile": "intranet_private",
  "force": true
}
```

## 9.5 Verify capsule

```json
{
  "capsule_path": "C:\\mycode\\Konnaxion\\runtime\\capsules\\konnaxion-v14-demo-2026.04.30.kxcap"
}
```

## 9.6 Import capsule

```json
{
  "capsule_path": "C:\\mycode\\Konnaxion\\runtime\\capsules\\konnaxion-v14-demo-2026.04.30.kxcap",
  "instance_id": "demo-001",
  "network_profile": "intranet_private"
}
```

## 9.7 Create instance

```json
{
  "instance_id": "demo-001",
  "capsule_id": "konnaxion-v14-demo-2026.04.30",
  "network_profile": "intranet_private",
  "exposure_mode": "private",
  "generate_secrets": true
}
```

## 9.8 Update instance

```json
{
  "instance_id": "demo-001",
  "capsule_path": "C:\\mycode\\Konnaxion\\runtime\\capsules\\konnaxion-v14-demo-2026.04.30.kxcap",
  "create_pre_update_backup": true
}
```

## 9.9 Start instance

```json
{
  "instance_id": "demo-001",
  "run_security_gate": true
}
```

## 9.10 Stop instance

```json
{
  "instance_id": "demo-001",
  "timeout_seconds": 60
}
```

## 9.11 Restart instance

```json
{
  "instance_id": "demo-001",
  "timeout_seconds": 60,
  "run_security_gate": true
}
```

Backend sequence:

```text
stop_instance
start_instance
```

## 9.12 Instance status

```json
{
  "instance_id": "demo-001"
}
```

## 9.13 View logs

```json
{
  "instance_id": "demo-001",
  "service": "django-api",
  "tail": 200
}
```

`service` must be one of:

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

## 9.14 View health

```json
{
  "instance_id": "demo-001"
}
```

## 9.15 Create backup

```json
{
  "instance_id": "demo-001",
  "backup_class": "manual",
  "verify_after_create": true
}
```

## 9.16 Verify backup

```json
{
  "instance_id": "demo-001",
  "backup_id": "<backup-id>"
}
```

## 9.17 Restore backup

```json
{
  "instance_id": "demo-001",
  "backup_id": "<backup-id>",
  "create_pre_restore_backup": true
}
```

## 9.18 Restore backup into new instance

```json
{
  "source_backup_id": "<backup-id>",
  "new_instance_id": "demo-restore-001",
  "network_profile": "intranet_private"
}
```

## 9.19 Test restore backup

```json
{
  "backup_id": "<backup-id>",
  "new_instance_id": "demo-test-restore-001",
  "network_profile": "intranet_private"
}
```

## 9.20 Rollback instance

```json
{
  "instance_id": "demo-001",
  "target_release_id": "<release-id>",
  "restore_data": true,
  "backup_id": "<backup-id>"
}
```

If `restore_data` is true, `backup_id` is required.

## 9.21 Run Security Gate

```json
{
  "instance_id": "demo-001",
  "blocking": true
}
```

## 9.22 Set network profile

```json
{
  "instance_id": "demo-001",
  "network_profile": "intranet_private",
  "exposure_mode": "private",
  "public_mode_expires_at": null
}
```

## 9.23 Disable public mode

```json
{
  "instance_id": "demo-001",
  "network_profile": "intranet_private",
  "exposure_mode": "private",
  "public_mode_expires_at": null
}
```

## 9.24 Set local target

```json
{
  "target_mode": "local",
  "network_profile": "local_only",
  "exposure_mode": "private",
  "runtime_root": "C:\\mycode\\Konnaxion\\runtime"
}
```

## 9.25 Set intranet target

```json
{
  "target_mode": "intranet",
  "network_profile": "intranet_private",
  "exposure_mode": "private",
  "runtime_root": "C:\\mycode\\Konnaxion\\runtime",
  "host": "konnaxion.local"
}
```

## 9.26 Set temporary public target

```json
{
  "target_mode": "temporary_public",
  "network_profile": "public_temporary",
  "exposure_mode": "temporary_tunnel",
  "public_mode_expires_at": "2026-04-30T22:00:00Z"
}
```

## 9.27 Set Droplet target

```json
{
  "target_mode": "droplet",
  "network_profile": "public_vps",
  "exposure_mode": "public",
  "droplet_name": "konnaxion-prod-01",
  "droplet_host": "203.0.113.10",
  "droplet_user": "root",
  "ssh_key_path": "C:\\Users\\user\\.ssh\\id_ed25519",
  "remote_kx_root": "/opt/konnaxion",
  "domain": "app.example.com",
  "remote_agent_url": "http://203.0.113.10:8765/v1"
}
```

## 9.28 Deploy local

```json
{
  "source_dir": "C:\\mycode\\Konnaxion\\Konnaxion",
  "capsule_output_dir": "C:\\mycode\\Konnaxion\\runtime\\capsules",
  "instance_id": "demo-001",
  "target_mode": "local",
  "network_profile": "local_only",
  "exposure_mode": "private",
  "build": true,
  "verify": true,
  "import_capsule": true,
  "start": true
}
```

## 9.29 Deploy intranet

```json
{
  "source_dir": "C:\\mycode\\Konnaxion\\Konnaxion",
  "capsule_output_dir": "C:\\mycode\\Konnaxion\\runtime\\capsules",
  "instance_id": "demo-001",
  "target_mode": "intranet",
  "network_profile": "intranet_private",
  "exposure_mode": "private",
  "build": true,
  "verify": true,
  "import_capsule": true,
  "start": true
}
```

## 9.30 Deploy Droplet

```json
{
  "source_dir": "C:\\mycode\\Konnaxion\\Konnaxion",
  "capsule_output_dir": "C:\\mycode\\Konnaxion\\runtime\\capsules",
  "capsule_file": "C:\\mycode\\Konnaxion\\runtime\\capsules\\konnaxion-v14-demo-2026.04.30.kxcap",
  "instance_id": "demo-001",
  "target_mode": "droplet",
  "network_profile": "public_vps",
  "exposure_mode": "public",
  "droplet_host": "203.0.113.10",
  "droplet_user": "root",
  "ssh_key_path": "C:\\Users\\user\\.ssh\\id_ed25519",
  "remote_kx_root": "/opt/konnaxion",
  "domain": "app.example.com",
  "build": true,
  "verify": true,
  "copy": true,
  "import_capsule": true,
  "start": true
}
```

---

## 10. Required Normalized Action Result

Every GUI action must render from this normalized result:

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

Remote Droplet result:

```json
{
  "ok": true,
  "action": "deploy_droplet",
  "instance_id": "demo-001",
  "message": "Droplet deployment completed.",
  "data": {
    "droplet_host": "203.0.113.10",
    "domain": "app.example.com",
    "remote_capsule_path": "/opt/konnaxion/capsules/konnaxion-v14-demo-2026.04.30.kxcap",
    "health_url": "http://203.0.113.10:8765/v1/health"
  }
}
```

---

## 11. UI Button Coverage

The Dashboard must include:

```text
Check Manager
Check Agent
Select Source Folder
Select Output Folder
Rebuild Capsule
Verify Capsule
Import Capsule
Create Instance
Update Instance
Start Instance
Stop Instance
Instance Status
Instance Health
Security Check
Set Network Profile
Open Manager Docs
Open Agent Docs
```

The Capsules page must include:

```text
Build Capsule
Rebuild Capsule
Verify Capsule
Import Capsule
List Capsules
View Capsule
```

The Instances page must include:

```text
Create Instance
Update Instance
Start Instance
Stop Instance
Restart Instance
Status
Logs
Health
Rollback
Open Instance
```

The Backups page must include:

```text
Create Backup
List Backups
Verify Backup
Restore Backup
Restore Backup New
Test Restore Backup
```

The Network page must include:

```text
Set Network Profile
Disable Public Mode
```

The Security page must include:

```text
Run Security Check
```

The Targets page must include:

```text
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
```

---

## 12. Safety Gating

## 12.1 Start button

Start must be disabled when:

```text
state in importing, verifying, starting, stopping, updating, rolling_back, security_blocked
security_status = FAIL_BLOCKING
```

Start may be enabled when:

```text
state in created, ready, stopped, degraded
security_status in PASS, WARN, UNKNOWN
```

If `security_status = UNKNOWN`, clicking Start must run Security Gate first or require explicit confirmation.

## 12.2 Public exposure

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
exposure_mode = public
```

then:

```text
network_profile = public_vps
explicit confirmation required
domain or host must be configured
```

## 12.3 Destructive actions

These require confirmation:

```text
stop_instance
restore_backup
restore_backup_new
rollback_instance
disable_public_mode
deploy_droplet
```

## 12.4 Rollback

If:

```text
restore_data = true
```

then:

```text
backup_id is required
```

## 12.5 Droplet deployment

Droplet deployment must be blocked unless:

```text
droplet_host is set
droplet_user is set
ssh_key_path exists
remote_kx_root is set
network_profile = public_vps
exposure_mode = public
explicit confirmation is accepted
```

---

## 13. Canonical Labels

Use these exact user-facing labels.

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
Rollback
Create Backup
List Backups
Verify Backup
Restore Backup
Restore Backup New
Test Restore Backup
Run Security Check
Set Network Profile
Disable Public Mode
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

---

## 14. Required Tests

Create:

```text
tests/test_manager_ui_action_coverage.py
```

Required tests:

```text
test_all_uiactions_have_labels
test_all_uiactions_have_route_or_link
test_all_post_action_routes_start_with_ui_actions
test_all_required_actions_exist
test_no_extra_unmapped_actions_exist
test_build_capsule_action_exists
test_rebuild_capsule_action_exists
test_restart_instance_action_exists
test_instance_status_action_exists
test_list_backups_action_exists
test_test_restore_backup_action_exists
test_check_manager_action_exists
test_check_agent_action_exists
test_open_docs_actions_exist
test_target_actions_exist
test_droplet_actions_exist
test_deploy_actions_exist
test_action_payloads_use_canonical_network_profiles
test_action_payloads_use_canonical_exposure_modes
test_action_payloads_use_canonical_docker_services
test_public_temporary_requires_expiration
test_public_vps_requires_confirmation
test_rollback_restore_data_requires_backup_id
test_droplet_deploy_requires_host_user_key_remote_root
test_command_fallback_uses_shell_false
test_fastapi_ui_register_exists
test_streamlit_is_not_required_for_fastapi_ui_import
```

Run:

```powershell
uv run python -m compileall kx_manager/ui kx_manager/services tests
uv run pytest -q
```

---

## 15. Acceptance Criteria

The GUI action coverage is complete when:

```text
All required UiAction values exist.
Every UiAction has a label.
Every UiAction maps to a route, link, client method, Agent endpoint, service wrapper, deploy wrapper, or CLI fallback.
Every action route is registered by kx_manager/ui/app.py.
Every action validates canonical values.
No GUI button exists without a mapped action.
No mapped action lacks a GUI button.
Local/intranet/droplet target modes are represented.
pytest passes.
```

The GUI is considered usable instead of commands when an operator can do this in browser:

```text
Check Manager
Check Agent
Select Konnaxion source folder
Select capsule output folder
Build Capsule
Verify Capsule
Import Capsule
Create Instance
Update Instance
Start Instance
View Status
View Health
Run Security Check
View Logs
Create Backup
Stop Instance
Rollback or Restore when needed
Deploy Local
Deploy Intranet
Deploy Droplet
```

without typing CLI commands.

---

## 16. Final Rule

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

