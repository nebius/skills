# Client setup and recovery

## Agent-run setup

Explicitly invoke the skill for installation. The agent runs the bundled helper
through `bash scripts/ensure-local-config.sh` from its installed skill directory,
first with `--check`, then with `--apply`. This entry point checks Python before
loading the installer.
For a first installation, supply non-secret selectors when asked:

```text
python3 scripts/setup.py --agent codex --user-profile NAME --grafana-url HTTPS_ORIGIN --apply
```

Use `--agent claude` for Claude Code. Later invocations can omit profile, origin
and server name when exactly one validated owned binding matches. Discovery
reads only owned receipts, origin/identity bindings, runtime provenance and
client registration; it does not inspect credentials or ambient CLI profiles.
Multiple matches require selection; foreign, malformed, symlinked or drifted
state is refused. Prepared registration can be resumed. A missing ready entry
or changed client config root needs explicit selectors for repair.

`--check` reports local ownership, registration, file presence and bundle integrity.
It never authenticates, reads tokens, starts MCP or performs a network check.
Its JSON includes `update_required`; the agent uses `--apply --update` for owned
repair/update when indicated, or when explicitly asked to renew authentication.
Missing non-secret fields are reported with exit 2 for one bundled question.

Apply checks CLI capabilities, installs the verified runtime, validates the
pinned human identity, handles credentials internally, registers one client and
verifies MCP. The helper may open browser sign-in; the user completes that step.
No token or login URL is copied into chat. The supplied HTTPS origin must be an
existing Grafana trusted to receive this human profile's Nebius IAM credential.
Existing Python, Bash, Nebius CLI and client prerequisites are checked, not
installed. Missing prerequisites and native permission blocks are reported.

## Client differences

| Client | Configuration and registration | Startup |
|---|---|---|
| Codex | User config.toml, native MCP add/remove and internal JSON inspection; existing CODEX_HOME is honored within the user's home | Existing client timeout remains unchanged |
| Claude Code | Standard user ~/.claude.json; native --scope user registration and direct internal JSON inspection | Existing client timeout remains unchanged |

The installer never directly rewrites client configuration or timeout settings.
It does not open or modify Claude's settings.json. Native MCP add/remove owns
registration writes. Before/after checks detect observable registration drift;
they cannot guarantee atomic preservation against every concurrent external
writer. A detected conflict leaves owned state for inspection and a later retry.
No shell profile, permission rule, hook or managed setting is changed.

Local initialization, ping and pinned tool/resource discovery are independent of
authentication and Grafana requests. This removes the need to increase startup
timeouts. A managed host restriction or a client configured with an unusually
short timeout can still require attention; initialization alone is not proof of
authenticated readiness or current-session activation.

When Claude has no user configuration yet, its native add command also creates
Claude's initial machine/migration metadata. Existing unrelated configuration
must remain unchanged; native migration drift is reported as partial setup for
human inspection before rerunning the same command.

Official references: [Codex MCP](https://developers.openai.com/codex/mcp),
[Claude MCP](https://code.claude.com/docs/en/mcp), and
[Claude settings environment](https://code.claude.com/docs/en/env-vars#in-settings-files).

## Ownership and updates

The default server is `grafana-nebius`. If another installer owns it, select a
distinct `--mcp-server-name`. Existing donor entries and credentials are never
adopted, migrated or overwritten.

Repeated apply reuses matching state. `--apply --update` requests credential
renewal even for a recent cache and allows an explicitly owned update;
unexpected configuration drift is refused. An origin or human
identity change requires a distinct installation, not an update of its binding.

A prepared receipt records partial registration. Re-running apply finishes an
exact owned native registration interrupted before final receipt publication. It does not restore an entire old configuration or discard another
writer's changes. Immutable old bundles remain available; no automatic cleanup
or rollback restores old credentials.

The executable always resides in the installer-owned version directory and is
verified against its receipt before reuse. A missing owned executable remains
discoverable: local check returns `update_required: true`, and normal skill
invocation reacquires the same checksum-pinned release. A changed executable,
unsafe path, malformed receipt or provenance mismatch fails closed. There is
no Homebrew adoption or legacy installation path. Interrupted receipt
publication recovers only an exact verified artifact, never arbitrary bytes.

## Locations and removal

- Runtime: `~/.local/share/nebius-grafana-mcp/runtime/<digest>/`.
- Binary/provenance: `~/.local/share/nebius-grafana-mcp/bin/1.4.0/`.
- State: `~/.config/nebius-grafana-mcp/<agent>/<server>/<profile>/`.

State contains the origin, identity, token, observation metadata and ownership
receipt. Directories/files use modes 0700/0600. Per-connection generation and
restart files are removed on shutdown. The loopback credential is never saved.
Codex and Claude share immutable code but have independent state. Installed
entries do not point into a checkout or plugin cache.

For removal, close the affected client sessions and have the human remove the
exact named registration with its native client command. Deleting private state
and unused bundles is a separate explicit human action. Preserve bundles still
used by another installation.

## Readiness

Apply launches the exact owned wrapper in an isolated helper subprocess with a
300-second overall verification budget. It performs MCP initialize, initialized
notification, paginated tool discovery and one `list_datasources` call with
`limit: 1`. During preparation it retries only the exact fixed retryable
response, without resetting the overall deadline. Protocol responses and all raw stderr remain internal; only fixed
progress and result fields reach the agent. Empty datasource lists pass. The
helper stops and reaps its test connection after success, failure or cancellation.

Successful apply returns registration `ready`, runtime `ready`, activation
`not checked`. Results also identify the validated server name for host activation.
Exit 4 means registration is retained but runtime verification
failed; the agent reports that distinction and the sanitized recovery message.
The skill separately checks current-chat tool availability, using supported
reconnect/reload controls if available. Otherwise the user reloads the client.
Do not terminate the active host or claim same-chat activation from the helper's
independent connection. Live datasource health is a separate query; unhealthy
or unsupported plugins do not make installation fail. Authentication failures
never authorize creating keys, service accounts, IAM grants or datasources.
