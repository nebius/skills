---
name: nebius-serverless-endpoints
description: Deploy and manage inference endpoints on Nebius Serverless. Use for "deploy vllm", "serve this model", "expose my container over https", "stop that endpoint", "how much is this endpoint costing" - any ai endpoint create, smoke test, start, stop, or teardown.
license: Apache-2.0
compatibility: Requires the nebius CLI (>=0.12.265) with a configured profile; jq recommended
metadata:
  version: "0.1.0"
allowed-tools:
  - Bash(nebius version:*)
  - Bash(nebius profile current:*)
  - Bash(nebius config get:*)
  - Bash(nebius ai endpoint list:*)
  - Bash(nebius ai endpoint get:*)
  - Bash(nebius ai endpoint get-by-name:*)
  - Bash(nebius ai endpoint logs:*)
  - Bash(nebius compute platform list:*)
---

# Nebius Serverless Endpoints (gated)

Deploy a container as a long-lived inference endpoint with the deterministic `nebius ai endpoint create`, smoke-test its managed URL, and — the part everyone forgets — account for the fact that it **bills wall-clock from create to delete**. Never the interactive `ai create` wizard.

Note: `allowed-tools` above pre-approves only reads. `create`, `start`, `stop`, and `restart` go through the normal permission flow *and* the workflow below.

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

These skills require CLI `0.12.247` or newer. If `nebius version` is older, stop and ask the user to update the CLI before relying on the commands or schemas below.

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

**Serverless tier additions:** `restart` is Tier B like `start`/`stop`. `endpoint delete` is Tier C — but see *The idle-cost rule*: when an endpoint should die, saying so loudly is part of this skill's job. Commands here need CLI **>= 0.12.265**; if older, ask the user to run `nebius update` first (print it — never run it yourself).

## The idle-cost rule (read this first)

An endpoint bills for every hour between `create` and `delete` — including idle time, including `STARTING`. A forgotten single-H100 endpoint is on the order of **$90+/day** (verify current prices at https://nebius.com/prices). Therefore, non-negotiable:

1. Immediately after every deploy, state the endpoint's hourly and daily cost to the user.
2. The moment an endpoint is no longer needed, `stop` it (gated) or hand the user the `delete` command.
3. **Never end a task with an endpoint running without telling the user it is running and what it costs per hour.** Silence here is the #1 way this skill can hurt someone.

## Ports and URLs

`--container-port HOST[:CONTAINER][/http|tcp|udp]` (repeatable, default protocol http):

- **http** → a managed `https://` URL per port; gRPC works over the same URL.
- **tcp** → a managed `tls://HOST:443` URL.
- **udp** → no managed URL.

The managed URLs are the canonical access path. `--public` (a raw public IP on the VM) is independent of them and almost never what you want — don't add it unless the user explicitly asks for a raw IP, and say why the managed URL is preferable (TLS, stable name, auth).

## Endpoint auth

Default is `--auth none` — an open endpoint on the internet. For anything beyond a throwaway demo, recommend `--auth token`:

- `--auth token` alone → the platform generates a random token (retrievable from the endpoint spec, not printed by you).
- `--token-secret <selector>` → token from MysteryBox (`AUTH_TOKEN` payload key) — the right choice for scripts; see `nebius-serverless-data-secrets`.
- `--token <value>` → caller-supplied; fine interactively, but never write the literal into scripts or logs.

## The deploy workflow (follow in order, no skipping)

1. **Requirements.** Image, port(s)+protocol, platform+preset (same catalog and discovery as jobs — see `nebius-serverless-jobs` or `nebius compute platform list`), auth choice, volumes/secrets.
2. **Idempotency check.** `nebius ai endpoint get-by-name --name <name> --parent-id <project-id> --format json` — if it exists, report state and URL instead of double-creating (a duplicate is a second bill).
3. **Dry-run.**
   ```bash
   nebius ai endpoint create --parent-id <project-id> --name vllm-abc123 \
     --image cr.eu-north1.nebius.cloud/e00example/vllm:latest \
     --platform gpu-h100-sxm --preset 1gpu-16vcpu-200gb \
     --container-port 8000/http --auth token --dry-run
   ```
4. **State the cost** — hourly and per-day, explicitly flagged as accruing until delete, not until "done".
5. **Confirmation gate.** Full command verbatim, what it deploys, the recurring cost line. Explicit yes or no mutation.
6. **Execute once**, prefer `--async` + poll `endpoint get --id <id>` (model-pulling images take minutes; never `logs --follow`).
7. **Smoke test before declaring success.** Get the managed URL from `endpoint get --format json`, then:
   ```bash
   curl -sS -m 15 -H "Authorization: Bearer <token>" https://<managed-url>/<health-or-infer-path>
   ```
   A deploy is not done until the URL answers. If it doesn't → `nebius-serverless-troubleshooting`, and remember the meter is running while you debug.
8. **Report**: id, name, state, URL, and the cost line (rule 1 above).

## Lifecycle

- `stop` (Tier B) parks the endpoint; `start` (Tier B) resumes it. Stopped endpoints stop the GPU bill — stopping is the default answer to "keep it around, not serving".
- There is **no `endpoint update`** — changing image/preset/ports means create-new → smoke-test → then hand the user delete of the old one. Say this before starting so nobody expects in-place edits.
- `delete` (Tier C): print the command, note the managed URL dies with it.
- `ssh` into the endpoint exists for live debugging — last resort, see `nebius-serverless-troubleshooting`.

**Parsing output:** until MSPDEV-778 ships, an empty `endpoint list` prints bare `{}` — a missing `items` key means empty; errors print as plain text even with `--format json` — branch on exit code, read stderr.

## Hand-offs

- Model weights via S3 volumes, tokens/registry creds from MysteryBox → `nebius-serverless-data-secrets`.
- Endpoint won't come up, empty logs, quota errors → `nebius-serverless-troubleshooting`.
- Batch work instead of serving → `nebius-serverless-jobs`.
- No working auth yet → `nebius-serverless-setup`.
