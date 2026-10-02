# Nebius Grafana MCP Install

A self-contained, agent-run installer for local Codex and Claude Code,
adapted from the Apache-2.0
[donor skill](https://github.com/nebius/nebius-ps-services/tree/a1d6ef7a0192072cf541891c78d3460a1b86a5e7/skills/install-grafana-mcp-for-nebius).

The runtime connects the agent's official Grafana MCP to an existing trusted
Grafana through a bundled credential proxy. The proxy holds the Nebius token,
verifies TLS, refuses redirects and permits only bounded read requests.
A successful token rotation requires a new MCP connection.

Explicit skill invocation authorizes bundled setup and its fixed supervised
renewal under this skill's documented credential boundary. Credentials
stay in helper/runtime processes and protected private state; sanitized results
keep the token out of agent context in the supported workflow. Same-user OS
access remains possible. See [runtime security](references/runtime-security.md).

This skill includes Python/Bash helpers and a Grafana MCP runtime. Its private
credential workflow differs from the catalog's generic CLI-only and human-run
credential defaults; the scope is defined in [Invocation Policy](SKILL.md#invocation-policy).
Host, workspace and organization restrictions still apply.

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
- Official Grafana MCP 1.4.0, installed from the checksum-pinned official archive
  into an owned version directory. Existing validated bytes are reused offline;
  a missing executable is repaired by invoking the skill again.
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

The runtime answers initialization and tool/resource discovery locally,
without waiting for authentication or Grafana metadata. Calls made during
preparation return a fixed retryable error; no operation is queued or forwarded.
The real authenticated backend must match the pinned catalog before it accepts
operations. Preparation is bounded to 240 seconds and never opens a browser.

Client descriptions reflect this runtime's restrictions. The original pinned
catalog remains unchanged for exact backend verification; a separate in-memory
copy corrects initialization instructions and tool descriptions. Tool names,
argument structure, resources and request routing stay unchanged. The API tool
permits only allowlisted GET routes, such as `/api/datasources`, rather than
arbitrary Grafana APIs. Leave custom headers unset. Loki queries support Loki
only, with a default of 10 and maximum of 20 log entries. Prometheus tools require
verified Prometheus HTTP routes; Cloud Monitoring and the dedicated
VictoriaMetrics plugin query route are unsupported. VictoriaMetrics behind a
Prometheus-compatible datasource can still work.

The one-hour freshness limit applies when loading a credential. Crossing that
boundary after loading does not end the connection; its watchdog retains the
eleven-hour operational cap measured from the token's original observation.
This cap does not establish the token's actual expiry.

Setup uses native client registration and does not rewrite client timeout
settings. Native commands retain their own concurrency behavior; detected
registration drift is reported. Setup verifies one bounded datasource list in
a private subprocess, retrying only the explicit preparation response within
its 300-second budget. Registration, runtime readiness and current-chat tool
availability are reported separately. Datasource health, including unsupported
plugin checks, does not determine installation success.

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
