<!-- markdownlint-disable MD001 MD024 -->
<!-- maintain-project-specs:requirements:start schema=maintain-project-specs/requirements-v2 -->
# Project Requirements

<!-- REQUIREMENT: REQ-001 status=active priority=P0 type=feature -->
### REQ-001: Self-contained agent-run Grafana MCP installation

#### User Story

A Nebius user explicitly invokes one skill to install and verify Grafana MCP for Codex or Claude Code. The agent executes the bundled helper; the user supplies missing non-secret inputs, completes browser sign-in when needed, and reloads the client only when automatic activation is unavailable.

#### Acceptance Criteria

- AC-001: One skill contains agent-run setup, both user-scoped client adapters, checksum-verified Grafana MCP 1.4.0 acquisition, immutable runtime bundles and a supervised credential proxy. Python 3.11+, Bash, the native client and a configured Nebius CLI remain prerequisites.
- AC-002: Setup requires a selected client, human profile and trusted HTTPS origin. Omitted selectors may be resolved only from a unique validated installer-owned binding; otherwise request missing inputs. Check remains non-mutating and credential-free.
- AC-003: Explicit invocation authorizes the bundled installer and its fixed renewal workflow under a narrowly scoped canonical repository policy exception. Direct agent token commands, credential-file inspection and permission bypass remain forbidden.
- AC-004: Credential values stay within local helper/runtime processes and protected storage. No credential values, raw subprocess output, authentication URLs or config dumps enter agent-visible results, progress, chat or generated documentation. This is a workflow-output guarantee, not OS-user isolation.
- AC-005: Only the credential proxy forwards the Nebius token to the bound origin, using TLS verification, redirect rejection, bounded reads and validated Prometheus query POSTs. Stock MCP receives an ephemeral loopback credential.
- AC-006: The advertised datasource health tool works through exact `GET /api/datasources/uid/<uid>/health` after UID verification; other methods, bodies, queries and neighboring routes are refused. Datasource health and plugin support do not determine installation success.
- AC-007: Setup automatically configures Codex startup timeout and Claude user-settings MCP_TIMEOUT, preserves a larger existing Claude timeout and unrelated configuration, and refuses concurrent drift or foreign registrations.
- AC-008: Setup verifies registration plus a bounded MCP initialize, tool list and datasource list using a helper-owned subprocess. Agent-visible status distinguishes local installation, runtime readiness and current-client activation. Reload is requested only when required; never terminate the host to activate tools.
- AC-009: Human identity, origin and token generations remain pinned. Browser authentication is bounded and resumes setup automatically. Repeats and partial recovery affect exactly owned state; renewal scheduling, original observation timestamps and reconnect-required rotation remain intact.
- AC-010: Development may change this skill, root README/changelog, SECURITY.md, CONTRIBUTING.md and the shared preamble with generated copies. CI, root evals, plugin manifests, donor source, installed skills and actual client/auth state remain unchanged. Skill-local tests and evals remain outside CI by explicit scope choice.
- AC-011: Refresh writers preserve validated PID/process-start identity without PID temporary files. Concurrent reuse requires a complete matching fresh token generation. Existing lock residue is not automatically deleted.

#### Negative Criteria

- NC-001: No real credentials, private origins, customer data or resource identifiers enter source, fixtures, documentation or reports.
- NC-002: No IAM creation, static keys, service-account substitution, impersonation, arbitrary forwarding, automatic identity/origin change, unbounded streams or native permission bypass.
- NC-003: Do not claim OS isolation, authoritative token expiry, uninterrupted operation beyond twelve hours, automatic same-chat activation, or live installation from offline evidence.

#### Validation Method

Repository structural checks, scoped lint/syntax, isolated tests, independent risk review and final alignment. Keep source, native client registration and live evidence separate.

#### Test Method

Synthetic credentials and isolated homes exercise browser-required/signed-in setup, output privacy, owned discovery/update/recovery, host timeouts, health routing, MCP readiness, cancellation and existing lifecycle guarantees.

#### Evaluation Method

Skill-local explicit invocation, missing inputs, browser handoff, native activation, collisions, rotation and privacy scenarios. Agent runs the helper; the user never copies an installer command. CI integration is excluded.

<!-- /REQUIREMENT: REQ-001 -->
<!-- maintain-project-specs:requirements:end -->
<!-- markdownlint-enable MD001 MD024 -->
