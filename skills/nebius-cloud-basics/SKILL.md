---
name: nebius-cloud-basics
description: Foundation for the nebius CLI. Check before any other Nebius task, or if a nebius command needs the right profile, --parent-id, or output format, or fails with an unclear error.
license: Apache-2.0
compatibility: Requires the nebius CLI (>=0.12) with a configured profile; jq recommended
metadata:
  version: "0.1.0"
allowed-tools:
  - Bash(nebius version:*)
  - Bash(nebius profile list:*)
  - Bash(nebius profile current:*)
  - Bash(nebius profile active:*)
  - Bash(nebius config get:*)
  - Bash(nebius config list:*)
  - Bash(nebius iam whoami:*)
  - Bash(jq:*)
---

# Nebius Cloud Basics

Consult this skill for any nebius CLI question the other `nebius-*` skills don't cover.
Everything the other `nebius-*` skills assume: how to pick a profile, resolve the right `--parent-id`, get machine-readable output, wait on operations, and stay inside the safety tiers.

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

## Grounding sequence

Run this once at the start of any Nebius session before acting:

```bash
nebius version                                    # CLI present and which version (a subcommand — there is no --version flag)
nebius profile list                               # available profiles; [default] marks the active one
nebius profile current                            # profile actually in effect
nebius config get parent-id --format json         # default project for that profile
nebius config get tenant-id --format json         # tenant for that profile
nebius iam whoami --format json                   # confirm identity/auth works
```

If the user names a profile ("use the testing profile"), append `-p <profile>` to **every** subsequent command — the active profile is easy to forget mid-session and mixing scopes across profiles is the top source of confusing permission errors.

Some profiles have no `parent-id` or `tenant-id` configured — `config get` then returns an error or empty value. In that case ask the user which project/tenant to target; do not borrow IDs from another profile.

## Which --parent-id does a command want?

| Command family | Scope to pass |
|---|---|
| `compute *` (instances, disks, filesystems, gpu-clusters, images, platforms) | project (`project-...`) |
| `quotas quota-allowance *` | project (or tenant for tenant-wide quotas) |
| `capacity resource-advice list` | **tenant** (`tenant-...`) — required to compute quota-clipped availability |
| `capacity capacity-block-group *`, `capacity capacity-interval *` | **tenant** |
| `capacity capacity-allowance *` | project |

## Decoding errors

- **Permission denied / empty list where resources should exist** — usually the wrong `--parent-id` scope (project vs tenant) or the wrong profile. Re-run the grounding sequence before retrying.
- **Authentication errors** — the profile's session expired. Re-auth is a human task (`nebius profile create` opens a browser); tell the user, don't attempt it.
- **Unknown flag / command** — the CLI is auto-generated and changes between versions. Treat `nebius <cmd> --help` as ground truth, never a memorized flag list.
- The CLI retries transient errors itself (`--retries`, default 3). Do not wrap read calls in your own retry loop; never retry a mutation after an ambiguous failure — check actual state with `get`/`list` first.

## Going deeper

- [references/context-resolution.md](references/context-resolution.md) — profiles, `~/.nebius/config.yaml`, NID formats, auth types, multi-profile work
- [references/output-and-paging.md](references/output-and-paging.md) — `--format json|yaml|jsonpath`, jq recipes, `--page-size`/`--page-token`/`--all`
- [references/operations.md](references/operations.md) — async operations, `operation wait`, polling patterns, timeouts and retries
- [references/safety-tiers.md](references/safety-tiers.md) — the full tier table with rationale and the complete refuse list
