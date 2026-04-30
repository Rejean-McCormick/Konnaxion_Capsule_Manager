# Konnaxion Capsule Manager

Konnaxion Capsule Manager packages Konnaxion v14 into signed, portable `.kxcap` capsules and runs them through a local Manager, privileged Agent, Docker Compose runtime, private-by-default network profiles, Security Gate checks, backups, restores, rollback, GUI workflows, and the canonical `kx` CLI.

## Purpose

The project turns Konnaxion into a portable, secure, plug-and-play appliance system.

```text
Konnaxion Source
→ Konnaxion Capsule Builder
→ Signed .kxcap Capsule
→ Konnaxion Capsule Manager
→ Konnaxion Agent
→ Docker Compose Runtime
→ Konnaxion Instance
````

## Core Components

* `kx_shared/` — canonical constants, paths, states, profiles, services, and validation
* `kx_agent/` — privileged local service for runtime, security, network, backup, restore, and rollback actions
* `kx_manager/` — user-facing API and local GUI layer
* `kx_builder/` — capsule build, manifest, checksum, image, and signature tooling
* `kx_cli/` — canonical `kx` operator/developer CLI
* `profiles/` — approved network profiles
* `policies/` — runtime and Security Gate policies
* `templates/` — Docker Compose and environment templates
* `docs/` — technical contracts and operator documentation
* `tests/` — contract and integration tests

## Default Runtime

Konnaxion runs through Docker Compose with canonical service names only:

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

Forbidden aliases include `backend`, `api`, `frontend`, `db`, `cache`, `worker`, `scheduler`, and `agent`.

## Security Model

Konnaxion is private by default.

The system enforces:

* signed capsules only
* generated secrets on install
* deny-by-default networking
* Traefik-only HTTP/S entrypoint
* no public PostgreSQL or Redis
* no Docker socket mounts
* no privileged app containers
* no host networking for app containers
* canonical network profiles only
* blocking Security Gate checks before startup
* backup safety checks before restore and rollback workflows

## Network Profiles

Supported canonical profiles:

```text
local_only
intranet_private
private_tunnel
public_temporary
public_vps
offline
```

Supported exposure modes:

```text
private
lan
vpn
temporary_tunnel
public
```

Default:

```text
network_profile = intranet_private
exposure_mode = private
```

Temporary public mode requires an expiration. Public VPS mode requires explicit operator confirmation.

## GUI

The Manager GUI is intended to run locally at:

```text
http://127.0.0.1:8714/ui
```

The GUI contract covers:

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
deploy local
deploy intranet
deploy droplet
```

The GUI must remain local-only by default and must not execute arbitrary shell commands. Every GUI action must map to an allowlisted Manager route, Agent API endpoint, Builder service, Deploy service, or approved CLI fallback.

GUI technical contracts:

```text
docs/DOC-16_Konnaxion_Manager_GUI_Technical_Contract.md
docs/DOC-17_Konnaxion_GUI_Action_Coverage_Contract.md
docs/DOC-18_Konnaxion_GUI_Target_Modes.md
```

## Target Modes

The GUI and Manager support these target modes:

```text
local
intranet
temporary_public
droplet
```

Target mapping:

| Target mode        | Network profile    | Exposure mode      | Purpose                         |
| ------------------ | ------------------ | ------------------ | ------------------------------- |
| `local`            | `local_only`       | `private`          | Same-machine development        |
| `intranet`         | `intranet_private` | `private` or `lan` | Private LAN/internal deployment |
| `temporary_public` | `public_temporary` | `temporary_tunnel` | Time-limited public demo        |
| `droplet`          | `public_vps`       | `public`           | Remote VPS/Droplet deployment   |

## Canonical CLI

```bash
kx capsule build
kx capsule verify
kx capsule import

kx instance create
kx instance start
kx instance stop
kx instance status
kx instance logs
kx instance backup
kx instance restore
kx instance restore-new
kx instance update
kx instance rollback
kx instance health

kx backup list
kx backup verify
kx backup test-restore

kx security check
kx network set-profile
```

## Development with uv

Create and install the environment:

```powershell
uv venv
uv pip install -e ".[dev]"
```

Run compile and tests:

```powershell
uv run python -m compileall kx_shared kx_agent kx_manager kx_builder kx_cli tests
uv run pytest -q
```

Current expected baseline:

```text
331 passed, 8 skipped
```

## Run the Agent

```powershell
uv run kx-agent run
```

Default Agent URL:

```text
http://127.0.0.1:8765
```

Useful endpoints:

```text
http://127.0.0.1:8765/docs
http://127.0.0.1:8765/v1/health
http://127.0.0.1:8765/v1/agent/info
```

A `404` at `/` is normal because the Agent does not define a homepage route.

## Run the Manager

```powershell
uv run kx-manager --host 127.0.0.1 --port 8714
```

Default Manager URLs:

```text
http://127.0.0.1:8714
http://127.0.0.1:8714/docs
http://127.0.0.1:8714/ui
```

## Windows Runtime Defaults

For local Windows development:

```powershell
$env:KX_ROOT="C:\mycode\Konnaxion\runtime"
$env:KX_SOURCE_DIR="C:\mycode\Konnaxion\Konnaxion"
$env:KX_AGENT_HOST="127.0.0.1"
$env:KX_AGENT_PORT="8765"
$env:KX_MANAGER_HOST="127.0.0.1"
$env:KX_MANAGER_PORT="8714"
```

Runtime folders:

```text
C:\mycode\Konnaxion\runtime\capsules
C:\mycode\Konnaxion\runtime\instances
C:\mycode\Konnaxion\runtime\backups
C:\mycode\Konnaxion\runtime\shared
```

Canonical appliance runtime paths remain:

```text
/opt/konnaxion
/opt/konnaxion/capsules
/opt/konnaxion/instances
/opt/konnaxion/backups
/opt/konnaxion/shared
```

## Typical Local Workflow

```powershell
uv run kx-builder capsule build --source-dir C:\mycode\Konnaxion\Konnaxion --output C:\mycode\Konnaxion\runtime\capsules\konnaxion-v14-demo-2026.04.30.kxcap --channel demo --capsule-id konnaxion-v14-demo-2026.04.30 --version 2026.04.30-demo.1 --profile intranet_private --force

uv run kx-builder capsule verify C:\mycode\Konnaxion\runtime\capsules\konnaxion-v14-demo-2026.04.30.kxcap

uv run kx capsule import C:\mycode\Konnaxion\runtime\capsules\konnaxion-v14-demo-2026.04.30.kxcap

uv run kx instance create demo-001
uv run kx instance start demo-001
uv run kx instance status demo-001
uv run kx instance health demo-001
```

## Target

Konnaxion as a signed, portable, private-by-default capsule system deployable on:

```text
Konnaxion Box
local host
intranet server
private tunnel
temporary public demo
hardened VPS/Droplet
```

