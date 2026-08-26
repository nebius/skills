# Changelog

All notable changes to this repository. Versioning is repo-wide semver; the plugin manifests carry the same version.

## 0.1.0 — Phase 1 (unreleased)

- Framework: root-as-plugin layout serving Claude Code, Codex, and `npx skills` from one tree; shared preamble stamped by `scripts/sync-shared.py`; validation via `scripts/validate.sh` (skills-ref, claude plugin validate, frontmatter/portability lint); CI workflow.
- Skills: `nebius-cloud-basics`, `nebius-compute-inventory`, `nebius-capacity-quotas`, `nebius-compute-provision`.
- Safety: three-tier model (read / gated write / refuse) in every skill's prose and `allowed-tools`.
- Evals: 3 scenarios per skill.
