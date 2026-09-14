<!-- markdownlint-disable MD001 MD024 -->
<!-- maintain-project-specs:requirements:start schema=maintain-project-specs/requirements-v2 -->
# Project Requirements

<!-- REQUIREMENT: REQ-001 status=active priority=P0 type=feature -->
### REQ-001: Self-contained agent-run Grafana MCP installation

#### User Story

A Nebius user explicitly invokes one skill to install and verify Grafana MCP for Codex or Claude Code. The agent executes the bundled helper; the user supplies missing non-secret inputs, completes browser sign-in when needed, and reloads the client only when automatic activation is unavailable.

#### Acceptance Criteria

- AC-001: One skill contains agent-run setup, both user-scoped client adapters, installer-owned checksum-verified Grafana MCP 1.4.0 acquisition, a pinned discovery catalog, immutable runtime bundles and a supervised credential proxy. Python 3.11+, Bash, the native client and a configured Nebius CLI remain prerequisites.
- AC-002: Setup requires a selected client, human profile and trusted HTTPS origin. Omitted selectors may be resolved only from a unique validated installer-owned binding; otherwise request missing inputs. Check remains non-mutating and credential-free.
- AC-003: Explicit invocation authorizes only this skill's bundled installer and fixed renewal workflow under its documented skill-specific credential boundary. Direct agent token commands, credential-file inspection and permission bypass remain forbidden. This boundary grants no authority to other skills and does not override host or organization restrictions.
- AC-004: Credential values stay within local helper/runtime processes and protected storage. No credential values, raw subprocess output, authentication URLs or config dumps enter agent-visible results, progress, chat or generated documentation. This is a workflow-output guarantee, not OS-user isolation.
- AC-005: Only the credential proxy forwards the Nebius token to the bound origin, using TLS verification, redirect rejection, bounded reads and validated Prometheus query POSTs. Stock MCP receives an ephemeral loopback credential.
- AC-006: The advertised datasource health tool works through exact `GET /api/datasources/uid/<uid>/health` after UID verification; other methods, bodies, queries and neighboring routes are refused. Datasource health and plugin support do not determine installation success.
- AC-007: Setup uses native MCP registration and never directly rewrites client configuration or timeout settings. Local MCP initialization and discovery do not wait for network authentication or Grafana metadata. Detectable registration drift and foreign registrations are refused; native-client writes retain their own concurrency semantics.
- AC-008: Setup verifies registration plus a bounded MCP initialize, tool list and datasource list using a helper-owned subprocess. Agent-visible status distinguishes local installation, runtime readiness and current-client activation. Reload is requested only when required; never terminate the host to activate tools.
- AC-009: Human identity, origin and token generations remain pinned. Browser authentication is bounded and resumes setup automatically. Repeats and partial recovery affect exactly owned state; renewal scheduling, original observation timestamps and reconnect-required rotation remain intact. Cached credentials must be at most one hour old when loaded. Watchdog attachment validates the already-frozen generation against its original eleven-hour operational cap without reapplying the one-hour admission limit.
- AC-010: Keep all implementation, setup instructions, credential-boundary documentation, tests and evals inside this skill folder. Outside it, change only this skill's README table row and one concise CHANGELOG entry. The shared preamble, other skills, SECURITY.md, CONTRIBUTING.md, CI, root evals and plugin manifests must match the PR base. Preserve donor source, installed skills and actual client/auth state. Keep this skill's generated preamble identical to the unchanged shared source; skill-specific instructions belong outside that generated block.
- AC-012: The runtime serves only verified pinned discovery metadata while preparing credentials asynchronously, with a 240-second preparation bound. Pending operations return a sanitized retryable error and send no Grafana requests. The live backend must match the catalog before operations are forwarded.
- AC-013: The binary always resides in the installer-owned version directory. Missing owned executable files are recoverable through normal setup; changed bytes, unsafe paths and malformed provenance fail closed. No Homebrew adoption or legacy installation support is included.
- AC-011: Refresh writers preserve validated PID/process-start identity without PID temporary files. Concurrent reuse requires a complete matching fresh token generation. Existing lock residue is not automatically deleted.

#### Negative Criteria

- NC-001: No real credentials, private origins, customer data or resource identifiers enter source, fixtures, documentation or reports.
- NC-002: No IAM creation, static keys, service-account substitution, impersonation, arbitrary forwarding, automatic identity/origin change, unbounded streams or native permission bypass.
- NC-003: Do not claim OS isolation, authoritative token expiry, uninterrupted operation beyond twelve hours, automatic same-chat activation, or live installation from offline evidence.

#### Validation Method

Repository structural checks, scoped lint/syntax, isolated tests, independent risk review and final alignment. Keep source, native client registration and live evidence separate.

#### Test Method

Synthetic credentials and isolated homes exercise browser-required/signed-in setup, output privacy, owned discovery/update/recovery, default-timeout startup, pending authentication, binary recovery, health routing, MCP readiness, cancellation and existing lifecycle guarantees.

#### Evaluation Method

Skill-local explicit invocation, missing inputs, browser handoff, native activation, collisions, rotation and privacy scenarios. Agent runs the helper; the user never copies an installer command. CI integration is excluded.

<!-- /REQUIREMENT: REQ-001 -->
<!-- maintain-project-specs:requirements:end -->
<!-- markdownlint-enable MD001 MD024 -->
