<!-- markdownlint-disable MD001 MD024 -->
<!-- maintain-project-specs:design:start schema=maintain-project-specs/design-v2 -->
# Project Design

<!-- FEATURE: FEAT-001 reqs=REQ-001 status=ready delivery=verified priority=P0 version=12 -->
### FEAT-001: Agent-run setup and supervised credential proxy

#### Requirements Covered

- REQ-001: Self-contained agent-run Grafana MCP installation.

#### Context Evidence

The installer supports agent-run setup and exact datasource health reads. Its helper-owned authentication and private credential storage differ from the catalog's generic human-run credential rules. Document that bounded workflow only in this skill; restore shared policy and other skills to the PR base. Browser sign-in and client reload remain user steps only when necessary.

#### Design Details

Keep the Python 3.11+ standard library, Bash supervisor, pinned MCP 1.4.0 and native Codex/Claude clients. No model, framework or new autonomous agent is added. The existing host agent gathers non-secret selectors, invokes the fixed helper and reports sanitized outcomes; all credential and installation logic is deterministic code.

Retain --agent codex|claude, --check (default), --apply, --update and --mcp-server-name. Allow missing profile/origin/server selectors only when a unique validated installer-owned binding supplies them. Never infer a trusted destination from ambient profiles or another installer's config. Explicit conflicting selectors fail before authentication. Check reads no tokens, changes no files and starts no runtime. Agent invocation runs apply and selects update only when owned state requires it.

Setup checks prerequisites, validates ownership, materializes immutable code, acquires the checksum-verified executable, validates the pinned human identity, acquires credentials internally and registers the chosen client. The helper opens the official browser when authentication is needed; raw CLI output and login URLs stay internal. Bounded progress and structured final results expose only fixed statuses and safe remediation messages. The agent never reads token files, runs token commands itself or weakens native permissions.

Configure Codex startup_timeout_sec=300. For Claude, atomically patch only user settings env.MCP_TIMEOUT to at least 300000 milliseconds, retaining a larger valid value and all unrelated values. Snapshot before authentication and recheck before every mutation; a concurrent edit is retained and reported. Record installation separately from readiness so a verification failure can leave recoverable owned configuration without a false success claim.

After registration, a bounded helper subprocess launches the exact owned wrapper and performs initialize, initialized notification, tools/list and one list_datasources call. Validate responses internally, then stop and reap its owned process group. Never relay MCP payloads or stderr to the agent. The host agent separately verifies actual current-session availability when supported; otherwise request reload without killing the active client. Registration, independent runtime verification and host activation are separate evidence lanes.

Extend only exact `GET /api/datasources/uid/<uid>/health`, without body or query, and verify the UID through the bound Grafana first. Preserve same-origin TLS, redirect rejection, finite limits, private authentication and output guards. Do not invoke bulk datasource health during installation; an unhealthy or unsupported datasource is not an installation failure. Keep the advertised tool and fixed read-only MCP categories including --disable-proxied.

Retain existing protected token files, immutable origin/identity binding, frozen connection generations, one-hour reuse, ten-hour renewal and eleven-hour operational caps. These are observation-based limits, not authoritative expiry. Rotation exits 75 and may require reconnecting. Preserve the existing directory-lock repair and explicit recovery boundary; do not invent token ages or delete unknown residue.

#### Selected Option

Agent-run deterministic installer with a skill-specific credential boundary, exact health-route support and separate installation/runtime/activation results. Keep the generated catalog preamble unchanged and explain the helper's limited exception in this skill's own invocation instructions. Host and organization restrictions remain authoritative.

#### Alternatives Considered

The manual terminal handoff does not meet the requested experience. Hiding datasource health avoids forwarding but removes useful functionality. Broad proxy route access and an unconditional safety claim are rejected. Replacing the existing stack or stdio transport is unnecessary.

#### Implementation Boundaries

Confine changes to this skill folder, its root README table row and one concise CHANGELOG entry. Restore shared/preamble.md, SECURITY.md, CONTRIBUTING.md and every other skill to the PR base. Preserve all other root documentation, CI, root evals, plugin manifests, donor source and actual installed client/auth state. This skill's generated block stays identical to the shared preamble; local invocation and credential instructions sit outside it. Existing prerequisites are checked, not installed. PR 8 remains Draft until separately requested otherwise.

#### Test-First Success Criteria

- TDD-001: Reproduce health-route refusal before repair, then prove healthy/error/unsupported responses and all route restrictions.
- TDD-002: Prove both-client automatic setup, owned selector resolution, missing/ambiguous input handling, timeout preservation, interrupted recovery and drift refusal with isolated fixtures.
- TDD-003: Inject credentials/login URLs into subprocess failures and protocol responses; no agent-visible output may contain them. Bound malformed, oversized, missing or stalled MCP responses and reap descendants.

#### Validation Plan

For runtime changes, run scoped Python/Bash checks and the full skill-local suite. For this documentation-only scope correction, verify exact equality of restored files to the PR base, only the allowed README/changelog additions, shared-preamble synchronization, local links/JSON, spec validation, repository structural validation, read-only risk review and align. Do not add CI jobs or claim source tests establish live activation.

#### Test Plan

Use fake Nebius/client/MCP executables, local HTTP fixtures and temporary homes. Verify actual protocol exchange, fixed MCP arguments, current config attestation, health forwarding and output privacy. Retain cancellation, rotation, concurrency and immutable-bundle regressions. Native-client verification uses disposable homes and synthetic auth only; real authentication is outside development scope.

#### Evaluation Plan

Update local scenarios for explicit invocation, non-secret questions, browser sign-in, automatic apply/update, protected output, client reload and unrelated-registration refusal. Model evals remain separate from deterministic tests; CI remains unchanged.

#### Rollout And Rollback

Return PR 8 to Draft, update the current branch and retain immutable runtime bundles. Repeated skill invocation reconciles only owned state. Do not automatically delete state, restore old credentials or terminate active clients. A readiness failure retains independently verified registration with a clear failure status.

#### Done Definition

The installer and skill-specific instructions pass focused verification and alignment. The complete diff outside the skill contains only its README table row and concise CHANGELOG entry. The final report distinguishes local/source proof from any unperformed live/browser/current-client activation checks.

#### Implementation Evidence

Implemented agent-run bundled setup with owned selector reuse, sanitized progress/results, automatic Claude settings, private MCP readiness and exact datasource health forwarding. Tests cover input reuse, configuration drift, browser-mode authentication, protocol failures and process cleanup. Restored shared/root policy and other skills to the PR base, retained only the allowed catalog rows, and localized the installer instructions and evidence without changing runtime code. The skill explicitly documents its credential-workflow deviation from generic catalog rules and respects higher-priority restrictions.

#### Verification Evidence

Revision verification: the full 92-test synthetic suite passed in 147.559 seconds, including strengthened paused-wrapper cleanup and malformed-binding regressions. Both actual native client CLIs passed registration, repeat apply, owned reuse, local check and synthetic runtime verification in temporary homes. Root validation, Ruff, ShellCheck, syntax/JSON and diff checks passed; Markdown has no introduced diagnostics relative to the baseline with documented style exclusions. Independent code/security review reproduced and verified repairs for origin selection and stopped-wrapper cleanup. The subsequent explicit alignment review found no additional code or security defects. Live authentication/Grafana access, Linux execution, live renewal, fresh model invocation and current-client activation are not claimed. See references/validation.md for evidence boundaries.

Scope-correction verification: exact comparison with the PR base confirms that only one README table row and one concise CHANGELOG entry differ outside this skill. All eleven generated preambles synchronize with the unchanged source. Repository structural validation, spec validation, JSON parsing, local link checks, diff whitespace and scoped Markdown checks passed. Independent read-only review found no introduced serious defect; the documented difference from generic catalog credential rules remains. Runtime scripts and tests match the previously validated revision, so the runtime suite was not repeated for this documentation-only correction.

<!-- /FEATURE: FEAT-001 -->
<!-- maintain-project-specs:design:end -->
<!-- markdownlint-enable MD001 MD024 -->
