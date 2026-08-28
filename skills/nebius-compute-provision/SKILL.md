---
name: nebius-compute-provision
description: Gated provisioning for Nebius Compute. Use for "create a VM", "provision a GPU cluster", "launch 8xH200", "resize this disk", "add a filesystem", "stop that instance" - any create, update, start, or stop.
license: Apache-2.0
compatibility: Requires the nebius CLI (>=0.12.247) with a configured profile; jq recommended
metadata:
  version: "0.1.0"
allowed-tools:
  - Bash(nebius version:*)
  - Bash(nebius profile list:*)
  - Bash(nebius profile current:*)
  - Bash(nebius config get:*)
  - Bash(nebius compute platform list:*)
  - Bash(nebius compute image list-public:*)
  - Bash(nebius compute image get-latest-by-family:*)
  - Bash(nebius compute instance list:*)
  - Bash(nebius compute instance get:*)
  - Bash(nebius compute instance get-by-name:*)
  - Bash(nebius compute disk list:*)
  - Bash(nebius compute disk get:*)
  - Bash(nebius compute gpu-cluster list:*)
  - Bash(nebius compute gpu-cluster get:*)
  - Bash(nebius compute filesystem list:*)
  - Bash(nebius compute filesystem get:*)
  - Bash(nebius capacity resource-advice list:*)
  - Bash(nebius quotas quota-allowance list:*)
  - Bash(nebius quotas quota-allowance get-by-name:*)
  - Bash(nebius billing v1alpha1 calculator estimate:*)
  - Bash(nebius billing v1alpha1 calculator estimate-batch:*)
---

# Nebius Compute Provisioning (gated)

Create and change compute resources deliberately: preflight capacity, quota, and cost; render a reviewable spec; show the exact command; run it once after explicit confirmation.

Note: `allowed-tools` above pre-approves only the read-only preflight commands. Every `create`/`update`/`start`/`stop` goes through the normal permission flow *and* the confirmation gate below — that is intentional, not an omission.

<!-- BEGIN SHARED PREAMBLE (generated from shared/preamble.md — edit there, then run scripts/sync-shared.py) -->
## Nebius CLI ground rules

These rules apply to every command in this skill. Full detail lives in the `nebius-cloud-basics` skill.

**CLI present and configured.** Before the first Nebius call in a session:

```bash
nebius version                 # CLI installed (a subcommand — there is no --version flag)
nebius profile list            # at least one profile; [default] marks the active one
nebius config get parent-id    # project-...
nebius config get tenant-id    # tenant-...
```

These skills require CLI `0.12.247` or newer; an individual skill may state a higher floor (the Serverless skills need `0.12.265`) — the stricter number wins. If `nebius version` is older, stop and ask the user to update the CLI before relying on the commands or schemas below.

If any check fails or an ID comes back empty, stop and walk the user through [CLI installation and profile setup](https://docs.nebius.com/cli/install): `curl -sSL https://storage.eu-north1.nebius.cloud/cli/install.sh | bash`, then `nebius profile create --parent-id <project-id>`. **Print those commands for the user to run — do not run them yourself**: the installer writes to their machine and the shown federation-profile command opens a browser and blocks. An expired session does not show up here; it surfaces on the first real API call, and re-auth is the same human task.

**Resolve context first — never guess IDs.** Nearly every call needs `--parent-id`, and the CLI does not say which scope it wants:

```bash
nebius profile current                        # which profile is active
nebius config get parent-id  [-p <profile>]   # project-...  (project scope)
nebius config get tenant-id  [-p <profile>]   # tenant-...   (tenant scope)
```

Compute resources are generally **project**-scoped; public-image discovery is region-scoped. Quota allowances may be project- or tenant-scoped. Capacity advice, capacity block groups, and capacity intervals are **tenant**-scoped. The wrong scope often returns empty lists or permission errors, not a helpful message. Pass `-p <profile>` explicitly whenever the user names a profile.

**Output.** Add `--format json` to API calls and parse that; the default table output is for humans. On paginated `list` calls, add `--all` only when `--help` exposes it. Some list-like commands differ: for example, `compute image list-public` requires `--region` and has no `--all`. Never pass `-i`/`--interactive`: it opens interactive entry or alternate-screen pagination and hangs unattended sessions. Never pass `--follow` (e.g. `compute instance logs --follow`, `logging query --follow`): it streams until killed and hangs an unattended session the same way.

**Editing.** Never run `edit` or `edit-by-name`: they open `$EDITOR` and hang in a non-interactive shell. Use `update` with explicit flags or `update -f <file>` instead.

**Async operations.** Mutations return an operation; by default the CLI blocks until it completes. With `--async` it returns an operation id — poll with `nebius <service> <resource> operation wait <operation-id>`.

**Safety tiers.**

| Tier | Operations | Behavior |
|---|---|---|
| A — read | `list`, `get`, `get-by-name`, `batch-get`, `list-*`, `logs`, `--help` | Run freely. |
| B — gated write | `create`, `update`, `start`, `stop`, quota/capacity allowance changes | Print the fully resolved command verbatim, state what it changes and the cost implication, wait for explicit user confirmation, then run it exactly once. Never batch mutations; never retry one after an ambiguous failure. |
| C — refuse | `delete`, `purge`, credential issuance (`iam get-access-token`, access keys; sole exception: `iam auth-public-key generate` is Tier B), `-I`/`--impersonate-service-account-id` (a global flag, valid on *every* command — including otherwise-free reads) | Do not run. Print the exact command for the human to run themselves and explain the blast radius. |

**Secrets.** Never print or persist tokens, access keys, or the contents of `~/.nebius/credentials.json`.
<!-- END SHARED PREAMBLE -->

## The provisioning workflow (follow in order, no skipping)

1. **Gather requirements.** Resource type, name, project (`PROJECT=$(nebius config get parent-id)` unless the user names one), and for instances: platform + preset, boot image, subnet. Anything missing → ask, don't default silently.
2. **Preflight what applies, before writing any spec:**
   ```bash
   # Instances: valid platform/preset names in the project's region
   nebius compute platform list --parent-id "$PROJECT" --format json --all

   # GPU instances only: current, non-guaranteed capacity advice (tenant-scoped)
   nebius capacity resource-advice list --parent-id "$(nebius config get tenant-id)" --format json --all

   # All resources: inspect the relevant project quota headroom
   nebius quotas quota-allowance list --parent-id "$PROJECT" --format json --all
   ```
   Capacity Advisor covers GPU VMs, not CPU-only VMs, disks, filesystems, or GPU-cluster resources. For a GPU VM, report `available`, `availability_level`, `data_state`, and `effective_at`; explain that advice is a timestamped estimate, not a launch guarantee. If an applicable quota cannot cover the request, or GPU advice reports no launchable capacity, stop and report.
3. **Estimate cost** where the calculator supports the resource, e.g. for a disk:
   ```bash
   nebius billing v1alpha1 calculator estimate \
     --resource-spec-compute-disk-spec-type network_ssd \
     --resource-spec-compute-disk-spec-size-gibibytes 500 --format json
   ```
4. **Build the spec.** Simple resources (disk, filesystem, gpu-cluster) fit in explicit flags. Instances have 30+ create flags — use a template file instead: copy the matching file from [assets/](assets/), fill it in, and pass it with `create -f <file>`. Template field names mirror the create flags (kebab-case flag → snake_case field, flag prefix → nesting); verify the final shape against a live resource (`get --format yaml`) when one exists.
5. **Confirmation gate.** Print, verbatim: the full command, the rendered template (if any), what will be created/changed, and the cost estimate. Then **stop and wait for an explicit yes**. No confirmation → no mutation. Never bundle two mutations into one confirmation.
6. **Execute once.** Prefer blocking mode (no `--async`) for single resources; for slow creates use `--async` and `nebius compute <resource> operation wait <op-id>`. If the outcome is ambiguous (timeout, dropped connection): do **not** re-run — check `list`/`get` and `list-operations-by-parent` first.
7. **Verify and report.** `get` the resource, report id, name, and state.

## Updates (the only editing path)

Never `edit`/`edit-by-name` ($EDITOR hang). Two safe options:

- **Small change** — explicit flags: `nebius compute disk update <id> --size-gibibytes 1000` (updates only named fields).
- **File-driven** — `update -f <file>` implies `--full`: the file **replaces** the whole spec. Start from `get --format yaml`, but build an update request containing only the fields accepted by `update --help` (normally `metadata` and `spec`); remove `status` and other output-only fields. Keep `metadata.id` and `metadata.resource_version` so a concurrent change fails loudly instead of being overwritten.

Both are Tier B: preview → confirm → run once → verify.

`start`/`stop` are also Tier B. Warn on `stop`: it releases non-reserved GPU capacity, which may not be available again at `start`.

## Refusals (Tier C — always)

`delete` of any resource is never executed by this skill, even on direct request. `compute instance delete` also deletes managed disks declared in the instance spec. Print the exact command for the human, explain what is destroyed and what depends on it. Snapshot-before-delete advice: suggest `nebius compute disk-snapshot` workflows so data outlives the resource.

## Templates

- [assets/instance-template.yaml](assets/instance-template.yaml) — VM/GPU instance (the 30-flag case)
- [assets/disk-template.yaml](assets/disk-template.yaml)
- [assets/filesystem-template.yaml](assets/filesystem-template.yaml)
- [assets/gpu-cluster-template.yaml](assets/gpu-cluster-template.yaml)

## Hand-offs

- The workload is "run this container" or "serve this model" rather than "give me a VM" → `nebius-serverless-jobs` / `nebius-serverless-endpoints` (no instance, subnet, or image plumbing to manage).
