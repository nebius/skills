# Nebius Agent Skills

Portable, pure-text agent skills for operating **Nebius AI Cloud** with the `nebius` CLI. One repo serves three channels: a Claude Code plugin marketplace, a Codex plugin marketplace, and a plain `skills/` tree for `npx skills`.

No server, no runtime dependency beyond the `nebius` CLI you already have.

> **Status: Phase 1 (private).** Not published anywhere until nebius org approval — see the project plan. Until the repo is public, replace `nebius/skills` in the commands below with a local checkout path or private URL.

## Skills

| Skill | What it does |
|---|---|
| [nebius-cloud-basics](skills/nebius-cloud-basics/SKILL.md) | Foundation: profiles, `--parent-id`/tenant resolution, JSON output, paging, async operations, safety tiers |
| [nebius-compute-inventory](skills/nebius-compute-inventory/SKILL.md) | Read-only inventory: instances, disks, filesystems, GPU clusters, images, platforms |
| [nebius-capacity-quotas](skills/nebius-capacity-quotas/SKILL.md) | "Can I launch 8×B200?" — capacity advice (tenant-scoped), reservations, quota allowances |
| [nebius-compute-provision](skills/nebius-compute-provision/SKILL.md) | Gated create/update of instances, disks, filesystems, GPU clusters — template-driven, preflighted |

Nebius **Token Factory** (inference / fine-tuning) is intentionally out of scope — it has a separate API and keys. See [Arindam200/nebius-skills](https://github.com/Arindam200/nebius-skills) for that lifecycle.

## Safety model

Every skill ships the same three-tier model, in prose **and** in `allowed-tools`:

- **Tier A — read**: `list`/`get`/`get-by-name`/… run freely (pre-approved via `allowed-tools`).
- **Tier B — gated write**: `create`/`update`/`start`/`stop` — the agent prints the exact command, states effect and cost, and waits for explicit confirmation. Never pre-approved.
- **Tier C — refuse**: `delete`, `purge`, credential issuance, impersonation — never executed; the command is printed for a human to run.

Full rationale: [skills/nebius-cloud-basics/references/safety-tiers.md](skills/nebius-cloud-basics/references/safety-tiers.md) and [SECURITY.md](SECURITY.md).

## Install

Prerequisite everywhere: `nebius` CLI ≥ 0.12.247 with a configured profile ([docs](https://docs.nebius.com/cli)).

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
shared/preamble.md   shared block stamped into every SKILL.md (scripts/sync-shared.py)
skills/              canonical skill payload — spec-conformant, vendor-neutral
```

## Development

```bash
bash scripts/validate.sh          # everything CI runs
python3 scripts/sync-shared.py    # re-stamp shared/preamble.md into all skills
```

Authoring conventions live in [CONTRIBUTING.md](CONTRIBUTING.md). Key invariants: frontmatter uses only the six Agent Skills spec keys; descriptions ≤ 600 chars; bodies ≤ 500 lines; no real tenant/project IDs anywhere in the repo.

## License

© 2026 Nebius BV

Apache-2.0 — see [LICENSE](LICENSE).
