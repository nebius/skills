# Changelog

All notable changes to this repository. Versioning is repo-wide semver; the plugin manifests carry the same version.

## 0.1.0 — 2026-09-28

- Skill `nebius-public-docs`: public documentation research with citations, targeted Markdown retrieval, and optional operational handoffs; no Nebius account or CLI required. Added documentation-only preamble handling and narrowed CLI setup routing.

- Framework: root-as-plugin layout serving Claude Code, Codex, and `npx skills` from one tree; shared preamble stamped by `scripts/sync-shared.py`; validation via `scripts/validate.sh` (skills-ref, claude plugin validate, frontmatter/portability lint); CI workflow.
- Skills: `nebius-cloud-basics`, `nebius-compute-inventory`, `nebius-capacity-quotas`, `nebius-compute-provision`.
- Skills (Serverless, CLI ≥ 0.12.265): `nebius-serverless-setup`, `nebius-serverless-jobs`, `nebius-serverless-endpoints`, `nebius-serverless-data-secrets`, `nebius-serverless-troubleshooting` — deterministic `ai job`/`ai endpoint` flows with dry-run → cost → confirm → verify, encoding live-verified CLI footguns tagged with their tickets (MSPDEV-323/347/775/778/784) for removal when fixed.
- Skill `nebius-serverless-recipes`: end-to-end playbooks (1-GPU/multi-GPU training, vLLM serving, batch fan-out, checkpointed & preemptible fine-tuning, GitHub Actions CI), each keeping the Tier B gate and idle-cost rule; SSH and credential steps stay human-only.
- Field-tested additions to the Serverless surface skills: `--args` splits on spaces not commas (jobs, endpoints); `torchrun` multi-GPU single-node + no multi-node (jobs); vLLM `vllm`-entrypoint form and `--runner pooling` embeddings (endpoints); bucket FUSE mounts are read-mostly, write via filesystem/boto3 (data-secrets); log retention not guaranteed after delete (troubleshooting); group-membership role-grant reference (setup, `references/iam-grants.md`).
- Skill `nebius-billing` (CLI ≥ 0.12.277): the `billing v1alpha1 calculator` (Tier A `estimate`/`estimate-batch` for hourly/monthly prices of instances, disks, filesystems; `--offer-types` list vs contract; region from parent project; does not quote live spot) and the `billing pricing-policy` lifecycle for preemptible bids (Tier A list/get, Tier B create/update — max bid = on-demand − $0.01, `BLOCKED` when below spot, mutable only with no running VMs, tenant-quota-limited; Tier C delete).
- Preemptible dynamic pricing (jobs, endpoints, recipes): `--follows-spot-price` / `--spot-pricing-policy-id <id>` / `--on-demand` (mutually exclusive; spot flags require `--preemptible`; a pricing model is mandatory with `--preemptible` as of 2026-10-08). Create skeletons updated; jobs/endpoints reference `nebius-billing` for policy management and the cost figure, and defer preset discovery to the compute catalog.
- Version floor raised to CLI **≥ 0.12.277** across the Serverless skills (shared preamble, per-skill `compatibility`, README, create skeletons).
- Safety: three-tier model (read / gated write / refuse) in every skill's prose and `allowed-tools`; Serverless additions — idle-cost guardrails for endpoints, mandatory job `--timeout`, `iam auth-public-key generate` carve-out (gated, file-only output, bounded expiry).
- Evals: 3+ scenarios per skill, including negative/safety cases (never leave a billable resource silently, never print a secret, never delete without listing).
