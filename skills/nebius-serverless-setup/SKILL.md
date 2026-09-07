---
name: nebius-serverless-setup
description: Auth and project bootstrap for Nebius Serverless in agent, CI, or script contexts. Use for "set up nebius for CI", "authenticate an agent", "create a service account key", "get a token without a browser" - any non-interactive credential setup before running jobs or endpoints.
license: Apache-2.0
compatibility: Requires the nebius CLI (>=0.12.265) with a configured profile; jq recommended
metadata:
  version: "0.1.0"
allowed-tools:
  - Bash(nebius version:*)
  - Bash(nebius profile list:*)
  - Bash(nebius profile current:*)
  - Bash(nebius config get:*)
  - Bash(nebius iam whoami:*)
  - Bash(nebius iam service-account list:*)
  - Bash(nebius iam service-account get:*)
  - Bash(nebius iam service-account get-by-name:*)
  - Bash(nebius ai job list:*)
---

# Nebius Serverless Setup

Get a machine (agent, CI runner, script) authenticated against Nebius without a browser, and verify it can reach the Serverless AI API. Interactive human setup (`nebius profile create` with a browser) is not this skill — hand that off to `nebius-cloud-basics`.

Note: `allowed-tools` above pre-approves only reads. Creating a service account and generating its key are gated writes that go through the confirmation flow below.

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

## Version floor for Serverless

The Serverless skills need CLI **0.12.265 or newer** (`--dry-run` on `ai job/endpoint create`, `iam auth-public-key generate`). Check `nebius version` first; if older, stop and ask the user to run `nebius update` before anything else — it rewrites the CLI binary on their machine, so print it for them, never run it yourself.

## Which auth path?

- **A human at a terminal** → `nebius profile create` (opens a browser). Hand off to `nebius-cloud-basics`; do not attempt it yourself — it blocks on the browser.
- **An agent, CI job, or script** → a service account with a generated auth key. That is this skill.
- **Already authenticated?** Check before creating anything: `nebius iam whoami --format json` succeeding means the current profile works — use it and skip to *Verify access*.

## Agent/CI path: service account + generated key

1. **Pick or create the service account.** List first: `nebius iam service-account list --parent-id <project-id> --format json`. Reuse an existing SA when one fits. Creating one is a gated write:
   ```bash
   nebius iam service-account create --parent-id <project-id> --name <sa-name>
   ```
   Recommend a dedicated SA with only the roles the task needs (Serverless jobs/endpoints), not an account with project-wide admin. Granting roles is IAM surgery — print the console path or `nebius iam` commands for the user rather than improvising grants. The exact mechanism (Nebius has **no `role-binding`** — roles are granted through **group membership**) is in [references/iam-grants.md](references/iam-grants.md); those commands are the human's to run, not the agent's.

2. **Generate the key.** One command creates the keypair, uploads the public half, and writes a credentials JSON — nothing secret is printed to stdout:
   ```bash
   nebius iam auth-public-key generate \
     --service-account-id <sa-id> \
     --expires-at <RFC3339, e.g. 2027-02-26T00:00:00Z> \
     --output <path>/credentials.json
   ```
   This issues a credential, so treat it as a gated write: show the command, state which SA it targets and when the key expires, get an explicit yes, run it once. **Always pass `--expires-at`** — about 6 months out is the sensible default; an unbounded key is a standing liability. Write `--output` inside the CI secret store or a `0600` directory, never into the repo.

3. **Wire it up.** Either create a non-interactive profile from the file:
   ```bash
   nebius profile create ci --service-account-file-path <path>/credentials.json --parent-id <project-id>
   ```
   or, where a profile is impractical (minimal containers), export an IAM token via the environment: the CLI honors `NEBIUS_IAM_TOKEN`. Obtaining a raw token (`iam get-access-token`) prints a secret and stays Tier C — leave that command to the human and prefer the profile path.

## Verify access

Prove the credentials work with the cheapest Serverless read before declaring setup done:

```bash
nebius ai job list --parent-id <project-id> --format json
```

An empty result is success (note: until MSPDEV-778 ships, an empty list prints bare `{}`, not `{"items": []}` — missing `items` means empty, not broken). `PermissionDenied` means the SA lacks a role on the project — name the gap, don't retry.

## Never do

- Never print, log, or `cat` the credentials JSON, the private key, or any token. Not even excerpts, not even to "verify it worked" — `iam whoami` is the verification.
- Never commit credentials files; check `.gitignore` covers the output path before generating into a working tree.
- Never generate a key without `--expires-at`.
- Never reuse one SA across unrelated projects "for convenience" — key compromise then crosses project boundaries.

## Hand-offs

- Human/interactive login, profile juggling, `--parent-id` confusion → `nebius-cloud-basics`.
- Ready to run something → `nebius-serverless-jobs` (batch) or `nebius-serverless-endpoints` (serving).
- Secrets *inside* the workload (registry auth, env secrets) → `nebius-serverless-data-secrets`.
