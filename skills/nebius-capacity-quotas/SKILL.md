---
name: nebius-capacity-quotas
description: Capacity and quota checks for Nebius. Use for "can I launch 8xB200 in us-central1-b", "where is available free GPU capacity", "how much quota do I have", "what's in our reservation", "request a quota increase" - any capacity or quota question.
license: Apache-2.0
compatibility: Requires the nebius CLI (>=0.12) with a configured profile; jq recommended
metadata:
  version: "0.1.0"
allowed-tools:
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
  - Bash(jq:*)
---

# Nebius Capacity & Quotas

Where and whether resources can actually be launched: physical capacity (tenant-wide), reservations (capacity block groups), and quota allowances (per project/region).

<!-- BEGIN SHARED PREAMBLE (generated from shared/preamble.md — edit there, then run scripts/sync-shared.py) -->
## Nebius CLI ground rules

These rules apply to every command in this skill. Full detail lives in the `nebius-cloud-basics` skill.

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

## The one thing everyone gets wrong

Capacity advice is keyed by **tenant NID**, not project. `nebius capacity resource-advice list --parent-id project-...` fails or returns nothing useful. Resolve the tenant first:

```bash
TENANT=$(nebius config get tenant-id)
nebius capacity resource-advice list --parent-id "$TENANT" --format json --all
```

Each advice entry is one (region, fabric, platform, preset) combination reporting current availability for three allocation types: **reserved**, **on-demand**, **preemptible** — already clipped by the tenant's quotas.

## Workflow: "Can I launch 8×B200 in us-central1-b?"

1. Resolve context: `TENANT=$(nebius config get tenant-id)`, `PROJECT=$(nebius config get parent-id)`.
2. Pull advice and filter (platform/region names are data, not guesses — read them from the output):
   ```bash
   nebius capacity resource-advice list --parent-id "$TENANT" --format json --all \
     | jq '.items[] | select((.spec.compute_instance.platform | test("b200")) and (.spec.region | test("us-central1")))'
   ```
   Entry shape (verify on first call, the API is versioned): `spec.region`, `spec.fabric`, `spec.compute_instance.platform`, `spec.compute_instance.preset.name` (+ `.resources` with gpu/vcpu/memory counts), and `status.reserved` / `status.on_demand` / `status.preemptible`, each carrying `availability_level` (e.g. `AVAILABILITY_LEVEL_LOW`, `AVAILABILITY_LEVEL_LIMIT_REACHED`), a numeric `limit` where applicable, and `data_state` freshness.
3. Report all three allocation types with their `availability_level` and `limit` — a "no on-demand" answer with free preemptible capacity is a useful answer.
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
