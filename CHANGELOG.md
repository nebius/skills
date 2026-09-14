# Changelog

All notable changes to this repository. Versioning is repo-wide semver; the plugin manifests carry the same version.

## 0.1.0 — Phase 1 (unreleased)

- Framework: root-as-plugin layout serving Claude Code, Codex, and `npx skills` from one tree; shared preamble stamped by `scripts/sync-shared.py`; validation via `scripts/validate.sh` (skills-ref, claude plugin validate, frontmatter/portability lint); CI workflow.
- Skills: `nebius-cloud-basics`, `nebius-compute-inventory`, `nebius-capacity-quotas`, `nebius-compute-provision`.
- Skills (Serverless, CLI ≥ 0.12.265): `nebius-serverless-setup`, `nebius-serverless-jobs`, `nebius-serverless-endpoints`, `nebius-serverless-data-secrets`, `nebius-serverless-troubleshooting` — deterministic `ai job`/`ai endpoint` flows with dry-run → cost → confirm → verify, encoding live-verified CLI footguns tagged with their tickets (MSPDEV-323/347/775/778/784) for removal when fixed.
- Skill `nebius-serverless-recipes`: end-to-end playbooks (1-GPU/multi-GPU training, vLLM serving, batch fan-out, checkpointed & preemptible fine-tuning, GitHub Actions CI), each keeping the Tier B gate and idle-cost rule; SSH and credential steps stay human-only.
- Added `nebius-grafana-mcp-install`: agent-run setup for Codex and Claude Code, with immediate discovery, private credentials, supervised renewal, consistent token lifetime checks and a recoverable owned runtime.
- Field-tested additions to the Serverless surface skills: `--args` splits on spaces not commas (jobs, endpoints); `torchrun` multi-GPU single-node + no multi-node (jobs); vLLM `vllm`-entrypoint form and `--runner pooling` embeddings (endpoints); bucket FUSE mounts are read-mostly, write via filesystem/boto3 (data-secrets); log retention not guaranteed after delete (troubleshooting); group-membership role-grant reference (setup, `references/iam-grants.md`).
- Safety: three-tier model (read / gated write / refuse) in every skill's prose and `allowed-tools`; Serverless additions — idle-cost guardrails for endpoints, mandatory job `--timeout`, `iam auth-public-key generate` carve-out (gated, file-only output, bounded expiry).
- Evals: 3+ scenarios per skill, including negative/safety cases (never leave a billable resource silently, never print a secret, never delete without listing).
