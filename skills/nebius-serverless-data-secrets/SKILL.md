---
name: nebius-serverless-data-secrets
description: Data and credentials for Nebius Serverless jobs and endpoints. Use for "mount an s3 bucket", "pass an api key to my container", "pull from a private registry", "inject a config file", "where do my results go" - any volume, env secret, registry auth, or artifact egress question.
license: Apache-2.0
compatibility: Requires the nebius CLI (>=0.12.265) with a configured profile; jq recommended
metadata:
  version: "0.1.0"
allowed-tools:
  - Bash(nebius version:*)
  - Bash(nebius profile current:*)
  - Bash(nebius config get:*)
  - Bash(nebius ai job get:*)
  - Bash(nebius ai job get-by-name:*)
  - Bash(nebius ai endpoint get:*)
  - Bash(nebius ai endpoint get-by-name:*)
---

# Nebius Serverless Data & Secrets

How data and credentials get into and out of `ai job`/`ai endpoint` containers: S3 volumes, MysteryBox-backed secrets, injected config files. These are all flags on `create` — the create itself stays gated by `nebius-serverless-jobs`/`nebius-serverless-endpoints`; this skill supplies the flags and their traps.

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

**Version floor:** these flags need CLI **>= 0.12.265**; if `nebius version` is older, ask the user to run `nebius update` first (print it — never run it yourself).

## S3 volumes (the main data path)

```
--volume s3://BUCKET:/container_path[:MODE[:PROFILE]]     # MODE: rw | ro (default rw)
```

- Repeatable; also accepts plain `SOURCE:CONTAINER_PATH[:MODE]` mounts.
- Mount inputs `ro` unless the workload writes back — a stray `rw` on a shared dataset bucket is how training runs corrupt inputs.
- `PROFILE` names AWS credentials (default `default`). For secret-backed S3 auth use `PROFILE@SECRET_SELECTOR` — the credentials come from MysteryBox, nothing lands on disk in the container spec.
- A `SECRET_SELECTOR` anywhere in this skill is: a secret name, secret ID, version ID, or `SECRET_ID@VERSION_ID`.

## Secrets into the container

- **Env secrets:** `--env-secret KEY=SECRET_SELECTOR` (repeatable). Plain `--env KEY=VALUE` is for non-secret config only — an `--env HF_TOKEN=hf_…` lands in the resource spec, readable by anyone who can `get` it.
- **Private registry:** `--registry-secret <selector>` — a MysteryBox secret with `REGISTRY_USERNAME` and `REGISTRY_PASSWORD` payload keys. **Never `--registry-username`/`--registry-password` in scripts or agent-composed commands** (plaintext in the spec and in shell history; the flags are headed for deprecation, MSPDEV-347). If no such secret exists yet, creating one in MysteryBox is the human's step — print what the payload keys must be named.
- The same selectors serve endpoint auth tokens (`--token-secret`, payload key `AUTH_TOKEN`) — see `nebius-serverless-endpoints`.

## Config files

```
--inject-file LOCAL_PATH:CONTAINER_PATH        # repeatable
```

Three hard limits, all verified: **64 KiB max**, **read-only** inside the container, `CONTAINER_PATH` must be **absolute**. Right for a config or small manifest; wrong for anything bigger or writable — that's an S3 volume. Never inject a file that contains a credential — that's `--env-secret`'s job.

## Getting results out

Write artifacts to an `rw` S3 volume path — that is the supported egress; the container filesystem vanishes with the job.

Bucket-side operations (download results locally, pre-upload datasets, list objects) have **no native CLI path** — there is no `nebius storage cp` (known gap). Use the AWS CLI against Nebius Object Storage with the bucket's endpoint and credentials:

```bash
aws s3 cp s3://BUCKET/results/ ./results/ --recursive --endpoint-url <storage-endpoint>
```

Setting up those AWS credentials is a one-time human step (access keys are Tier C credential issuance) — point the user at the console's Object Storage access-key page rather than minting keys yourself.

## Checking what a workload actually mounts

`nebius ai job get --id <id> --format json` (same for endpoints) shows the resolved volumes, env names, and secret *selectors* — never the secret values. Use it to debug "my file isn't there" before touching the container: nine times out of ten the container path or mode is wrong in the spec.

## Hand-offs

- Composing the actual `create` (gating, dry-run, cost) → `nebius-serverless-jobs` / `nebius-serverless-endpoints`.
- Auth for the CLI itself (service accounts, tokens) → `nebius-serverless-setup`.
- Mount present but empty, permission errors on the bucket → `nebius-serverless-troubleshooting`.
