#!/usr/bin/env bash
# Command skeleton for CLI 0.12.277. Copy and resolve it for the task.
# All create-specific flags are covered below; global flags are not enumerated.
# Export AI_AGENT first per the shared preamble; preserve a non-empty harness value.
# Verify `nebius ai devlab create --help` for the installed version.
# This asset validates only. After the Tier B gate, run the reviewed command
# once without --dry-run. It does not install, authenticate, or create secrets.
set -euo pipefail

# Require explicit values to prevent an accidental run against a default project.
: "${DEVLAB_PROFILE:?Set the Nebius CLI profile}"
: "${DEVLAB_PROJECT_ID:?Set the project ID}"
: "${DEVLAB_NAME:?Set the Devlab name}"
: "${DEVLAB_TEMPLATE:?Select a template from devlab template list}"
: "${DEVLAB_PLATFORM:?Select a platform from the target project catalog}"
: "${DEVLAB_PRESET:?Select a preset belonging to that platform}"
: "${DEVLAB_DISK_SIZE:?Set the shared container/workspace disk size, e.g. 250Gi}"

cmd=(nebius ai devlab create
  -p "$DEVLAB_PROFILE"
  --parent-id "$DEVLAB_PROJECT_ID"
  --name "$DEVLAB_NAME"
  --template "$DEVLAB_TEMPLATE"
  --platform "$DEVLAB_PLATFORM"
  --preset "$DEVLAB_PRESET"
  --disk-size "$DEVLAB_DISK_SIZE"
  --dry-run
  --format json
)

# Template mode: inspect the template's declared inputs and default workspace.
# --input is repeatable and requires --template; names are template-specific.
# cmd+=(--input 'INPUT_NAME=VALUE')

# Custom image mode: remove --template and the DEVLAB_TEMPLATE requirement above.
# Add BOTH --image and --primary-route-port. Template and image are exclusive.
# cmd+=(--image 'registry.example.com/team/dev:tag')
# cmd+=(--primary-route-port 8888)
# The custom image must start a reachable web service on the primary route port.
# These overrides are NOT allowed with --template:
# cmd+=(--container-command '<entrypoint-command>')
# cmd+=(--args '<container-arguments>')
# cmd+=(--working-dir '/workspace')

# Debugging mode: source failed job configuration; dry-run resolves the result.
# --image overrides disable registry credential inheritance from the source job.
# cmd+=(--from-job '<failed-job-id>')
# cmd+=(--registry-secret '<selector>') # REGISTRY_USERNAME + REGISTRY_PASSWORD

# Workspace is persistent; extra mounts must not overlap it (including ancestors).
# Defaults: /workspace for custom images; template default for template mode.
# cmd+=(--workspace-path '/workspace')
# --volume is repeatable; plain mounts accept SOURCE:CONTAINER_PATH[:rw|ro].
# Devlab S3 mounts require a secret selector; PROFILE is an AWS profile here.
# cmd+=(--volume 's3://BUCKET:/data:ro:PROFILE@SECRET_SELECTOR')

# Configuration and credentials: repeat flags for multiple entries.
# cmd+=(--env 'LOG_LEVEL=info')              # non-secret KEY=VALUE only
# cmd+=(--env-secret 'HF_TOKEN=SECRET_SELECTOR')
# cmd+=(--inject-file './app.conf:/etc/app.conf') # absolute target, read-only, <=64 KiB
# Secret selectors: name, ID, version ID, or SECRET_ID@VERSION_ID.
# cmd+=(--auth-token-secret '<selector>')   # AUTH_TOKEN payload key, never token value

# Additional container ports, repeatable; distinct from the primary UI route.
# cmd+=(--container-port '8000/http')
# cmd+=(--shm-size '16Gi')                  # default 16Gi on GPU platforms, 0 on CPU
# cmd+=(--subnet-id '<subnet-id>')

# SSH: public-key CONTENT, repeatable. Never load/print a private key.
# cmd+=(--ssh-key '<public-key-content>')
# cmd+=(--public)                          # runtime public IP; default false
# Public SSH requires --public. Managed web access alone does not require it.

# On the reviewed create, --async returns immediately; poll the operation/resource.
# cmd+=(--async)
# No workload timeout flag exists: global --timeout limits the API request only.
"${cmd[@]}"
