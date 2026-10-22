---
name: nebius-api-debug
description: Use when investigating failed Nebius CLI commands, Terraform provider operations, or SDK calls.
compatibility: Requires the affected Nebius tool and permission to reproduce the failed operation.
---

# Nebius API tool diagnostics

Collect a debug log and request Trace IDs before attributing a failure to a client or service.
Apply the shared CLI rules only when using the CLI; SDK and provider diagnostics do not require CLI setup.

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

1. Record the tool version, exact command or minimal code, UTC time, endpoint, region, and authentication method.
   Include relevant configuration and inputs, with credential values omitted.
2. Enable the affected tool's debug logging as described below. Preserve stdout, stderr, and the exit status.
   Prefer the original failing inputs. Record any changes made for a controlled comparison.
3. Reproduce once within the existing authorization. Do not repeat an ambiguous mutation just to obtain a debug log.
   If replay is unsafe, collect existing logs and state which evidence is unavailable.
4. Collect every request's Trace ID, including retries, authentication calls, and operation polling.
   Also record Request IDs, operation IDs, and the method and timestamp for each ID when available.
   Use response metadata such as `x-trace-id`, SDK request metadata, or the CLI's printed `Trace ID`.
   A local parse, configuration, or connection failure may have no server Trace ID. State that explicitly; never invent one.
5. Attach the complete debug log dump and reproduction details to the ticket being investigated.
   List the Trace IDs in the ticket text; a screenshot or the final error line alone is insufficient.
   If no ticket is in scope, provide the log files and IDs for handoff instead of creating an unrelated ticket.

Keep logs for distinct attempts separate. Correlate each ID with the attempt that produced it.

## CLI

Always use `--debug` when reproducing a CLI error or collecting CLI failure evidence.
Keep the original profile, arguments, and input files unless the comparison requires a change.

Capture stdout and debug stderr separately so JSON output remains parseable.
If normal stdout contains credentials, replace `>cli.stdout.log` with `>/dev/null`; do not save the raw response.

Replace `ORIGINAL_ARGUMENTS` with the original command arguments.

```bash
(
  umask 077
  cli_status=0
  nebius --debug ORIGINAL_ARGUMENTS >cli.stdout.log 2>cli.debug.log || cli_status=$?
  printf 'exit_status=%s\n' "$cli_status" >cli.exit.txt
)
```

Include the captured files and the CLI version in the ticket. Extract Trace IDs from both output files.
When asking a user to collect evidence, give the exact failing command with `--debug` and the capture instructions.

## Terraform provider

Enable the affected provider's logging, rather than enabling debug for every provider and Terraform Core.
For the public Nebius provider, use `TF_LOG_PROVIDER_NEBIUS=DEBUG`:

Replace `ORIGINAL_ARGUMENTS` with the original command arguments.

```bash
(
  umask 077
  tf_status=0
  TF_LOG_PROVIDER_NEBIUS=DEBUG terraform ORIGINAL_ARGUMENTS >terraform.stdout.log 2>terraform.debug.log || tf_status=$?
  printf 'exit_status=%s\n' "$tf_status" >terraform.exit.txt
)
```

For another provider name, use its supported `TF_LOG_PROVIDER_<NAME>` variable with the uppercase provider name.
Check existing `TF_LOG` and `TF_LOG_PROVIDER` settings: they can override the provider-specific level.
Use `TRACE` only if `DEBUG` omits the needed information. Preserve any configured `TF_LOG_PATH` file as well.
Do not add `apply`, `destroy`, `-auto-approve`, or a second mutation solely to collect logs.
Attach the debug dump, Terraform version, provider version from `.terraform.lock.hcl`, and relevant HCL.
Collect Trace IDs for all API requests involved in the failed resource operation.

## SDKs

Enable debug logging in the affected SDK before reproducing the call.
Keep its request and error objects so response metadata remains available on failure.
Read [SDK logging](references/sdk-logging.md) for Go, Python, and JavaScript/TypeScript setup and Trace ID access.
For any other SDK, inspect its installed version's logger and request-metadata APIs; do not invent a debug flag.
Route SDK logs to a dedicated file or handler when application logs would obscure the request sequence.
Attach that dump, SDK/runtime versions, and a minimal reproduction to the ticket.

## Secrets in diagnostic logs

Nebius tools are designed to keep raw secrets and credentials out of their logs.
They can log diagnostic fragments, such as a shortened token or a JWT without its signature.
Do not remove these fragments merely because they resemble a credential; they can help diagnose authentication failures.
This design does not cover arbitrary application logs, custom handlers, or third-party output.
Inspect the dump for intact credentials and redact any accidental exposure before attaching it to the appropriate ticket.
Do not dump credential files or add raw tokens to a command or reproduction. Preserve Trace IDs and useful request context.
