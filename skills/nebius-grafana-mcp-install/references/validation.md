# Validation evidence

## Restricted discovery descriptions

Validated on macOS on 2026-09-27 in an isolated tree combining the latest base
branch with the installer changes:

- All 117 deterministic tests passed in 178.173 seconds, including description
  projection, raw-catalog immutability and drift rejection, stable discovery
  before/after readiness, and unsupported-route rejection without upstream I/O.
- The official checksum-verified MCP 1.4.0 executable reproduced the unchanged
  pinned catalog. Client descriptions are a separate in-memory view.
- Actual Codex and Claude CLIs passed initial and repeat registration, synthetic
  authenticated readiness, and local checks in disposable homes. These checks
  do not establish live Nebius/Grafana access or current-chat activation.
- Repository validation passed for all 14 skills, including shared-preamble,
  frontmatter, skills-ref, manifest and native Claude plugin checks. Ruff,
  ShellCheck, Bash syntax, Python AST and JSON checks passed.
- Independent review found no blocking defect. The proxy policy, credential
  handling, runtime inventory and pinned catalog were unchanged.
- The final PR scope is the installer folder and one README table row; the root
  changelog matches the base. Existing project requirements/design stay intact.

The live-access, renewal, Linux and model-evaluation limits below still apply.
Default Markdown lint is not fully clean: existing line-length/table style
findings remain, and the base README/shared preamble also have missing code-fence
languages and a table-column issue. No shared policy or lint configuration was
changed to address those out-of-scope findings.

## Previous watchdog boundary validation

The watchdog boundary fix was validated on macOS on 2026-09-14.
Credentials and Grafana data in tests were synthetic. Native client checks used
disposable homes in the preceding revision; those checks were not rerun for
this boundary fix. Actual installed client/authentication state was preserved.

| Evidence | Result |
| --- | --- |
| Full deterministic suite | 110 tests passed in 180.472 seconds: setup, owned artifacts, frontend routing, actual wrapper subprocesses, HTTP proxy, protocol protection and token lifecycle |
| Watchdog boundary regression | A synthetic generation frozen at observation plus 3599 seconds failed attachment at plus 3601 before the source fix and passed afterward; five new mocked-clock tests cover original metadata/deadline preservation, unchanged admission checks, operational cutoff and invalid/private-file rejection |
| Startup separation | With token minting delayed 12 seconds, initialization and tool/resource discovery completed within 5 seconds; pending calls returned the fixed retryable response and no stock backend had started |
| Preparation deadline | The actual wrapper with a shortened fixture deadline terminated a stalled backend while client stdin remained open; elapsed time and owned-child cleanup were verified |
| Binary recovery | Missing owned executable remained discoverable, check requested update, and apply restored it; byte/mode/path/provenance drift failed closed; receipt interruption and offline reuse passed |
| Shared configuration | Native MCP registration passed without timeout insertion or settings.json creation; existing, symlinked and concurrently edited Claude settings remained untouched |
| Pinned discovery catalog (preceding revision) | capture_catalog.py --check reproduced the committed catalog from the checksum-verified official MCP 1.4.0: 22 tools, one resource, no templates; isolated loopback endpoint and no cloud credentials |
| Native clients (preceding revision) | Actual Codex and Claude CLIs passed initial registration, repeat apply, owned-binding reuse, local check and helper readiness in disposable homes with synthetic authentication/MCP |
| Skill distribution (preceding revision) | skills 1.5.26 discovery, Codex/Claude copy parity, repeat install and isolation passed in disposable homes |
| Repository validation | Shared-preamble and frontmatter checks passed for all eleven skills after the boundary fix; the preceding revision also passed scripts/validate.sh, including skills-ref, manifests and native Claude plugin validation |
| Code and docs | Ruff, ShellCheck, Bash syntax, Python AST, JSON parsing, local links, spec validation, scoped Markdown and diff whitespace passed |
| Read-only review | Focused review of the watchdog fix and five new tests found no additional defect; independent execution of those five tests passed |
| Security review | One-hour credential admission, original operational deadline, metadata validation and private-file/output protection remain intact; no new unresolved finding in this change |
| Scope | Only the installer folder, its existing root README table row and one concise changelog entry differ from the PR base; PR remains Draft |
| Behavioral definitions | Six canonical trigger cases and local setup scenarios; STATIC_PASS, not model-run evidence |
| CI coverage | Root CI and eval discovery unchanged by explicit scope decision; run the skill-local suite separately |
| Fresh skill/model behavior | NOT_RUN; runtime trigger and comparative model-output quality were not exercised |
| Live browser/Grafana access | NOT_RUN; synthetic sign-in and HTTP tests do not prove live identity, entitlement or endpoint compatibility |
| Live renewal/current-chat activation | NOT_RUN; accelerated lifecycle fixtures do not prove future human-login renewal or host reconnection |
| Linux execution | NOT_RUN; GNU stat coverage on macOS does not establish complete Linux support |

## Additional validator limits

The separate cross-catalog align-skill structural validator reports the same
findings for this revision and an isolated HEAD baseline: list-valued
allowed-tools instead of its strict standard string, a repository-specific Help
contract, an incorrect implicit-invocation expectation, and a repo-root
validation command interpreted as a missing skill-relative resource. Its core,
Codex and Claude profiles therefore remain FAIL; this is not a full pass of that
validator. The target repository's own checks and actual distribution/client
checks above pass. Invocation controls and existing catalog conventions were
preserved; these unrelated format/policy differences were not changed.

## Evidence boundaries

The earlier two findings are resolved at their owners: the installer no longer
directly rewrites shared client settings, and it no longer records an externally
managed Homebrew executable. Native commands retain their own concurrency
semantics; before/after comparisons cannot promise protection against every
external writer. Initialization/discovery are local and cannot establish
successful authentication. Readiness still requires a real datasource list
through the authenticated backend.

CR-GRAFANA-003 is resolved in the frozen-generation reader: watchdog attachment
uses the original eleven-hour operational cap, while credential inspection,
freezing and backend loading retain the one-hour admission limit. The fix does
not refresh credentials, change observation metadata or extend the deadline.

Existing health routing, renewal, original observation timestamps, frozen
generations, concurrency, output protection and interrupted-publication cases
remain covered. No check establishes uninterrupted operation, authoritative
token expiry or merge approval. The unchanged directory-lock protocol's
age-based recovery against a paused initializer remains unproven. Same-user
file/process access, upstream DNS establishment limits and unrelated secrets in
telemetry remain explicit in [runtime security](runtime-security.md) and
[authentication lifecycle](auth-lifecycle.md).
