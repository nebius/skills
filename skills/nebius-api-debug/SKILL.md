---
name: nebius-api-debug
description: Use when investigating failed Nebius CLI commands, Terraform provider operations, or SDK calls.
compatibility: Requires the affected Nebius tool and permission to reproduce the failed operation.
---

# Nebius API tool diagnostics

Collect debug log + request Trace IDs before assigning failure to client/service.
Shared CLI rules apply to CLI only; SDK/provider diagnostics need no CLI setup.

## Secrets in diagnostic logs

Nebius tools designed to omit raw secrets/credentials from logs.
Diagnostic fragments may appear: shortened token, JWT without signature.
Keep these diagnostic fragments; credential resemblance alone no reason to remove. Useful for auth diagnosis.
Design excludes arbitrary app logs, custom handlers, third-party output.
Inspect dump; redact intact credentials before presenting to user.
Never dump credential files or add raw tokens to command/reproduction. Keep Trace IDs + useful request context.

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

**Tool errors.** Use the `nebius-api-debug` skill for debug logs and request Trace IDs.

**Secrets.** Never print or persist tokens, access keys, or the contents of `~/.nebius/credentials.json`. Some Tier A reads carry credential material in their output: on a token-auth endpoint `ai endpoint get`/`get-by-name` return the bearer token at `.spec.auth_token` and `ai endpoint list` returns it for every item it lists, while job and endpoint specs carry plain `--env` values and registry passwords. Never read those raw — project the fields you need, e.g. `| jq '{id: .metadata.id, state: .status.state, urls: .status.public_endpoints}'`, or `| jq '.items[]? | {…}'` on a list (the `?` matters: an empty list can come back as bare `{}`, and `.items[]` on that aborts with "Cannot iterate over null").
<!-- END SHARED PREAMBLE -->

## Collect evidence

1. Record tool version, exact command/minimal code, UTC time, endpoint, region, auth method.
   Include relevant config + inputs; omit credential values.
2. Enable affected tool debug logs below. Keep stdout, stderr, exit status.
   Prefer original failing inputs. If comparison needs changed args, inputs, config, or code, record what changed + why.
3. Reproduce once within existing authorization. Never replay mutation with unknown outcome just for logs.
   Replay unsafe or unauthorized → collect existing logs; state skipped reproduction + missing evidence.
   Command prompts interactively for input/approval → collect existing logs or hand reproduction to user with prompts visible. Never bypass approval for logs.
4. Collect every request Trace ID: retries, auth calls, operation polling included.
   Keep Request IDs, operation IDs, method + timestamp per ID when available.
   Sources: response `x-trace-id`, SDK request metadata, CLI `Trace ID`.
   Local parse/config/connection failure may lack server Trace ID. State absence; never invent IDs.
5. Prepare full debug dump + reproduction details as artifacts for user.
   Present absolute file paths or available download links, versions, Trace IDs + missing-evidence notes.
   Full logs required; screenshot/final error alone insufficient.

Keep original working directory. Fresh private output directory per capture: no overwritten evidence or reused loose permissions.
Map each ID to producing attempt.

Finish with prepared artifacts + file locations shown to user. Ticket creation/upload workflow outside this skill; do not search for it.

## CLI

CLI error reproduction/evidence collection: always `--debug`.
Keep original profile, args, input files; change only for controlled comparison.

Capture stdout + debug stderr separately; keep JSON parseable.
Credential-bearing stdout: replace `>"$capture_dir/cli.stdout.log"` with `>/dev/null`. Never save raw response.

Replace `ORIGINAL_ARGUMENTS` with original command args.

```bash
(
  umask 077
  capture_dir=$(mktemp -d) || exit 1
  printf 'Log directory: %s\n' "$capture_dir"
  cli_status=0
  nebius --debug ORIGINAL_ARGUMENTS >"$capture_dir/cli.stdout.log" 2>"$capture_dir/cli.debug.log" || cli_status=$?
  printf 'exit_status=%s\n' "$cli_status" >"$capture_dir/cli.exit.txt"
)
```

Artifacts: captured files + CLI version. Extract Trace IDs from every captured output file; stdout discarded → debug log only.
User collecting evidence → give exact failing command with `--debug` + capture steps.

## Terraform provider

Enable affected provider logs only; avoid debug across other providers/Terraform Core.
Unattended capture: supply required variables. Use `-input=false` only when authorized reproduction stays equivalent.
Public Nebius provider: `TF_LOG_PROVIDER_NEBIUS=DEBUG`:

Replace `ORIGINAL_ARGUMENTS` with original command args.

```bash
(
  umask 077
  capture_dir=$(mktemp -d) || exit 1
  printf 'Log directory: %s\n' "$capture_dir"
  tf_status=0
  TF_LOG_PROVIDER_NEBIUS=DEBUG terraform ORIGINAL_ARGUMENTS >"$capture_dir/terraform.stdout.log" 2>"$capture_dir/terraform.debug.log" || tf_status=$?
  printf 'exit_status=%s\n' "$tf_status" >"$capture_dir/terraform.exit.txt"
)
```

Other provider: supported `TF_LOG_PROVIDER_<NAME>`, uppercase provider name.
Check `TF_LOG` + `TF_LOG_PROVIDER`: may override provider-specific level.
Use `TRACE` only when `DEBUG` lacks needed detail. Keep configured `TF_LOG_PATH` file too.
Never add `apply`, `destroy`, `-auto-approve`, or second mutation just for logs.
Artifacts: debug dump, Terraform version, provider version from `.terraform.lock.hcl`, relevant HCL.
Collect Trace IDs for all API requests in failed resource operation.

## SDKs

Enable affected SDK debug logs before reproduction.
Keep request + error objects; retain response metadata on failure.
Read [SDK logging](references/sdk-logging.md): Go, Python, JavaScript/TypeScript setup + Trace IDs.
Other SDK: inspect installed version logger/request-metadata APIs; invent no debug flag.
App logs obscure request sequence → dedicated SDK log file/handler.
Artifacts: dump, SDK/runtime versions, minimal reproduction.
