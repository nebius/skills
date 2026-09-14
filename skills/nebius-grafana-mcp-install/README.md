# Nebius Grafana MCP Install

A self-contained, agent-run installer for local Codex and Claude Code,
adapted from the Apache-2.0
[donor skill](https://github.com/nebius/nebius-ps-services/tree/a1d6ef7a0192072cf541891c78d3460a1b86a5e7/skills/install-grafana-mcp-for-nebius).

The runtime connects the agent's official Grafana MCP to an existing trusted
Grafana through a bundled credential proxy. The proxy holds the Nebius token,
verifies TLS, refuses redirects and permits only bounded read requests.
A successful token rotation requires a new MCP connection.

Explicit skill invocation authorizes bundled setup and its fixed supervised
renewal under the repository's narrow credential-handling exception. Credentials
stay in helper/runtime processes and protected private state; sanitized results
keep the token out of agent context in the supported workflow. Same-user OS
access remains possible. See [runtime security](references/runtime-security.md).

## Install the skill, then configure MCP

Use the repository's marketplace instructions for the complete `nebius-cloud`
plugin. For an individual skill, select `nebius-grafana-mcp-install` using the
repository's documented Agent Skills installer. Copying this entire folder
also provides all resources; no donor checkout or companion skill is needed.

Skill installation does not run MCP setup. Explicitly invoke
`$nebius-grafana-mcp-install` in Codex. Claude Code uses
`/nebius-grafana-mcp-install` for a standalone skill or
`/nebius-cloud:nebius-grafana-mcp-install` in the plugin.

The agent checks prerequisites, asks once for missing non-secret inputs, and
runs setup automatically. Later invocations reuse a unique validated owned
binding. You may need to complete browser sign-in or reload the client when it
cannot activate a new MCP registration in the current session. No manual setup
command or token copying is needed.

Supply a human Nebius profile and an existing trusted HTTPS Grafana origin when
asked. That Grafana must accept your Nebius IAM credential.
The installer does not deploy Grafana or configure its data sources.
A public observability datasource read endpoint is not a Grafana API endpoint.
Custom `--mcp-server-name` values start with a letter or digit and contain
1-64 letters, digits, underscores or hyphens. Invalid names are refused before
setup commands or local state changes.

## Requirements and behavior

- Local macOS/Linux on ARM64 or x86-64, Bash and Python 3.11+.
- Nebius CLI >=0.12.247 with a human profile and bounded authentication flags.
  Setup verifies capabilities; it does not upgrade the CLI or create IAM objects.
- Codex CLI or Claude Code's standard user configuration. Custom Claude config
  directories are refused; existing Codex home settings are honored inside the
  user's home.
- Official Grafana MCP 1.4.0, reused only with verified Homebrew provenance or
  installed from the locked official archive. No global package upgrades.
- A human-supplied HTTPS Grafana origin, bound privately to the installation and reused on later invocations.
  Origin and identity changes require a distinct installation name.

The proxy is an ephemeral loopback listener owned by the MCP connection. It has
no system service, public listener or persistent local access credential.
Read-only categories and explicit `--disable-proxied` prevent automatic remote
MCP discovery probes. Tempo queries use the bounded GET API paths.

See [client setup](references/client-setup.md),
[authentication lifecycle](references/auth-lifecycle.md), and
[runtime security](references/runtime-security.md) for paths, recovery and limits.
Ordinary queries are a separate task after setup succeeds.

Renewal avoids PID temporary files and rejects incomplete concurrent token
generations. Background failures retain bounded retries. When updating a pre-fix
runtime, stop writers sharing its state and follow the authentication recovery
instructions for any existing lock residue; it is not automatically deleted.

Setup configures Codex's per-server 300-second startup timeout and Claude's user
`env.MCP_TIMEOUT` to at least 300000 milliseconds, preserving a larger valid
value and unrelated settings. It verifies initialization, tool discovery and one
bounded datasource list in a private subprocess. Registration, this runtime
check and current-chat tool availability are reported separately. Datasource
health results, including unsupported plugin checks, do not determine whether
installation succeeded.

## Validation

From the repository root:

```bash
python3 -B -m unittest discover -s skills/nebius-grafana-mcp-install/tests
bash -n skills/nebius-grafana-mcp-install/scripts/ensure-local-config.sh
bash -n skills/nebius-grafana-mcp-install/scripts/run-nebius-grafana-mcp.sh
shellcheck skills/nebius-grafana-mcp-install/scripts/*.sh
python3 scripts/sync-shared.py --check
python3 scripts/check-frontmatter.py
bash scripts/validate.sh
```

Tests use synthetic credentials, isolated homes, fake CLI/client executables
and local HTTP fixtures. Skill-local `evals/` records behavioral and trigger
expectations; root CI does not execute these local evaluation files.

The scoped requirements/design pair is under `docs/`. See
[validation evidence](references/validation.md) for observed checks and unverified
surfaces. Attribution and adaptation boundaries are in [NOTICE](NOTICE).
