<!-- markdownlint-disable MD001 MD024 -->
<!-- maintain-project-specs:design:start schema=maintain-project-specs/design-v2 -->
# Project Design

<!-- FEATURE: FEAT-001 reqs=REQ-001 status=ready delivery=verified priority=P0 version=10 -->
### FEAT-001: Shared setup and supervised credential proxy

#### Requirements Covered

- REQ-001: Self-contained human-operated Grafana MCP installation.

#### Context Evidence

Accepted design retains the official Grafana MCP and existing hosted Grafana. Direct API and separately launched installed-MCP datasource reads succeeded using an existing protected token; those probes do not prove this new implementation. Upstream v1.4.0 reapplies authorization through its HTTP transport and supports no outbound redirect restriction. Proxied discovery requires explicit disablement because startup may issue MCP availability DELETE probes.

#### Design Details

Human setup takes --agent codex|claude, --user-profile and --grafana-url, with --check as the local-only default, --apply for installation, optional --mcp-server-name and explicit --update for credential renewal and an exactly owned update. Use Python 3.11+ standard library and the existing Bash supervisor. Bind a canonical HTTPS origin, human identity and client/server/profile state in private files. Code is content-addressed and release artifacts remain checksum-verified for macOS/Linux ARM64/x86-64. Changing a bound origin or identity is refused. Server names use 1-64 letters, digits, underscores or hyphens and start with a letter or digit; setup rejects names outside the existing runtime contract before preflight or authentication.

The supervisor launches a loopback HTTP proxy and stock MCP in one owned runtime. A random ephemeral local credential authenticates MCP requests; only the proxy holds the frozen Nebius token generation. The proxy uses verified TLS, no ambient proxies or redirects, fixed origin-relative read paths, bounded finite bodies and requests, and only validated Prometheus query/query_range/labels POST routes. Datasource UIDs must come from authenticated discovery; a constant bounded query establishes Prometheus route compatibility without relying on plugin names. Other mutations, streaming, redirects and arbitrary plugin paths are refused. A complete-frame stdio guard withholds malformed, oversized or credential-reflecting output; subprocess diagnostics never pass through.

Fixed MCP options are --transport stdio --disable-write --disable-proxied --enabled-tools search,datasource,dashboard,prometheus,loki,api --max-loki-log-limit 20. Tempo uses fixed GET query/tag/trace routes. Each connection freezes one token generation. Reuse tokens observed within one hour, schedule renewal at ten hours, stop by eleven hours using wall and monotonic bounds, and retain the original observation time for repeated bytes. These are operational caps, not authoritative issuance/expiry. Renewal is noninteractive and bounded; successful rotation exits 75 and the next connection loads the new generation. Failed renewal stops safely with human authentication guidance.

Keep both native client adapters, exact ownership recovery and unrelated configuration preservation. A first Claude registration may create native initialization metadata only when no configuration existed; existing unrelated values remain protected. Codex startup timeout remains 300 seconds. Claude parent MCP_TIMEOUT remains 300000. Public examples contain only placeholders. Remove the source approval gate and replace maintainer prerequisites with operational documentation that explicitly identifies the unchanged credential-policy, runtime dependency and root-eval-placement discrepancies.

Targeted CR003/CR004 repair: capture the writer PID with an explicit exec of Python os.getppid in command substitution before acquiring the directory lock, validate its process-start identity, and keep writer variables separate from inspected lock-owner variables. Remove owner-pid.tmp creation and deletion; retain the existing owner metadata format and exact cleanup checks. Existing residue requires human-confirmed quiescence and exact cleanup, with no automatic migration. Require token_file_is_fresh before concurrent reuse succeeds. Incomplete metadata causes owned lock cleanup, a sanitized error and return 1, allowing background retries while foreground setup fails. Do not synthesize metadata or alter token ages.

The selected scope retains directory locking. Replacing it with kernel locking and proving age-based recovery safe against a paused initializer are explicitly separate work. CLI, client adapters, token metadata schema, deadlines, credential policy and installation methods remain fixed.

#### Selected Option

A self-contained human-operated installer with a bundled credential proxy, deterministic supervised renewal and restart-based stdio. The host agent explains setup and performs credential-free inspection; it does not execute the credential-issuing setup workflow.

#### Alternatives Considered

Direct MCP authentication cannot enforce exact-origin credential forwarding. A new Grafana deployment or direct observability server is unnecessary for the selected hosted-Grafana topology. A permanent maintainer approval switch prevents useful operator software and does not resolve repository policy.

#### Implementation Boundaries

Only this skill tree, one root README row and the root changelog entry for this skill. Preserve root policy, plugin manifests, root evals, CI, donor source and current installed client/auth state. No claim that skill-local prose overrides SECURITY.md.

#### Test-First Success Criteria

- TDD-001: Missing/malformed origin or changed binding fails before authentication or file mutation; check/help remain credential-free.
- TDD-002: Synthetic proxy fixtures prove local authentication, exact-origin forwarding, no redirect leakage, read-route enforcement, custom datasource handling and private output.
- TDD-003: Both adapters, immutable packaging, partial recovery, repeated bytes, frozen connection deadlines, rotation, cancellation and worker supervision retain their guarantees.

#### Validation Plan

Run focused unit/HTTP/stdio fixtures, Python/Bash/Markdown checks, full repository validation, risk review and alignment. Preserve separate evidence for source, temporary native-client registrations and live compatibility.

#### Test Plan

Use isolated homes and synthetic credentials. Test actual HTTP requests and MCP framing, redirects toward a second fixture server, oversized/malformed/secret-reflecting output, UID validation, method restrictions, concurrent refresh and process cleanup. Existing live credentials may be used only for the separately authorized bounded read-only proxy acceptance check; do not mint or modify credentials for development.

#### Evaluation Plan

Update local scenarios for human-run setup and private token handling. Keep six trigger examples and at least three behavioral scenarios; root CI does not execute these skill-local evaluations. Fresh agent triggering and comparative model quality require separate evaluation.

#### Rollout And Rollback

Human-run setup materializes immutable bundles and creates exact owned user-scoped MCP entries. Re-run check to inspect; update only with explicit --apply --update. Existing foreign registrations and changed bindings are refused. Operator utility is functional without a maintainer switch, while repository policy discrepancies remain explicitly documented.

#### Done Definition

Scoped implementation and passing focused verification with documentation aligned. Distinguish remaining live/runtime evidence gaps and policy discrepancies from code completion.

#### Implementation Evidence

Implemented self-contained setup, origin binding, immutable runtime inventory, credential proxy, full-frame bridge, fixed MCP flags, observation metadata and process-group supervision. Removed the permanent policy gate and replaced maintainer prerequisites with operational/policy documentation. Scope is this skill tree, one root README row and the root changelog entry for this skill; donor source and installed client/auth state were preserved.

#### Verification Evidence

Publication validation passed all 70 offline tests on macOS in 105.631 seconds, including the two security-hardening tests for early invalid-name refusal and both-client valid-name preservation. The root changelog records the new skill and its explicit runtime/policy deviations. Repository validation and scoped lint/syntax checks passed; no live authentication or existing client configuration was changed.

68 offline tests passed on macOS in 106.353 seconds. CR001/CR002 GNU stat and source-update inspection fixes retain their earlier focused coverage. Targeted CR003/CR004 repairs now pass seven additional tests: foreground/background PID-capture crashes leave no blocking artifact and a subsequent renewal succeeds; both writer identities match live owning shells; incomplete concurrent publication fails foreground refresh without changing that generation and permits background retry to publish a complete generation and exit 75; pre-fix PID residue remains for human recovery. The four defect-specific controls failed for the original reasons before repair and passed afterward. Writer inspection uses a bounded synthetic mint barrier, avoiding timing or CLI-help-count assumptions.

The implementation captures validated writer identity before acquiring the directory lock, removes PID-temp creation/deletion, and requires token_file_is_fresh before concurrent reuse success. Invalid metadata returns 1 after owned lock cleanup, preserving background retry control flow without rewriting the incomplete pair. Scoped lint, syntax, wiring, changed-scope alignment and follow-up code/security review passed. The generic structure validator retains its documented root-relative shared-marker false positive; repository preamble/frontmatter checks pass. Current Codex/Claude installations, credentials and donor files were preserved.

CR003/CR004 are verified within the explicitly selected targeted scope. Existing PID residue requires human recovery after quiescence; no automated migration was added. Directory-lock replacement and proving age-based incomplete-lock recovery safe against a paused initializer remain separate work. GNU stat coverage on macOS does not prove full Linux execution.

Earlier implementation evidence includes native Codex/Claude registration, repeat apply and local inspection in isolated temporary homes, and a locked official MCP1.4.0 initialize/tools-list/datasource read through the new proxy using an existing protected credential without issuance or configuration changes. That evidence was not rerun for the current repairs. Prior repository validation passed; the generic skill validator has one documented root-relative shared-marker false positive. Live renewal, fresh skill triggering, Linux execution and comparative model quality were not run. The preceding alignment repaired malformed Prometheus probe handling and runtime help. See references/validation.md for evidence boundaries. DNS establishment is subject to OS resolver/socket behavior; total establishment duration is not strictly bounded. Same-user access and unchanged repository-policy discrepancies remain explicit.

<!-- /FEATURE: FEAT-001 -->
<!-- maintain-project-specs:design:end -->
<!-- markdownlint-enable MD001 MD024 -->
