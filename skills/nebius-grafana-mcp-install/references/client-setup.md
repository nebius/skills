# Client setup and recovery

## Human-run setup

Run from this installed skill directory with an explicit client, human profile
and trusted HTTPS origin:

```bash
python3 scripts/setup.py --agent codex --user-profile <human-profile> --grafana-url https://<trusted-grafana-host> --check
python3 scripts/setup.py --agent codex --user-profile <human-profile> --grafana-url https://<trusted-grafana-host> --apply
```

Use `--agent claude` for Claude Code. `--check` reports local ownership, file
presence and bundle integrity. It does not read tokens, authenticate, launch
MCP or perform a health check. Raw configuration stays inside the helper.

The human executes `--apply` in a terminal. It inspects collisions, checks CLI
capabilities, stages a verified binary/runtime, binds the origin and human
identity, captures token output into a protected file, and registers one client.
Initial authentication may open the browser. Review the destination carefully:
explicitly supplying an origin trusts it to receive your Nebius IAM credential.

## Client differences

| Client | Configuration and registration | Startup |
|---|---|---|
| Codex | User config.toml, native MCP add/remove and internal JSON inspection; existing CODEX_HOME is honored within the user's home | startup_timeout_sec = 300 |
| Claude Code | Standard user ~/.claude.json; native --scope user registration and direct internal JSON inspection | Parent MCP_TIMEOUT=300000 |

For Claude, start a new parent process with:

```bash
MCP_TIMEOUT=300000 claude
```

No shell profile, hook or unrelated setting is edited. A running client does
not acquire a new launch environment automatically.

When Claude has no user configuration yet, its native add command also creates
Claude's initial machine/migration metadata. Existing unrelated configuration
must remain unchanged; native migration drift is reported as partial setup for
human inspection before rerunning the same command.

Official references: [Codex MCP](https://developers.openai.com/codex/mcp),
[Claude MCP](https://code.claude.com/docs/en/mcp), and
[Claude skill names](https://code.claude.com/docs/en/skills).

## Ownership and updates

The default server is `grafana-nebius`. If another installer owns it, select a
distinct `--mcp-server-name`. Existing donor entries and credentials are never
adopted, migrated or overwritten.

Repeated apply reuses matching state. `--apply --update` requests credential
renewal even for a recent cache and allows an explicitly owned update;
unexpected configuration drift is refused. An origin or human
identity change requires a distinct installation, not an update of its binding.

A prepared receipt records partial registration. Re-running apply finishes an
exact owned partial entry, including a Codex add interrupted before its timeout
was written. It does not restore an entire old configuration or discard another
writer's changes. Immutable old bundles remain available; no automatic cleanup
or rollback restores old credentials.

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

After setup, restart the selected client and verify initialize, list-tools and
a bounded datasource list on an authorized target. Local registration success
and offline fixtures do not establish live access or successful future renewal.
Authentication/entitlement failures never authorize creating keys, service
accounts, IAM grants or datasources.
