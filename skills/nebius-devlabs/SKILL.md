---
name: nebius-devlabs
description: Creates and operates Nebius Devlabs, interactive development environments on Serverless infrastructure. Use for "create a devlab", "launch a GPU notebook", "connect to my devlab", "stop or restart my devlab", or "debug a failed job in a devlab". Covers templates, custom images, persistent workspaces, managed web access, SSH, and diagnostics.
license: Apache-2.0
compatibility: Requires the nebius CLI (>=0.12.277) with a configured profile; jq recommended
metadata:
  version: "0.1.0"
allowed-tools:
  - Bash(nebius version:*)
  - Bash(nebius profile list:*)
  - Bash(nebius profile current:*)
  - Bash(nebius config get:*)
  - Bash(nebius ai devlab template list:*)
  - Bash(nebius ai devlab list:*)
  - Bash(nebius ai devlab get:*)
  - Bash(nebius ai devlab get-by-name:*)
  - Bash(nebius ai devlab logs:*)
  - Bash(nebius ai devlab operation get:*)
  - Bash(nebius compute platform list:*)
---

# Nebius Devlabs

Operate interactive development environments with `nebius ai devlab`. Use a discovered template or a custom container, preserve the workspace, and make the running cost and access method clear. Batch jobs and inference endpoints have separate lifecycles; do not copy their flags into Devlab commands.

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

## Command contract

This skill uses **CLI 0.12.277 as its verified compatibility floor**, not a claim about the first release of Devlabs. Check `nebius ai devlab create --help` when the installed version differs. `create`, `stop`, and `restart` are Tier B; `delete` is Tier C. SSH runs a shell and is not a pre-approved read.

- `devlab list` is project-scoped and has no `--all`; `devlab template list` lists global templates and takes no `--parent-id`.
- Create uses the flags in [assets/devlab-create.sh](assets/devlab-create.sh). Do not assume the global `-f` option provides a Devlab request schema.
- There is no Devlab `start`, `update`, or `cancel` command in the verified surface. Use `restart` or `stop` as appropriate.
- There is **no workload runtime limit** on Devlab create. Global `--timeout` only limits the CLI request; it does not stop the Devlab or bound its bill. Do not invent `--preemptible`, `--restart-policy`, endpoint `--auth token`, or `--token-secret` flags.

## Discover or inspect

Use the selected profile consistently, including template discovery:

```bash
nebius ai devlab template list -p <profile> --format json
nebius ai devlab list -p <profile> --parent-id <project-id> --format json
nebius ai devlab get-by-name -p <profile> --parent-id <project-id> --name <name> --format json
nebius ai devlab get -p <profile> --id <devlab-id> --format json
```

Summarize metadata, platform/preset, workspace path, state, state details, and endpoint URLs; avoid dumping the complete spec or operation request. Do not request an API `SECRET` view: the default view masks environment values and omits injected-file contents. Treat missing `items` on a successful list as empty; distinguish API/auth failures from an empty project. Do not create a replacement when a lookup fails for permissions or connectivity.

## Create workflow

1. **Resolve the environment.** Choose either a template from `template list` or an image plus `--primary-route-port`. Templates declare the image, primary route, and default workspace path; inspect their input definitions before supplying repeatable `--input KEY=VALUE`. `--image` and `--template` are mutually exclusive. Templates reject `--container-command`, `--args`, and `--working-dir`; inputs require a template. For failed-job debugging, read [references/workspaces-and-access.md](references/workspaces-and-access.md) first.
2. **Resolve resources and data.** Name the project/profile, platform, preset, disk size, workspace path, access method, and intended session duration. Read `nebius compute platform list --parent-id <project-id> -p <profile> --format json --all`; match the platform against `.items[].metadata.name` and its preset against that same platform's `.spec.presets[].name`. Resolve an unsupported pair before submitting; catalog failure is not proof of an invalid pair. Do not silently accept GPU defaults or substitute a different billable preset.
3. **Check for an existing Devlab.** Use `get-by-name` in the same project/profile. If found, report its state and reuse or propose restarting it according to the user's intent. A name check reduces accidental duplicates; it does not guarantee idempotency after a timeout.
4. **Prepare and validate.** Compose the exact flags from the asset and run with `--dry-run`. Use `--auth-token-secret <selector>` for an existing MysteryBox secret containing `AUTH_TOKEN` when token access is needed. Keep secret values out of arguments, files, and output. Use `--env-secret` and `--registry-secret` for workload credentials. Resolve validation errors before a billable attempt; do not silently change template, image, or authentication to make validation pass.
5. **Make the launch reviewable.** Show the resolved command without `--dry-run`, the resource sizes, access exposure, and an hourly compute/storage estimate from current [Nebius prices](https://nebius.com/prices). If pricing cannot be established, say so instead of inventing a total. Explain the intended stop point and that idle time can remain billable; the session duration is a plan, not an automatic shutdown. Apply the Tier B confirmation gate.
6. **Execute once and verify.** Prefer `--async`; track the returned operation with `devlab operation get --id <operation-id>`, or a bounded `operation wait`. Then get the Devlab by returned resource ID or resolved name. A successful create operation alone does not prove the notebook or IDE is ready. Report actual state and managed URLs, and verify the requested UI when access is available. If authentication requires the user, report UI verification as pending.

## Connect, preserve work, and diagnose

Read [references/workspaces-and-access.md](references/workspaces-and-access.md) for web authentication, SSH, mounts, and `--from-job`. Put notebooks, code, and outputs that need to persist under the configured workspace; do not promise that arbitrary container filesystem changes survive lifecycle operations.

Use bounded diagnostics:

```bash
nebius ai devlab get -p <profile> --id <devlab-id> --format json
nebius ai devlab logs <devlab-id> -p <profile> --tail 100 --since 30m
nebius ai devlab operation get -p <profile> --id <operation-id> --format json
```

Inspect state details and instance states, then image/registry access, template inputs or web process/port, mount overlap, capacity/quota, and subnet permissions as relevant. Empty logs do not establish health or prove an image-pull failure. Do not automatically transplant the job-specific STARTING recovery timer or cancel/recreate workflow. A stuck Devlab may contain work: diagnose before restarting, and never delete/recreate as a troubleshooting shortcut.

## Stop, restart, and finish

- **Stop:** get current state, save work and account for interrupted sessions, then gate `nebius ai devlab stop --id <devlab-id> -p <profile> --async`. Verify operation completion and resource state. Stopping is distinct from deletion; do not report all charges as zero without checking retained-storage pricing.
- **Restart/resume:** inspect first, state interruption and renewed running cost, then gate `nebius ai devlab restart --id <devlab-id> -p <profile> --async`. Re-read endpoints and verify readiness. Never invent `devlab start`.
- **Delete:** Tier C. Show `nebius ai devlab delete --id <devlab-id> -p <profile>` for the human, explain potential loss of the workspace and resource record, and establish an export/backup plan before deletion. Do not promise recovery or storage retention after delete.
- **Ambiguous mutation failure:** inspect the operation and resource before any further write. Do not replay create, stop, or restart automatically.
- Finish with the Devlab ID/name, actual state, connection method, workspace path, and remaining cost exposure. If it is still running, say so and give the stop command; do not stop an environment the user intends to keep using.

## Sources

The command asset follows local CLI 0.12.277 help and the official [create reference](https://docs.nebius.com/cli/reference/ai/devlab/create). Response masking follows the [Devlab Get API](https://docs.nebius.com/rest-api/ai/v1/devlabs/get). Lifecycle operations: [stop](https://docs.nebius.com/rest-api/ai/v1/devlabs/stop), [restart](https://docs.nebius.com/rest-api/ai/v1/devlabs/restart), [delete](https://docs.nebius.com/rest-api/ai/v1/devlabs/delete). These API pages do not establish a Devlab-specific storage-retention or pricing guarantee; verify those terms before making one.
