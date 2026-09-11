<!-- markdownlint-disable MD001 MD024 -->
<!-- maintain-project-specs:requirements:start schema=maintain-project-specs/requirements-v2 -->
# Project Requirements

<!-- REQUIREMENT: REQ-001 status=satisfied priority=P0 type=feature -->
### REQ-001: Self-contained human-operated Grafana MCP installation

#### User Story

A Nebius user installs the official Grafana MCP for Codex or Claude Code against an explicitly trusted hosted Grafana, keeping bearer credentials outside agent-visible output and using best-effort renewal for long-running use.

#### Acceptance Criteria

- AC-001: One skill contains human-run setup, both user-scoped client adapters, verified Grafana MCP 1.4.0 acquisition, immutable runtime bundles and a supervised local credential proxy.
- AC-002: Setup requires an explicit client, human profile and HTTPS Grafana origin. Check is credential-free and non-mutating; no permanent approval gate or credential-command agent pre-approval is provided.
- AC-003: Only the proxy receives the Nebius token. It authenticates local access, binds outbound credentials to one origin, refuses redirects, verifies TLS and permits only bounded read routes and validated Prometheus query POSTs.
- AC-004: MCP uses fixed read-only categories and explicit --disable-proxied. Tempo uses finite GET routes. Credential-bearing or malformed MCP output is withheld.
- AC-005: Human identity, private state and token generations remain pinned. Observation timestamps are not represented as issuance or expiry; identical bytes retain the earlier timestamp. Rotation requires reconnection and has no uninterrupted-service guarantee.
- AC-006: Existing donor and unrelated client registrations are preserved; updates and interrupted recovery affect exactly owned state only.
- AC-007: Development changes only this skill tree, one root README row and the root changelog entry for this skill. Tests, evaluations and references are self-contained; no donor source, installed skill or current client/auth configuration changes.

- AC-008: Refresh writers capture their own PID and process-start identity before lock acquisition without creating a PID temporary file. Existing pre-fix residue is not automatically deleted.
- AC-009: Concurrent refresh reuse succeeds only for a complete, matching, fresh token generation. Incomplete publication returns a normal failure so background renewal retains bounded retries; foreground setup fails with human guidance.

#### Negative Criteria

- NC-001: No real credentials, private origins, customer data or resource identifiers enter source, fixtures, documentation or agent output.
- NC-002: No IAM creation, static keys, service-account substitution, impersonation, arbitrary proxy forwarding, automatic origin change or unbounded stream.
- NC-003: Do not claim OS isolation, authoritative token expiry, uninterrupted access beyond twelve hours, full repository-policy compliance, or live client installation based on offline evidence.

#### Validation Method

Repository validation, focused Python/Bash checks, isolated fixtures, read-only risk review and changed-surface alignment.

#### Test Method

Synthetic CLI/client/MCP executables and local HTTP fixtures cover both clients, lifecycle, origin and route enforcement, output privacy, cancellation, packaging and failure recovery.

#### Evaluation Method

Skill-local setup, human handoff, collision, rotation, unsafe origin and standalone-install scenarios. Separate authorized live proxy/MCP readiness from offline renewal tests and native-client installation.

<!-- /REQUIREMENT: REQ-001 -->
<!-- maintain-project-specs:requirements:end -->
<!-- markdownlint-enable MD001 MD024 -->
