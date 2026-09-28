---
name: nebius-billing
description: Nebius billing - resource price estimates and preemptible-VM pricing policies. Use for "how much will this cost", "hourly/monthly price of a GPU VM", "estimate the price", "set a max spot price", "create a pricing policy", "cap my preemptible bid", "list pricing policies", "why is my policy BLOCKED" - nebius billing v1alpha1 calculator estimate for prices, and pricing-policy list/create/update/delete for the id behind --spot-pricing-policy-id.
license: Apache-2.0
compatibility: Requires the nebius CLI (>=0.12.277) with a configured profile; jq recommended
metadata:
  version: "0.1.0"
allowed-tools:
  - Bash(nebius version:*)
  - Bash(nebius profile current:*)
  - Bash(nebius config get:*)
  - Bash(nebius billing pricing-policy list:*)
  - Bash(nebius billing pricing-policy get:*)
  - Bash(nebius billing pricing-policy get-by-name:*)
  - Bash(nebius billing v1alpha1 calculator estimate:*)
  - Bash(nebius billing v1alpha1 calculator estimate-batch:*)
---

# Nebius Billing — Pricing Policies

A **pricing policy** caps what you pay for a preemptible (spot) VM. It is a billing resource, one per compute **platform**, whose bid is the **maximum spot price per GPU-hour** you accept. You reference it at launch with `--spot-pricing-policy-id <id>`; if the market rises above the bid the VM is **preempted rather than billed higher**. Managing policies is a billing task and lives here; the launch flags live in the workload skills (`nebius-serverless-jobs`, `nebius-serverless-endpoints`).

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

If any check fails or an ID comes back empty, stop and walk the user through [CLI installation and profile setup](https://docs.nebius.com/cli/install): `curl -sSL https://artifacts.nebius.cloud/cli/install.sh | bash`, then `nebius profile create --parent-id <project-id>`. **Print those commands for the user to run — do not run them yourself**: the installer writes to their machine and the shown federation-profile command opens a browser and blocks. An expired session does not show up here; it surfaces on the first real API call, and re-auth is the same human task.

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

**Safety tiers.** Every operation falls in exactly one tier; when a command fits two, the higher (more restrictive) tier wins.

| Tier | Operations | Behavior |
|---|---|---|
| A — read | `list`, `get`, `get-by-name`, `batch-get`, `list-*`, `logs`, `--help` | Run freely — unless the command emits credential material, which puts it in C whatever its verb. |
| B — gated write | `create`, `update`, `start`, `stop`, quota/capacity allowance changes | Print the fully resolved command verbatim, state what it changes and the cost implication, wait for explicit user confirmation, then run it exactly once. Never batch mutations; never retry one after an ambiguous failure. A command or rendered template carrying a literal secret is never printed and never run: it *accepts* key material, so it is Tier C — replace the literal with a secret selector, or hand the command to the human with the value left as a placeholder. |
| C — refuse | `delete`, `purge`, credential issuance (`iam get-access-token`, access keys; sole exception: `iam auth-public-key generate` is Tier B), any command that emits or accepts token/key material whatever its verb — a raw read whose output carries a token (secret-store payloads, an endpoint spec's auth token) included, `-I`/`--impersonate-service-account-id` (a global flag, valid on *every* command — including otherwise-free reads) | Do not run. Print the exact command for the human to run themselves and explain the blast radius. **Exposure is the line, not handling:** a credential captured into an unechoed shell variable and consumed inside the same compound command stays at its verb's own tier — what Tier C refuses is the value reaching tool output, the transcript, shell history, or a file. So the endpoint smoke test (`TOKEN=$(… | jq -r '.spec.auth_token') && curl -H "Authorization: Bearer $TOKEN" …`) is permitted, while a raw spec dump, `echo $TOKEN`, or a literal token typed into a flag is not. |

**Secrets.** Never print or persist tokens, access keys, or the contents of `~/.nebius/credentials.json`. Some Tier A reads carry credential material in their output: on a token-auth endpoint `ai endpoint get`/`get-by-name` return the bearer token at `.spec.auth_token` and `ai endpoint list` returns it for every item it lists, while job and endpoint specs carry plain `--env` values and registry passwords. Never read those raw — project the fields you need, e.g. `| jq '{id: .metadata.id, state: .status.state, urls: .status.public_endpoints}'`, or `| jq '.items[]? | {…}'` on a list (the `?` matters: an empty list can come back as bare `{}`, and `.items[]` on that aborts with "Cannot iterate over null").
<!-- END SHARED PREAMBLE -->

## Price estimation (calculator) — Tier A read

Answer "what will this cost?" before you launch or set a bid. `nebius billing v1alpha1 calculator` prices a resource **config** and returns hourly + monthly cost — it **creates nothing** (a read). Currency defaults to USD. The **region comes from the resource's parent project** (a uk-south2 project prices uk-south2).

**One resource** (`estimate`) — three resource types, mutually exclusive; use the flags for the one you're pricing:

```bash
# GPU/CPU VM — platform + preset (names from nebius-compute-inventory / `compute platform list`)
nebius billing v1alpha1 calculator estimate \
  --resource-spec-compute-instance-spec-parent-id <project-id> \
  --resource-spec-compute-instance-spec-resources-platform gpu-rtx6000-a \
  --resource-spec-compute-instance-spec-resources-preset 1gpu-24vcpu-218gb \
  --format json
# → {"hourly_cost":{"general":{"total":{"cost":"1.8","cost_rounded":"1.8"}}},"monthly_cost":{..."1314"}}

# Disk — type: network_ssd | network_ssd_io_m | network_ssd_non_replicated | network_hdd
nebius billing v1alpha1 calculator estimate \
  --resource-spec-compute-disk-spec-parent-id <project-id> \
  --resource-spec-compute-disk-spec-type network_ssd \
  --resource-spec-compute-disk-spec-size-gibibytes 1024 --format json

# Filesystem — type: network_ssd | network_hdd
nebius billing v1alpha1 calculator estimate \
  --resource-spec-compute-filesystem-spec-parent-id <project-id> \
  --resource-spec-compute-filesystem-spec-type network_ssd \
  --resource-spec-compute-filesystem-spec-size-gibibytes 1024 --format json
```

Read `hourly_cost.general.total.cost` (full precision) and `.cost_rounded`; `monthly_cost` mirrors it. (Preemptible sub-flags exist on the instance spec — `--resource-spec-compute-instance-spec-preemptible-priority` / `-on-preemption` — but see the spot caveat below.)

**Many at once** (`estimate-batch`) — price a whole stack (VM + boot disk + filesystem) together, with per-resource lines and an aggregated total:

```bash
nebius billing v1alpha1 calculator estimate-batch --format json \
  --resource-specs '[
    {"compute_instance_spec":{"parent_id":"<project-id>","resources":{"platform":"gpu-rtx6000-a","preset":"1gpu-24vcpu-218gb"}}},
    {"compute_disk_spec":{"parent_id":"<project-id>","type":"network_ssd","size_gibibytes":"1024"}}
  ]'
# → resource_costs[] (per item) + total_costs[]; each carries sku_costs[] = per-SKU quantity × unit price
```

`--resource-specs` is required and also accepts `-f <file.json>`. Each element is exactly one of `compute_instance_spec` / `compute_disk_spec` / `compute_filesystem_spec` (or their `*_update_spec` forms), mirroring the create request.

**Offer type** (`--offer-types`, on both verbs): `offer_type_contract_price` prices at the tenant's negotiated **contract** rate; omitted / `offer_type_unspecified` gives the public **list / on-demand** price.

**What it does NOT quote: the live spot price.** Estimates are the on-demand/contract ceiling; a preemptible VM is billed at the dynamic spot price (≤ on-demand). Use `estimate` for the ceiling and to size a pricing-policy bid — then cap below with a policy.

## Discover policies (Tier A)

```bash
nebius billing pricing-policy list --parent-id <project-id> --format json
nebius billing pricing-policy get --id <pricing-policy-id> --format json
```

Read `spec.compute_instance.platform` (which platform it caps), the bid at `spec.pricing.max_price_v1`, and **`status.scheduling_state`**: `SCHEDULING_STATE_BLOCKED` means the bid is **below the current spot price**, so the policy backs nothing until the market drops (or you raise the bid). One policy caps one platform — a job on `gpu-h100-sxm` needs a policy created for `gpu-h100-sxm`.

## Create / raise a bid (Tier B — gated)

Size the bid from the calculator above: the highest legal cap is the on-demand price minus `0.01`; a bid below the live spot price is accepted but starts `BLOCKED`. Print the command, state the bid and what it caps, confirm, run once:

```bash
nebius billing pricing-policy create --parent-id <project-id> \
  --name <name> \
  --compute-instance-spec-v1-platform gpu-h100-sxm \
  --pricing-max-price-v1-max-price 3.515      # per-GPU hourly USD, decimal string, 3-digit precision
```

Change an existing bid with `update`:

```bash
nebius billing pricing-policy update <pricing-policy-id> \
  --pricing-max-price-v1-max-price 4.000
```

Constraints (verified):

- A bid **below** the current market price is accepted but the policy starts/stays `BLOCKED` — it exists but backs no VM until the market falls to it.
- A bid **outside the allowed range** fails `OUT_OF_RANGE`. The **maximum allowed bid is 1 cent below the current on-demand price** (e.g. on-demand `1.80` → max `1.790`) — get on-demand from the calculator above and subtract `0.01` for the highest legal cap.
- The bid can change **only while no VM runs under the policy** (`status.running_vm_count == 0`), else `FAILED_PRECONDITION`. `metadata.name` can change any time; other spec fields are immutable.
- Policies are **tenant-quota-limited** — past the limit `create` fails `RESOURCE_EXHAUSTED`.
- `create`/`update` return an operation; with `--async` poll `nebius billing pricing-policy operation wait <op-id>`.

## Delete (Tier C — refuse, hand to human)

`nebius billing pricing-policy delete --id <id>` — do not run; print it for the human. It fails `FAILED_PRECONDITION` if any VM runs under the policy or a preemption is in flight. Never `edit`/`edit-by-name` (opens `$EDITOR`, hangs an unattended shell).

## How a policy is consumed at launch

On `nebius ai job create`, `nebius ai endpoint create` (and compute VM create), `--preemptible` takes exactly one mutually-exclusive pricing model:

- `--follows-spot-price` — accept the current spot price, no cap (no policy needed).
- `--spot-pricing-policy-id <id>` — cap at this policy's bid.
- `--on-demand` — regular VM (the default when `--preemptible` is absent).

The gated **launch** (dry-run → cost → confirm) stays in `nebius-serverless-jobs` / `nebius-serverless-endpoints`. Full reference: https://docs.nebius.com/signup-billing/manage-pricing-policy

## Hand-offs

- Have a policy id and want to run a workload on it → `nebius-serverless-jobs` / `nebius-serverless-endpoints`.
- "Is spot capacity even available for this platform/region?" (not a price question) → `nebius-capacity-quotas`.
