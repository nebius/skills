# Runtime security and contribution boundaries

## What the human authorizes

Explicit installation invocation authorizes the agent to run bundled setup, which installs one local MCP registration and trusts the explicit
HTTPS Grafana origin to receive the selected human profile's Nebius IAM token.
The operator must establish this audience before setup. No endpoint is embedded
or declared universally available to Nebius customers.

Origin validation accepts a named HTTPS origin with an optional port and trailing
slash. It rejects credentials, paths, query strings, fragments, ambiguous names
and IP literals. The private origin binding is immutable for that installation.
A changed environment value does not change the credential destination.

## Proxy and output protection

The supervised proxy binds only 127.0.0.1 on a random port and requires a fresh
local access credential. Stock MCP receives this credential in its process
environment; the real Nebius token and its file path are omitted. The local
credential lasts only for that process and is not stored in client configuration.

The proxy verifies upstream TLS, ignores ambient proxies, replaces authentication
headers and follows no redirects. Upstream Location, cookies and raw error bodies
are not forwarded. It accepts finite JSON reads only, with 256 KiB request,
8 MiB response, four concurrent connections and 30-second local connection and
connected-upstream read deadlines. DNS/TCP/TLS establishment uses the operating
system resolver and socket timeouts; its total duration is not strictly bounded.
Stalled establishment can occupy the four slots until it finishes or the owned
runtime stops. Reconnecting starts a new proxy; the connection lifecycle cap
still applies.

Approved paths cover Grafana frontend/datasource/search/dashboard reads and fixed
Prometheus, Loki and Tempo query/metadata routes. UIDs are validated against the
bound Grafana. A bounded constant query establishes custom Prometheus route
compatibility; a plugin's name alone is insufficient. POST is limited to the
Prometheus query, query_range and labels routes with bounded form bodies.
The exact GET `/api/datasources/uid/<uid>/health` route is also supported after
UID verification, without a body or query string. The plugin owns its health
status; unsupported handlers retain their HTTP failure status with sanitized
bodies. Setup never uses bulk datasource health as an installation gate.
Other POSTs, PUT/PATCH/DELETE, streaming, MCP discovery, upgrades, arbitrary plugin
paths, encoded separators and path traversal are refused. Generic Loki query
reads also enforce the 20-result limit.

MCP runs with fixed read categories, --disable-write and --disable-proxied.
The latter is explicit because upstream discovery can send MCP availability
DELETE probes independently of the selected categories. Tempo uses fixed GET
search/tag/trace paths instead of proxied tool discovery.

Upstream JSON and complete MCP frames are checked for the active Nebius/local
credential, including decoded JSON strings. Malformed, oversized or reflecting
output is withheld. Raw MCP stderr, HTTP logs, exceptions and CLI diagnostics do
not reach the agent. No system service or public network listener is installed.
These controls cover credentials handled by this runtime; they do not identify
all unrelated secrets that may already exist in queried telemetry.

The same OS user can inspect process environments or private files. This design
protects supported workflow output and credential routing, not against a hostile
agent with unrestricted access to the user's operating-system account.

## Repository policy and agent output

The shared preamble and SECURITY.md define a narrow exception for this bundled
installer and its fixed supervised renewal. The agent can invoke setup after an
explicit installation/update request, but cannot run credential commands
directly, read private token files, reproduce the credential workflow or bypass
native permissions. Protected persistence is limited to this runtime's state.
No broad Python, Bash or credential prefix is added to allowed-tools.

Setup captures all CLI and readiness output internally. Progress and final JSON
contain fixed stages, statuses, the validated server name and sanitized
remediation messages. The Nebius token is never placed in agent-visible tool
results, prompts, chat, logs or documentation by the supported workflow. This is a scoped privacy property,
not an unconditional safety guarantee or an OS isolation boundary.

The runtime requires Python/Bash and stock Grafana MCP. Root documentation
states these extra prerequisites. Skill-local tests and behavior definitions
remain outside root CI by scope decision. Source tests, isolated native-client
checks, live Grafana access and current-chat activation are separate evidence.

## Sources

- [Grafana MCP transport](https://github.com/grafana/mcp-grafana/blob/v1.4.0/mcpgrafana.go)
- [Grafana MCP API client](https://github.com/grafana/mcp-grafana/blob/v1.4.0/tools/api.go)
- [Proxied discovery](https://github.com/grafana/mcp-grafana/blob/v1.4.0/proxied_tools.go)
- [Prometheus backend](https://github.com/grafana/mcp-grafana/blob/v1.4.0/tools/prom_backend.go)
- [Datasource health API](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/data_source/#check-data-source-health)
