# Validation evidence

Validation on 2026-09-11 covers the source implementation on macOS. Existing
installed skills, actual client registration and authentication state were not
changed. No live token was issued for development.

| Evidence | Result |
| --- | --- |
| Offline deterministic suite | Full 70-test suite passed in 105.631 seconds before publication, covering setup, artifacts, actual wrapper subprocesses, local HTTP and stdio. |
| Native client registration | Actual Codex and Claude CLIs passed registration, repeat apply and local check in temporary homes with synthetic authentication/MCP fixtures |
| Live proxy compatibility | Locked official Grafana MCP 1.4.0 passed initialize, tool listing and a datasource read through the new proxy/stdio guard with an existing protected credential |
| Repository validation | Full scripts/validate.sh passed: shared preamble, frontmatter, Agent Skills spec, manifest consistency and Claude plugin validation |
| Code checks | Ruff, ShellCheck, Python/Bash syntax, JSON parsing and scoped Markdown lint passed |
| Security/code review | All four review findings repaired and covered by focused checks; broader directory-lock recovery remains outside the accepted scope |
| Security hardening | PY-INPUT-001 (low): names already refused by runtime now fail before setup commands/state. The regression failed before repair; valid custom names retain both clients' apply, repeat, check and attestation behavior. Authentication, proxy and renewal are unchanged. |
| Trigger definitions | Six CSV cases: three positive and three meaningful near misses |
| Behavioral definitions | Eight repository-shaped JSON scenarios; root CI does not discover them |
| Fresh skill triggering | NOT_RUN; installed skill directories were preserved |
| Comparative output quality | NOT_RUN; deterministic checks and instruction review are not a clean model baseline comparison |
| Live renewal or client reconnection | NOT_RUN; long-session and rotation behavior tested with accelerated synthetic fixtures |
| Linux execution | NOT_RUN; GNU stat refresh/startup regression passed on macOS, without proving full Linux execution |

The subsequent scoped alignment reproduced and fixed a malformed Prometheus
probe error: null, list, string, numeric or boolean data now returns a sanitized
403 response, and the requested query is not forwarded. The regression failed
for all five shapes before the guard and passed afterward. Runtime help now
lists every required setup-owned environment binding, describes the renewal
delay accurately and supports custom names in restart guidance. The final
58-test run passed; native-client and live evidence above is from the preceding
implementation check and was not repeated for these local repairs.

The subsequent code review reproduced and repaired two additional defects.
The BSD-first stat fallback previously retained stdout from a failed GNU stat
invocation, so valid private files failed ownership checks. Failed probe output
is now discarded, and an actual GNU stat regression verifies refresh and MCP
startup. GNU documents its distinct -f and -c meanings in the
[stat manual](https://www.gnu.org/software/coreutils/manual/html_node/stat-invocation.html).
After a skill source update, credential-free check now reports status 3 and
setup/repair needed before probing the not-yet-staged bundle. Both client
adapters preserve all local files during that check; corruption of an expected
installed bundle still fails integrity validation. Both defect-specific tests
failed before repair and passed afterward. That 61-test suite and scoped
lint/syntax checks passed; no native-client or live test was repeated.

The accepted targeted recovery implementation repairs CR003 and CR004. Writer
PID discovery now precedes lock acquisition and creates no temporary file.
Concurrent reuse requires matching fresh observation metadata; incomplete
publication returns a normal failure so background retries remain available.
Four foreground/background crash and interrupted-publication tests reproduced
the defects before repair and passed afterward. Additional tests verify live
writer PID/start identity using a bounded synthetic mint barrier and preservation
of pre-fix residue for human recovery. The final 68-test suite passed in 106.353
seconds; scoped lint, syntax, wiring and follow-up code/security review passed.
All fault injection, credentials, processes and configuration were isolated
fixtures. Native-client and live evidence was not repeated.

These repairs close the two targeted findings, not every directory-lock failure
mode. Existing owner-pid.tmp residue is not automatically deleted. Age-based
incomplete-lock recovery against a paused initializer remains unproven and was
explicitly excluded from this repair. See [human recovery](auth-lifecycle.md)
for quiescence and exact-artifact handling; no current installation was changed.

The offline tests verify cloud/local credential separation, full-frame output
filtering including JSON-escaped reflection, redirect refusal toward a second
fixture server, route/method limits, custom Prometheus protocol validation,
Loki bounds, malformed/oversized responses, origin binding, immutable bundles,
partial recovery, credential-free checks and explicit renewal on owned update.

Actual supervisor subprocesses verify rotation exit 75, reconnection, repeated
cached bytes, concurrent renewal, renewal failure, frozen deadlines, watchdog
failure, delayed process-group creation and cancellation. Assertions check that
the stock MCP child PIDs are gone. Accelerated deadlines and synthetic binaries
exist only in temporary fixtures, never as production bypass options.

Native client tests exercise real configuration parsers/commands, including
Claude's first-write initialization metadata. They do not authenticate an agent
or prove skill triggering. The separate live check loaded an existing credential
inside the helper process, withheld resource content and confirmed the token
and client configuration were unchanged. It did not run installer apply, mint a
token, modify Grafana, test every query backend or repair the current chat's MCP.

The personal align-skill validator passes metadata, help, learning-loop and
trigger checks but reports one repository-layout false positive: the required
shared-preamble marker names scripts/sync-shared.py relative to the repository
root. That file exists; it is not an installed-skill dependency. The marker is
preserved verbatim and the repository synchronizer passes. Additional docs/
and tests/ folders are intentional review warnings. Markdown checking excludes
line-length and table-spacing rules to preserve the required preamble.

The scoped spec-pair publisher accepts the requirements/design pair. Its
standalone Git validator reports SPEC_REQUIRED while these new documents remain
untracked; implementation leaves all changes unstaged and uncommitted.

Evidence classification: STATIC_PASS with the documented generic-validator
exception; fresh skill activation and comparative model quality are NOT_RUN.
The unchanged repository credential-policy discrepancy, same-user access and
DNS establishment limit remain explicit in [runtime security](runtime-security.md).
No result establishes merge approval, authoritative token expiry or uninterrupted
operation beyond the renewal capabilities of a human login.
