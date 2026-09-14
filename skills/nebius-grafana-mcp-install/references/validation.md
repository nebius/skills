# Validation evidence

The agent-run revision was validated on macOS on 2026-09-14. All new credential
and Grafana data were synthetic. Existing installed skills, actual client
registration and authentication state were preserved; no live token was issued.

| Evidence | Result |
| --- | --- |
| Full deterministic suite | 92 tests passed in 147.559 seconds, including setup, artifacts, actual wrapper subprocesses, HTTP proxy, MCP protocol and renewal/rotation |
| Final focused regressions | Paused-wrapper/stalled-MCP cleanup and malformed-owned-binding cases pass in the full 92-test suite |
| Native client registration | Actual Codex and Claude CLIs passed initial registration, repeat apply, owned-binding reuse, local check and helper readiness in disposable homes with synthetic authentication/MCP fixtures |
| Browser-required workflow | A synthetic CLI requiring browser-mode authentication resumed setup and verification; its diagnostic login URL stayed out of helper output |
| Readiness transport | Actual synthetic stdio to bridge to credential proxy to local HTTP datasource read passed; the production wrapper was separately exercised for both clients |
| Datasource health | Healthy and error JSON, unsupported-handler HTTP status, UID verification and exact method/body/query/neighbor restrictions passed |
| Repository validation | scripts/validate.sh passed shared preamble sync, frontmatter, Agent Skills spec, manifest versions and native Claude plugin validation |
| Code checks | Ruff, ShellCheck, Python AST, Bash syntax, JSON parsing and git diff whitespace passed |
| Markdown | No introduced diagnostics relative to HEAD, with existing line-length and generated-table exclusions; unrelated baseline Markdown style issues remain |
| Security and code review | Prior origin-selection and paused-wrapper findings remain covered; the subsequent explicit alignment review found no additional code or security defects |
| Behavioral definitions | Skill-local scenarios updated for automatic setup, missing selectors, privacy, host activation and datasource-health separation; these are definitions, not model-run evidence |
| CI coverage | Root CI and eval discovery unchanged by explicit scope decision; run the skill-local suite separately |
| Fresh skill/model behavior | NOT_RUN; installed skill directories and the active host were preserved |
| Live browser/Grafana access | NOT_RUN for this revision; synthetic sign-in and HTTP tests do not prove live identity, entitlement or endpoint compatibility |
| Live renewal/current-chat activation | NOT_RUN; accelerated lifecycle fixtures do not prove future human-login renewal or host reconnection |
| Linux execution | NOT_RUN; GNU stat fixture coverage on macOS does not establish complete Linux support |

The health regression failed against the previous proxy before the exact-route
repair. Read-only review independently reproduced both selector and paused
process defects. The repaired paused-wrapper/stalled-MCP reproduction completed
in 2.8 seconds with no surviving bridge group. Its regression waits for an
initialize request to reach the stalled fixture before suspending the wrapper.

The first full revision run found an obsolete fixture expectation for the
pinned MCP datasource-list result. Updating that expectation from an array to
the upstream result object resolved the failure; the full suite above passed.
The defensive shape check for malformed owned environment bindings and the
strengthened stalled-child cleanup case also pass in the full alignment run.

Earlier human-operated source, native-client and live compatibility evidence is
historical and does not verify this revised installation workflow. Existing
renewal, original observation timestamps, frozen generations, concurrency and
interrupted-publication tests remain in the suite. No check establishes
uninterrupted operation, authoritative token expiry or merge approval.

The directory-lock protocol and explicit residue-recovery boundary are
unchanged. Age-based incomplete-lock recovery against a paused initializer
remains unproven and outside this revision. Same-user file/process access,
upstream DNS establishment limits and unrelated secrets in telemetry remain
explicit in [runtime security](runtime-security.md) and
[authentication lifecycle](auth-lifecycle.md).
