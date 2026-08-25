---
name: nebius-compute-inventory
description: Read-only inventory of Nebius Compute. Use for "list instances", "show disks", "find the GPU cluster", "which platforms and presets exist", "what images can I boot" - any question about what exists.
license: Apache-2.0
compatibility: Requires the nebius CLI (>=0.12) with a configured profile; jq recommended
metadata:
  version: "0.1.0"
allowed-tools:
  - Bash(nebius version:*)
  - Bash(nebius profile list:*)
  - Bash(nebius profile current:*)
  - Bash(nebius config get:*)
  - Bash(nebius compute instance list:*)
  - Bash(nebius compute instance get:*)
  - Bash(nebius compute instance get-by-name:*)
  - Bash(nebius compute instance batch-get:*)
  - Bash(nebius compute instance logs:*)
  - Bash(nebius compute instance list-operations-by-parent:*)
  - Bash(nebius compute instance list-instances-by-nvl-instance-group:*)
  - Bash(nebius compute disk list:*)
  - Bash(nebius compute disk get:*)
  - Bash(nebius compute disk get-by-name:*)
  - Bash(nebius compute filesystem list:*)
  - Bash(nebius compute filesystem get:*)
  - Bash(nebius compute filesystem get-by-name:*)
  - Bash(nebius compute gpu-cluster list:*)
  - Bash(nebius compute gpu-cluster get:*)
  - Bash(nebius compute gpu-cluster get-by-name:*)
  - Bash(nebius compute image list:*)
  - Bash(nebius compute image list-public:*)
  - Bash(nebius compute image get:*)
  - Bash(nebius compute image get-by-name:*)
  - Bash(nebius compute image get-latest-by-family:*)
  - Bash(nebius compute platform list:*)
  - Bash(nebius compute platform get:*)
  - Bash(nebius compute node list:*)
  - Bash(nebius compute node get:*)
  - Bash(nebius compute nvl-instance-group list:*)
  - Bash(nebius compute nvl-instance-group get:*)
  - Bash(jq:*)
---

# Nebius Compute Inventory

Answer "what exists?" across Nebius Compute — instances, disks, filesystems, GPU clusters, images, platforms, nodes, NVLink instance groups — without ever mutating anything.

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

If any of these fails or comes back empty, stop and walk the user through [CLI installation and profile setup](https://docs.nebius.com/cli/install): `curl -sSL https://storage.eu-north1.nebius.cloud/cli/install.sh | bash`, then `nebius profile create --parent-id <project-id>`. **Print those commands for the user to run — do not run them yourself**: the installer writes to their machine and `profile create` opens a browser and blocks. An expired session does not show up here; it surfaces on the first real API call, and re-auth is the same human task.

**Resolve context first — never guess IDs.** Nearly every call needs `--parent-id`, and the CLI does not say which scope it wants:

```bash
nebius profile current                        # which profile is active
nebius config get parent-id  [-p <profile>]   # project-...  (project scope)
nebius config get tenant-id  [-p <profile>]   # tenant-...   (tenant scope)
```

Compute and quota commands are **project**-scoped; capacity advice, capacity block groups, and capacity intervals are **tenant**-scoped. The wrong scope returns empty lists or permission errors, not a helpful message. Pass `-p <profile>` explicitly whenever the user names a profile.

**Output.** Add `--format json` to every call and parse that; the default table output is for humans. On `list` calls add `--all` to disable paging. Never pass `-i`/`--interactive`: it opens alternate-screen pagination and hangs unattended sessions.

**Editing.** Never run `edit` or `edit-by-name`: they open `$EDITOR` and hang in a non-interactive shell. Use `update` with explicit flags or `update -f <file>` instead.

**Async operations.** Mutations return an operation; by default the CLI blocks until it completes. With `--async` it returns an operation id — poll with `nebius <service> <resource> operation wait <operation-id>`.

**Safety tiers.**

| Tier | Operations | Behavior |
|---|---|---|
| A — read | `list`, `get`, `get-by-name`, `batch-get`, `list-*`, `logs`, `--help` | Run freely. |
| B — gated write | `create`, `update`, `start`, `stop`, quota/capacity allowance changes | Print the fully resolved command verbatim, state what it changes and the cost implication, wait for explicit user confirmation, then run it exactly once. Never batch mutations; never retry one after an ambiguous failure. |
| C — refuse | `delete`, `purge`, credential issuance (`iam get-access-token`, access keys), `--impersonate-service-account-id` | Do not run. Print the exact command for the human to run themselves and explain the blast radius. |

**Secrets.** Never print or persist tokens, access keys, or the contents of `~/.nebius/credentials.json`.
<!-- END SHARED PREAMBLE -->

## The shape of every query

```bash
PROJECT=$(nebius config get parent-id)   # or the project the user names
nebius compute <resource> list --parent-id "$PROJECT" --format json --all
```

Resources: `instance`, `disk`, `filesystem`, `gpu-cluster`, `image`, `platform`, `node`, `nvl-instance-group`. Read verbs on each: `list`, `get <id>`, `get-by-name --parent-id ... --name ...`, plus per-resource extras (see [references/resources.md](references/resources.md)).

List responses put resources in `.items[]`, each with `metadata` (id, name, labels), `spec` (desired config), `status` (observed state). Before extracting fields programmatically, run one `get --format yaml` and read the actual field names — the API is versioned and field layouts are ground truth, not memory.

## Common recipes

```bash
# Instances with state — the "what's running" answer
nebius compute instance list --parent-id "$PROJECT" --format json --all \
  | jq -r '.items[] | [.metadata.id, .metadata.name, .status.state] | @tsv'

# One instance in full (spec shows platform/preset, boot disk, network)
nebius compute instance get-by-name --parent-id "$PROJECT" --name my-vm --format yaml

# Valid GPU platforms and presets in this project's region
nebius compute platform list --parent-id "$PROJECT" --format json --all \
  | jq -r '.items[] | .metadata.name'

# Disks with size and type
nebius compute disk list --parent-id "$PROJECT" --format json --all \
  | jq -r '.items[] | [.metadata.id, .metadata.name, .spec.type, (.spec.size_gibibytes // .spec.size_bytes)] | @tsv'

# Public bootable images (OS choices) — note: public images, not project-scoped ones
nebius compute image list-public --format json --all | jq -r '.items[].metadata.name'

# Recent serial/console output of an instance
nebius compute instance logs <computeinstance-id> --format json
```

## Scoping rules that bite

- Everything here is **project**-scoped (`project-...`). An empty list usually means the wrong project or profile, not "nothing exists" — verify with `nebius profile current` and `nebius config get parent-id` before concluding a project is empty.
- Filtering by label or state is client-side: fetch with `--all --format json`, then filter with jq. There is no server-side `--filter` flag.
- `platform list` is also the preflight source of truth for valid `--resources-platform` / `--resources-preset` values used at provisioning time.

## Hand-offs

- "Can I launch X here?" → `nebius-capacity-quotas` (capacity is tenant-scoped and lives elsewhere).
- "Create/resize/start/stop something" → `nebius-compute-provision` (gated writes).
