<!-- markdownlint-disable MD001 MD024 -->
<!-- maintain-project-specs:design:start schema=maintain-project-specs/design-v2 -->
# Project Design

<!-- FEATURE: FEAT-001 reqs=REQ-001 status=ready delivery=verified priority=P0 version=14 -->
### FEAT-001: Agent-run setup and supervised credential proxy

#### Requirements Covered

- REQ-001: Self-contained agent-run Grafana MCP installation.

#### Context Evidence

The installer supports agent-run setup and exact datasource health reads. Its helper-owned authentication and private credential storage differ from the catalog's generic human-run credential rules. Document that bounded workflow only in this skill; restore shared policy and other skills to the PR base. Browser sign-in and client reload remain user steps only when necessary.

#### Design Details

Keep Python 3.11+ standard library, Bash supervision, pinned MCP 1.4.0, stdio and native Codex/Claude registration. All installation, credential and protocol handling is deterministic code. The existing host agent collects non-secret selectors and invokes the bundled helper. There is no new model, framework or persistent daemon.

Remove direct Codex timeout insertion, Claude settings writes and timeout-specific partial repair. Preserve the existing public setup flags and owned registration receipts. Native client commands own configuration writes; detect drift before and after those commands without claiming atomic preservation against all external writers. Check is credential-free and never creates state or starts a runtime.

Bundle discovery metadata generated from the checksum-verified official executable and exact immutable MCP arguments. The bridge owns client-side initialize, initialized, ping and discovery. It advertises pinned tools and resources without waiting on authentication. Integrity-bind the catalog into the runtime manifest. After credential preparation, launch the live stock MCP, initialize it privately and compare tools/resources with the pinned catalog before forwarding operations. Real Grafana frontend metadata is fetched by this live backend, never fabricated or replaced by a successful synthetic response.

The shell supervisor launches the local bridge before asynchronous credential preparation. Existing fresh tokens are frozen immediately; missing or stale tokens use bounded noninteractive refresh. Preparation, including backend readiness, has a 240-second deadline. Pending operations receive a fixed retryable error and never reach Grafana. Credential, worker or backend validation failure stops the owned connection. No background browser sign-in is permitted. Keep token bytes within helper/runtime processes and protected storage; install output guards before enabling the backend. Preserve generation binding, one-hour reuse, ten-hour renewal, eleven-hour operational caps and rotation exit 75. The one-hour limit applies to credential admission (inspection, freezing and backend loading). When attaching the watchdog, generation-observed instead requires 0 <= observation age < STOP_AGE, retaining schema/hash/private-file checks and the original observation. Keep watchdog timing, outputs, errors and all persistent formats unchanged. This repairs CR-GRAFANA-003 without extra refreshes or startup grace periods.

Acquire only the checksum-pinned official release into the private owned version directory. Reuse validated bytes offline. Separate structural ownership discovery from executable availability so a missing owned binary produces update_required and normal invocation can reacquire it. Never silently replace altered bytes, malformed provenance or unsafe paths. Publish the receipt last and retain interruption recovery only for exactly verified artifacts. No Homebrew or legacy path remains.

Setup still prepares authentication before native registration and performs a bounded independent protocol conversation plus one datasource read. Retry only the explicit preparation-pending response within the existing 300-second verification budget. Registration, authenticated runtime readiness and current-client activation remain separate statuses. Keep exact datasource health forwarding, finite proxy limits, TLS/origin restrictions and token redaction unchanged.

#### Selected Option

Eliminate direct shared-settings writes through immediate local protocol discovery and asynchronous authenticated backend preparation. Own the official executable. This preserves one-invocation installation and avoids package-manager lifetime coupling.

#### Alternatives Considered

An installer-only lock cannot protect uncooperative writers. Native configuration APIs alone do not cover both clients' timeout settings. Continuing to reference Homebrew files retains the recovery defect. Serving fabricated Grafana metadata or weakening token freshness is rejected. A persistent daemon and legacy migration layers are unnecessary for this unreleased skill.

#### Implementation Boundaries

Confine changes to this skill folder, its root README table row and one concise CHANGELOG entry. Restore shared/preamble.md, SECURITY.md, CONTRIBUTING.md and every other skill to the PR base. Preserve all other root documentation, CI, root evals, plugin manifests, donor source and actual installed client/auth state. This skill's generated block stays identical to the shared preamble; local invocation and credential instructions sit outside it. Existing prerequisites are checked, not installed. PR 8 remains Draft until separately requested otherwise.

#### Test-First Success Criteria

- TDD-001: Prove client timeout/settings writes are absent, including concurrent external settings edits.
- TDD-002: Block authentication behind a barrier and prove initialization/discovery remain within native startup defaults; pending calls perform no Grafana reads and become usable after valid preparation.
- TDD-003: Prove owned binary offline reuse, missing-file recovery, checksum/path/provenance rejection and receipt-publication interruption recovery.
- TDD-004: Preserve protocol privacy, catalog matching, cancellation, worker cleanup, generation freshness, renewal and operational deadlines.
- TDD-005: Freeze synthetic credentials at observation plus 3599 seconds, then attach the watchdog at plus 3601 using a mocked clock. Preserve original observation/file bytes, reject new loading after one hour, and enforce the original eleven-hour cap including invalid metadata and permission cases.

#### Validation Plan

Run targeted tests first, then the full skill-local suite, Ruff, ShellCheck, Bash syntax, structural/spec checks and scoped align. Compare the complete PR diff with its base to enforce the root/shared boundary. CI expansion remains deferred.

#### Test Plan

Use synthetic credentials, fake Nebius executables, temporary homes and local HTTP fixtures. Verify actual protocol flows and native client registration separately. Validate the pinned official MCP against the catalog with no cloud credentials; native client checks use disposable homes. Do not perform real authentication or modify installed clients.

#### Evaluation Plan

Update local scenarios for invocation-driven installation, immediate discovery, pending/failed authentication, runtime readiness, default client timeouts and owned binary recovery. Model-run evaluation remains distinct from deterministic test evidence.

#### Rollout And Rollback

The skill is unreleased and has no existing users. Use one canonical implementation without migration or compatibility branches. Keep PR 8 Draft and do not commit or push as part of this implementation request. Retain immutable bundles and preserve actual user installations. Runtime verification failures remain explicit rather than reporting installation success.

#### Done Definition

The shared-settings, binary-ownership and watchdog-boundary findings are resolved, focused verification and scoped alignment pass, and only the skill plus its permitted README/changelog rows differ from the PR base. Source, isolated native and live evidence are reported separately.

#### Implementation Evidence

The v13 startup and binary-ownership changes remain intact. CR-GRAFANA-003 is implemented in token_state.py: generation-observed validates against STOP_AGE while inspection, freezing and backend loading retain MAX_STARTUP_AGE. Original metadata, watchdog timing, errors and output formats are unchanged. Five deterministic tests cover the boundary, admission restrictions, original deadline and malformed/private-file rejection. Skill-local lifecycle documentation and the existing concise changelog entry describe the distinction.

#### Verification Evidence

On 2026-09-14, the new mocked-clock regression failed before the source fix and passed afterward. All five new tests passed independently, and the full skill suite passed 110 tests in 180.472 seconds. Ruff, ShellCheck, Bash syntax, Python AST, JSON, local links, Markdown, shared-preamble/frontmatter, spec and whitespace checks passed. Scoped code/security review found no additional defect. Changes from the prior working baseline are confined to the skill and its existing changelog entry; the complete PR diff retains only the permitted skill, README row and changelog entry, and PR 8 remains Draft. Earlier isolated native/distribution/catalog checks are historical evidence, not reruns for this fix. Live/platform and cross-catalog validator limitations remain documented in references/validation.md.

<!-- /FEATURE: FEAT-001 -->
<!-- maintain-project-specs:design:end -->
<!-- markdownlint-enable MD001 MD024 -->
