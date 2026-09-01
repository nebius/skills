# Changelog

All notable changes to this repository. Versioning is repo-wide semver; the plugin manifests carry the same version.

## 0.1.0 — Phase 1 (unreleased)

- Framework: root-as-plugin layout serving Claude Code, Codex, and `npx skills` from one tree; shared preamble stamped by `scripts/sync-shared.py`; validation via `scripts/validate.sh` (skills-ref, claude plugin validate, frontmatter/portability lint); CI workflow.
- Skills: `nebius-cloud-basics`, `nebius-compute-inventory`, `nebius-capacity-quotas`, `nebius-compute-provision`.
- Skills (Serverless, CLI ≥ 0.12.265): `nebius-serverless-setup`, `nebius-serverless-jobs`, `nebius-serverless-endpoints`, `nebius-serverless-data-secrets`, `nebius-serverless-troubleshooting` — deterministic `ai job`/`ai endpoint` flows with dry-run → cost → confirm → verify, encoding live-verified CLI footguns tagged with their tickets (MSPDEV-323/347/775/778/784) for removal when fixed.
- Safety: three-tier model (read / gated write / refuse) in every skill's prose and `allowed-tools`; Serverless additions — idle-cost guardrails for endpoints, mandatory job `--timeout`, `iam auth-public-key generate` carve-out (gated, file-only output, bounded expiry).
- Evals: 3+ scenarios per skill, including negative/safety cases (never leave a billable resource silently, never print a secret, never delete without listing).
