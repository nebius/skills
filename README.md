# Nebius Agent Skills

Portable, pure-text agent skills for researching **Nebius AI Cloud** documentation and operating cloud resources with the `nebius` CLI. One repo serves three channels: a Claude Code plugin marketplace, a Codex plugin marketplace, and a plain `skills/` tree for `npx skills`.

No bundled server. Documentation research needs web access; operational skills use the `nebius` CLI.

> **Status: Phase 1 (private).** Not published anywhere until nebius org approval — see the project plan. Until the repo is public, replace `nebius/skills` in the commands below with a local checkout path or private URL.

## Skills

| Skill | What it does |
|---|---|
| [nebius-public-docs](skills/nebius-public-docs/SKILL.md) | Public documentation research: capabilities, configuration, supported versions, and documented limits with citations; no account or CLI required |
| [nebius-cloud-basics](skills/nebius-cloud-basics/SKILL.md) | Foundation: profiles, `--parent-id`/tenant resolution, JSON output, paging, async operations, safety tiers |
| [nebius-compute-inventory](skills/nebius-compute-inventory/SKILL.md) | Read-only inventory: instances, disks, filesystems, GPU clusters, images, platforms |
| [nebius-capacity-quotas](skills/nebius-capacity-quotas/SKILL.md) | "Can I launch 8×B200?" — capacity advice (tenant-scoped), reservations, quota allowances |
| [nebius-compute-provision](skills/nebius-compute-provision/SKILL.md) | Gated create/update of instances, disks, filesystems, GPU clusters — template-driven, preflighted |
| [nebius-serverless-setup](skills/nebius-serverless-setup/SKILL.md) | Non-interactive auth for agents/CI: service account + generated key, verified with a cheap read |
| [nebius-serverless-jobs](skills/nebius-serverless-jobs/SKILL.md) | Gated containerized GPU/CPU batch jobs — dry-run, cost statement, explicit timeout, status watching |
| [nebius-serverless-endpoints](skills/nebius-serverless-endpoints/SKILL.md) | Gated inference endpoints — managed URLs, token auth, smoke test, idle-cost guardrails |
| [nebius-serverless-data-secrets](skills/nebius-serverless-data-secrets/SKILL.md) | S3 volumes, MysteryBox env/registry secrets, injected config files, artifact egress |
| [nebius-serverless-troubleshooting](skills/nebius-serverless-troubleshooting/SKILL.md) | Job/endpoint diagnosis: states, bounded logs, error catalog with recovery actions |
| [nebius-serverless-recipes](skills/nebius-serverless-recipes/SKILL.md) | End-to-end playbooks: 1-GPU/multi-GPU training, vLLM serving, batch fan-out, checkpointed & preemptible fine-tuning, GitHub Actions CI |
| [nebius-devlabs](skills/nebius-devlabs/SKILL.md) | Interactive GPU/CPU development environments: templates, workspaces, web/SSH access, failed-job debugging, gated stop/restart |
| [nebius-billing](skills/nebius-billing/SKILL.md) | Price estimates (calculator: hourly/monthly for VMs, disks, filesystems) and pricing policies for preemptible (spot) VMs — cap the max spot price, the id behind `--spot-pricing-policy-id` |

Nebius **Token Factory** (inference / fine-tuning) is intentionally out of scope — it has a separate API and keys. See [Arindam200/nebius-skills](https://github.com/Arindam200/nebius-skills) for that lifecycle.

## Safety model

CLI skills ship the same three-tier model, in prose **and** in `allowed-tools`. The documentation skill reads public sources without running cloud commands or accessing credentials.

For CLI skills:

- **Tier A — read**: `list`/`get`/`get-by-name`/… run freely (pre-approved via `allowed-tools`).
- **Tier B — gated write**: `create`/`update`/`start`/`stop` — the agent prints the exact command, states effect and cost, and waits for explicit confirmation. Never pre-approved.
- **Tier C — refuse**: `delete`, `purge`, credential issuance, impersonation — never executed; the command is printed for a human to run.

Full rationale: [skills/nebius-cloud-basics/references/safety-tiers.md](skills/nebius-cloud-basics/references/safety-tiers.md) and [SECURITY.md](SECURITY.md).

## Scope and support

**Best-effort guidance, not official Nebius documentation.** These skills encode command shapes, flags, presets etc verified against a specific `nebius` CLI version; they drift as the CLI and the platform change. When a skill and [docs.nebius.com](https://docs.nebius.com) (or `nebius <command> --help`) disagree, the docs and the CLI win.

They are also instructions an agent acts on, and the tier model above is prose, not a sandbox — **review every command an agent proposes before letting it run**, especially provisioning, quota changes, and deletion.

Reporting problems:

- **Security** — a skill that emits credentials, runs or induces something destructive, or looks deliberately malicious: report privately via the GitHub Security Advisory ["Report a Vulnerability"](https://github.com/nebius/skills/security/advisories/new) tab, not a public issue.
- **Incorrect guidance** — a wrong flag, a command the CLI no longer has: open an [issue](https://github.com/nebius/skills/issues/new) with the skill name, the command, your `nebius version`, and what actually happened.

## Install

The documentation skill requires only web access. Operational skills require: `nebius` CLI ≥ 0.12.247 with a configured profile ([docs](https://docs.nebius.com/cli)). The `nebius-serverless-*` skills need ≥ 0.12.265 (`--dry-run`, `iam auth-public-key generate`) — `nebius update` gets you there.

The `nebius-devlabs` skill uses CLI ≥ 0.12.277 as its verified compatibility floor.

### Claude Code

```
/plugin marketplace add nebius/skills
/plugin install nebius-cloud@nebius
```

Or non-interactively:

```bash
claude plugin marketplace add nebius/skills && claude plugin install nebius-cloud@nebius
```

To pin a release instead of tracking `main`: `/plugin marketplace add nebius/skills@v0.1.0`.

### Codex

```bash
codex plugin marketplace add nebius/skills
```

then restart Codex and enable the `nebius-cloud` plugin (or install it from the `/plugins` browser in the TUI).

Codex does not auto-update marketplaces — pull new releases with `codex plugin marketplace upgrade nebius`. To pin a release: `codex plugin marketplace add nebius/skills --ref v0.1.0`.

### Anything else ([Agent Skills](https://agentskills.io)-compatible)

```bash
npx skills add nebius/skills
```

As a last resort, copy `skills/*` into your agent's skills directory (e.g. `~/.claude/skills/`) — works, but you get no versioning and no update path.

### Teams

To roll the plugin out to a whole team, add it to a shared or managed `settings.json` ([docs](https://code.claude.com/docs/en/plugin-marketplaces)):

```json
{
  "extraKnownMarketplaces": {
    "nebius": {
      "source": { "source": "github", "repo": "nebius/skills" },
      "autoUpdate": true
    }
  },
  "enabledPlugins": ["nebius-cloud@nebius"]
}
```

## Repository layout

```
.agents/plugins/     Codex marketplace manifest
.claude-plugin/      Claude Code marketplace + plugin manifest (plugin root = repo root)
.codex-plugin/       Codex plugin manifest
evals/               ≥3 scenarios per skill
scripts/             sync + validation tooling
shared/preamble.md   CLI ground rules stamped into operational skills (scripts/sync-shared.py)
skills/              canonical skill payload — spec-conformant, vendor-neutral
```

## Development

```bash
bash scripts/validate.sh          # everything CI runs
python3 scripts/sync-shared.py    # re-stamp shared/preamble.md into CLI skills
```

Authoring conventions live in [CONTRIBUTING.md](CONTRIBUTING.md). Key invariants: frontmatter uses only the six Agent Skills spec keys; descriptions ≤ 600 chars; bodies ≤ 500 lines; no real tenant/project IDs anywhere in the repo.

## License

© 2026 Nebius BV

Apache-2.0 — see [LICENSE](LICENSE).
