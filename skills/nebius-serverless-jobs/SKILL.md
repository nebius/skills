---
name: nebius-serverless-jobs
description: Run containerized GPU/CPU batch jobs on Nebius Serverless. Use for "run this container on an H100", "launch a training job", "run my script on a GPU", "why is my job stuck", "cancel that job" - any ai job create, monitor, cancel, or re-run.
license: Apache-2.0
compatibility: Requires the nebius CLI (>=0.12.277) with a configured profile; jq recommended
metadata:
  version: "0.1.0"
allowed-tools:
  - Bash(nebius version:*)
  - Bash(nebius profile current:*)
  - Bash(nebius config get:*)
  - Bash(nebius ai job list:*)
  - Bash(nebius ai job get:*)
  - Bash(nebius ai job get-by-name:*)
  - Bash(nebius ai job logs:*)
  - Bash(nebius compute platform list:*)
  - Bash(nebius billing pricing-policy list:*)
  - Bash(nebius billing pricing-policy get:*)
  - Bash(nebius billing pricing-policy get-by-name:*)
---

# Nebius Serverless Jobs (gated)

Run a container as a one-off GPU/CPU job with the deterministic `nebius ai job create` — validate with `--dry-run`, state the cost, confirm, run once, watch it to a terminal state. Never the interactive `ai create` wizard (hangs unattended sessions), never `job run` (beta), never SDK decorators.

Note: `allowed-tools` above pre-approves only reads. `create`, `cancel`, and `restart` go through the normal permission flow *and* the workflow below — that is intentional.

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

**Serverless tier additions:** `cancel` and `restart` are Tier B (gated). `job delete` removes the record *and* its logs — Tier C, print it for the human. The Serverless commands need CLI **>= 0.12.277**; if `nebius version` is older, ask the user to run `nebius update` first (print it — never run it yourself).

## Choosing platform and preset

There is no `--gpu 1xH100` shorthand yet (MSPDEV-775) — you pick a `--platform` and a `--preset` yourself. **Never silently accept the defaults for GPU work**: the platform default (`gpu-h100-sxm` in eu-north1, `gpu-h200-sxm` elsewhere) is a billing decision the user should see.

| You want | `--platform` | typical `--preset` |
|---|---|---|
| smoke test / validation run | `cpu-d3` | `4vcpu-16gb` |
| 1× H100 | `gpu-h100-sxm` | `1gpu-16vcpu-200gb` |
| 8× H100 | `gpu-h100-sxm` | `8gpu-128vcpu-1600gb` |
| 1–8× H200 | `gpu-h200-sxm` | `1gpu-16vcpu-200gb` / `8gpu-128vcpu-1600gb` |
| 1–4× L40S (lighter/cheaper) | `gpu-l40s-d` or `gpu-l40s-a` | `1gpu-16vcpu-96gb` … |

Availability differs per region (RTX 6000-class platforms exist only in some) — ground truth is `nebius compute platform list --parent-id <project-id> --format json --all` in the target project; the full verified table lives in [references/platform-presets.md](references/platform-presets.md). Unknown platform/preset strings fail validation — that's what `--dry-run` is for.

**Validate cheap, run expensive.** First run of an untested image → `cpu-d3` (or the smallest GPU preset if CUDA is required). `--preemptible` is markedly cheaper but the VM can be stopped at any time — pair it with `--restart-policy on-failure` only if the workload checkpoints; default `never` otherwise.

## Preemptible pricing model (dynamic pricing)

With `--preemptible` you also choose how you pay — exactly one of three mutually-exclusive flags (GPU platforms only). **As of 2026-10-08 a pricing model is mandatory with `--preemptible`** — a bare `--preemptible` no longer defaults silently.

- `--follows-spot-price` — accept the current spot price, **no cap**. Cost floats with the market; the VM is preempted only on capacity, not price.
- `--spot-pricing-policy-id <id>` — cap at a pricing policy's max bid. If the market rises above the bid the VM is **preempted rather than billed higher**.
- `--on-demand` — explicit regular VM (this is the default when `--preemptible` is absent); cannot be combined with `--preemptible`.

State which model you're using and its cost implication in the create confirmation, exactly like the preset — for cost, the calculator (`nebius-billing`) gives the on-demand rate, an **upper bound** for preemptible (billed at the lower, unquoted spot price); a policy caps at its bid, not the charge. To use a capped bid, get an existing policy id with `nebius billing pricing-policy list --parent-id <project-id> --format json` (its platform must match `--platform`); creating or changing a policy is a billing task — see `nebius-billing`.

## Command and args (verified footgun)

`--args` is one string split on **spaces** into container argv — commas are literal, **not** separators. A comma-joined list (`--args "--a,1,--b,2"`) arrives as a single broken token and crashes arg parsing. The image `ENTRYPOINT` is prepended, so the args must be valid for it.

- Right: `--args "--epochs 3 --lr 1e-4"`  ·  Wrong: `--args "--epochs,3,--lr,1e-4"`
- A multi-word `bash -c "…"` can **not** go through `--args` (the whole script must be a single arg). Bake multi-step or piped logic into a script in the image and run it with `--container-command /path/run.sh`.
- `--container-command` overrides the `ENTRYPOINT` (leaves `CMD` alone); `--args` overrides `CMD`.

**Multi-GPU, single node:** pick a multi-GPU preset and drive it with `torchrun`:

```bash
--container-command torchrun \
--args "--standalone --nproc_per_node=8 /app/train.py --batch-size 64"
```

Serverless AI is **one VM per job** — there is no multi-node. For multi-node training use Managed Slurm (Soperator) or Managed Kubernetes with a GPU node group.

## The job create workflow (follow in order, no skipping)

1. **Requirements.** Image reference, command/args, platform+preset, data in/out (volumes → `nebius-serverless-data-secrets`), and an explicit `--timeout`. Anything missing → ask, don't default silently.
2. **Idempotency check.** `nebius ai job get-by-name --name <name> --parent-id <project-id> --format json` — if a job of that name exists, report its state instead of double-creating. Use deterministic names (`<task>-<short-hash>`).
3. **Dry-run.** The same command with `--dry-run` validates without creating anything:
   ```bash
   nebius ai job create --parent-id <project-id> --name train-abc123 \
     --image cr.eu-north1.nebius.cloud/e00example/train:v3 \
     --platform gpu-h100-sxm --preset 1gpu-16vcpu-200gb \
     --timeout 4h --dry-run
   ```
   Fix validation errors here, not on the billable attempt. The full flag surface (every valid flag, commented) is `assets/job-create.sh` — build the command from it rather than improvising flags.
4. **State the cost.** Before creating, tell the user the preset's hourly price (current prices: https://nebius.com/prices) and the worst case implied by `--timeout`. A job bills from provisioning until a terminal state.
5. **Confirmation gate.** Print the fully resolved create command (without `--dry-run`) verbatim, what it launches, and the cost line. Stop and wait for an explicit yes. No confirmation → no job.
6. **Execute once.** **`--timeout` is mandatory, always explicit.** Verified footgun: a job whose image never starts does not fail — it sits in `STARTING`, billing, until the timeout; the default is 24 hours (range 1h–168h). Set it to a realistic runtime bound. For anything longer than a few minutes add `--async` and poll rather than blocking.
7. **Verify.** `nebius ai job get --id <job-id> --format json` — report id, name, and `status.state`.

## Watching a job

States run `PROVISIONING → STARTING → RUNNING →` terminal. Poll with `job get --id <job-id>` on a minute-scale interval — never `logs --follow` (streams forever, hangs unattended sessions; use bounded `--tail`/`--since` instead, and note `job logs` takes the id *positionally*, not via `--id`).

**The STARTING trap (MSPDEV-323):** today `STARTING` shows no image-pull progress and surfaces no pull error, and `logs` is empty with exit 0 the whole time. If a job sits in `STARTING` beyond ~10 minutes, assume the image pull is failing: verify the image reference and registry auth exist, cancel the job (it is billing), fix, re-create. Do not wait out the timeout. Deeper log/error forensics → `nebius-serverless-troubleshooting`.

## Finishing up

- A job that reached a terminal state costs nothing further — leaving the record is fine and preserves logs.
- A job no longer needed but still `PROVISIONING`/`STARTING`/`RUNNING` is **billing** — `cancel` it (Tier B: confirm first): `nebius ai job cancel --id <job-id>`.
- `restart` re-runs the same spec at today's prices — gate it like a create, with the cost line.
- `delete` erases the job *and its logs* — Tier C: print the command and what is lost; the human runs it.
- Never end a task leaving a job in a billable state without telling the user, with its hourly cost.

**Parsing output:** until MSPDEV-778 ships, an empty `job list` prints bare `{}` — treat a missing `items` key as an empty list; and CLI errors print as plain text even with `--format json` — branch on exit code and read stderr, never parse stdout of a failed command.

## Hand-offs

- Volumes, env/registry secrets, getting results out → `nebius-serverless-data-secrets`.
- Stuck/failed job, empty logs, quota or permission errors → `nebius-serverless-troubleshooting`.
- Long-lived serving instead of batch → `nebius-serverless-endpoints`.
- No working auth yet → `nebius-serverless-setup`.
