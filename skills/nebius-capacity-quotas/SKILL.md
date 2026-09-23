---
name: nebius-capacity-quotas
description: GPU capacity advice and quota checks for Nebius. Use for "can I launch 8xB200 in us-central1-b", "what GPU capacity is currently advised", "how much quota do I have", "what's in our reservation", or "request a quota increase".
license: Apache-2.0
compatibility: Requires the nebius CLI (>=0.12.247) with a configured profile; jq recommended
metadata:
  version: "0.1.0"
allowed-tools:
  - Bash(nebius version:*)
  - Bash(nebius profile list:*)
  - Bash(nebius profile current:*)
  - Bash(nebius config get:*)
  - Bash(nebius capacity resource-advice list:*)
  - Bash(nebius capacity capacity-block-group list:*)
  - Bash(nebius capacity capacity-block-group get:*)
  - Bash(nebius capacity capacity-block-group get-by-resource-affinity:*)
  - Bash(nebius capacity capacity-block-group list-resources:*)
  - Bash(nebius capacity capacity-interval list:*)
  - Bash(nebius capacity capacity-interval get:*)
  - Bash(nebius capacity capacity-allowance list:*)
  - Bash(nebius capacity capacity-allowance get:*)
  - Bash(nebius capacity capacity-allowance get-by-parent-and-capacity-block-group:*)
  - Bash(nebius capacity capacity-allowance list-by-capacity-block-group:*)
  - Bash(nebius quotas quota-allowance list:*)
  - Bash(nebius quotas quota-allowance get:*)
  - Bash(nebius quotas quota-allowance get-by-name:*)
  - Bash(nebius compute platform list:*)
---

# Nebius Capacity & Quotas

GPU VM launch guidance: timestamped physical-capacity advice (tenant-wide), reservations (capacity block groups), and quota allowances (per project/region). Capacity advice is not a launch guarantee and does not cover CPU-only VMs or storage resources.

<!-- BEGIN SHARED PREAMBLE (generated from shared/preamble.md — edit there, then run scripts/sync-shared.py) -->
## Nebius CLI ground rules

These rules apply to every command in this skill. Full detail lives in the `nebius-cloud-basics` skill.

**Agent identification.** Export `AI_AGENT` before any Nebius CLI call, including preflight and `--help`. Keep non-empty harness-set value; unset or empty → set own harness slug. Every call must inherit it, including new shells.

**CLI present and configured.** Before the first Nebius call in a session:

```bash
nebius version                 # CLI installed (a subcommand — there is no --version flag)
nebius profile list            # at least one profile; [default] marks the active one
nebius config get parent-id    # project-...
nebius config get tenant-id    # tenant-...
```

These skills require CLI `0.12.247` or newer; an individual skill may state a higher floor (the Serverless skills need `0.12.277`) — the stricter number wins. If `nebius version` is older, stop and ask the user to update the CLI before relying on the commands or schemas below.

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

## The one thing everyone gets wrong

Capacity advice is keyed by **tenant NID**, not project. `nebius capacity resource-advice list --parent-id project-...` fails or returns nothing useful. Resolve the tenant first:

```bash
TENANT=$(nebius config get tenant-id)
nebius capacity resource-advice list --parent-id "$TENANT" --format json --all
```

Each advice entry is one GPU VM (region, fabric, platform, preset) combination reporting timestamped availability for three allocation types: **reserved**, **on-demand**, **preemptible** — already clipped by the tenant's quotas. Advice can become stale and does not guarantee that a later create will succeed.

## Where region, platform, and preset names come from

Never type platform or preset names from memory. For GPU VM capacity, this call enumerates the combinations currently reported by Capacity Advisor:

```bash
nebius capacity resource-advice list --parent-id "$TENANT" --format json --all \
  | jq -r '.items[] | [.spec.region, .spec.compute_instance.platform, .spec.compute_instance.preset.name] | @tsv' \
  | sort -u
```

Run this once per session and reuse the output while checking `data_state` and `effective_at`. Region values are opaque service output and may be plain (`eu-north1`) or location-specific (`us-central1-b`); platform and preset examples include `gpu-b200-sxm` and `8gpu-160vcpu-1792gb`.

- `nebius compute platform list --parent-id "$PROJECT" --format json --all` answers "which presets exist for platform X" from the project side. It says nothing about availability.
- **Do not translate regions by hand.** Use the region string from `resource-advice` only to filter that response. For quota lookups, use the plain region from quota output (for example, `eu-north1`). The strings may coincide, but location-specific capacity values such as `us-central1-b` are not valid quota regions.
- `resource-advice list --help` claims it "supports filtering by region, resource type, or platform", but exposes no filter flags. Filtering is client-side jq only.

If a requested GPU platform is valid according to `compute platform list` but absent from Capacity Advisor, report that no advice is available; do not claim the platform is invalid. Capacity Advisor provides no answer for CPU-only VMs or storage.

## Workflow: "Can I launch 8×B200 in us-central1-b?"

1. Resolve context: `TENANT=$(nebius config get tenant-id)`, `PROJECT=$(nebius config get parent-id)`.
2. Pull advice and filter. The `b200` and `us-central1` literals below are **placeholders** — substitute the real values from the enumeration above (see *Where region, platform, and preset names come from*); never copy these through:
   ```bash
   nebius capacity resource-advice list --parent-id "$TENANT" --format json --all \
     | jq '.items[] | select((.spec.compute_instance.platform | test("b200")) and (.spec.region | test("us-central1")))'
   ```
   Entry shape (verify on first call, the API is versioned): `spec.region`, `spec.fabric`, `spec.compute_instance.platform`, `spec.compute_instance.preset.name`, resource counts under `spec.compute_instance.preset.resources`, and `status.reserved` / `status.on_demand` / `status.preemptible`. Each status may contain `available`, `limit`, `availability_level`, `data_state`, and `effective_at`; fields can be absent when not applicable.
3. Report all three allocation types with `available`, `limit`, `availability_level`, `data_state`, and `effective_at` when present. State that the result is timestamped advice, not guaranteed free capacity. A "no on-demand" answer with advised preemptible capacity is still useful.
4. Cross-check the project's quota if the user intends to launch (capacity and quota fail independently):
   ```bash
   nebius quotas quota-allowance list --parent-id "$PROJECT" --format json --all \
     | jq '.items[] | select(.metadata.name | test("gpu|compute"))'
   ```
5. If capacity exists but is reserved, check whether the tenant's reservations cover it: see reservations below.

## Reservations (capacity block groups)

Tenant-scoped, read-only — reservations are arranged with a Nebius account manager, not self-served:

```bash
nebius capacity capacity-block-group list --parent-id "$TENANT" --format json --all
nebius capacity capacity-block-group get <id> --format json          # window, size, platform
nebius capacity capacity-block-group list-resources <id> --format json  # which instances occupy it
nebius capacity capacity-interval list --parent-id "$TENANT" --format json --all
```

`capacity-allowance` (project-scoped) maps how much of a capacity block group each project may use: `list`, `get`, `get-by-parent-and-capacity-block-group`, `list-by-capacity-block-group` are Tier A; `create`/`update` are Tier B; `delete` is Tier C.

## Quota allowances

```bash
# all quotas for a project (or tenant)
nebius quotas quota-allowance list --parent-id "$PROJECT" --format json --all

# one quota by name+region (all three flags required)
nebius quotas quota-allowance get-by-name --parent-id "$PROJECT" \
  --name compute.disk.size.network-ssd --region us-central1 --format json
```

Quota entries carry current usage in `status.usage` with `status.unit`; the allowed value lives in the spec **only when an explicit allowance is set** — tenants running on defaults show usage without a limit field. Dump one entry raw before extracting programmatically. Quota names are hierarchical strings at `metadata.name` (e.g. `compute.disk.count`); discover the exact names from `list` output rather than constructing them.

**Quota increases** are `quota-allowance create` (also used to raise an existing quota: "If the quota already exists, its value is replaced") or `update` — **Tier B**: print the exact command, state old → new value, get explicit confirmation, run once. `quota-allowance delete` resets a quota's value — **Tier C**, refuse and hand the command to the human.

## Hand-offs

- Capacity + quota confirmed and the user wants to launch → `nebius-compute-provision`.
- The workload is a container job or inference endpoint, not a VM → `nebius-serverless-jobs` / `nebius-serverless-endpoints`.
