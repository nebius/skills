# Safety tiers — the full model

Every nebius CLI operation falls into exactly one tier. When in doubt, treat a command as the higher (more restrictive) tier.

| Tier | Operations | Agent behavior |
|---|---|---|
| **A — Read** | `list`, `get`, `get-by-name`, `batch-get`, `describe`, `list-operations-by-parent`, `list-public`, `get-latest-by-family`, `logs`, `operation get/list/wait`, `capacity resource-advice list`, `quotas quota-allowance list/get/get-by-name`, `billing v1alpha1 calculator estimate*`, `iam whoami`, `profile list/current`, `config get/list`, `--help` | Run freely. These are enumerated in each skill's `allowed-tools`. |
| **B — Gated write** | `create`, `update`, `start`, `stop`, `undelete`, `quotas quota-allowance create/update`, `capacity capacity-allowance create/update` | Print the resolved command **verbatim** (including `--parent-id` and any rendered template file), state what it will create/change and its cost implication, wait for explicit user confirmation, then run exactly once. Never batch mutations; never retry a mutation after an ambiguous failure. |
| **C — Refuse** | `delete`, `purge`, `quotas quota-allowance delete`, `capacity capacity-allowance delete`, `profile delete`, `iam access-key` / `iam v2 access-key` / `static-key` / `auth-public-key` (create/get), `iam get-access-token`, anything with `-I`/`--impersonate-service-account-id`, any command that emits or accepts token/key material | Do not run — even if asked directly. Print the exact command for the human to run themselves and explain the blast radius (what is destroyed, whether it is reversible, what depends on it). |

## Why these lines are where they are

- **Deletes are refused, not gated**, because confirmation fatigue is real: an agent that "usually asks" will eventually delete on a misread. Structural refusal is testable and predictable. `compute instance delete` also deletes the managed disks declared in the instance spec — the blast radius is bigger than the command name suggests.
- **`stop` is gated, not free**, because stopping an instance releases non-reserved GPU capacity; in a tight market you may not get the same capacity back on `start`.
- **Credential issuance is refused** because an agent transcript, log, or context window is not a safe place for a bearer token or key material. This mirrors the Nebius MCP server, which forbids commands that accept or return tokens/keys.
- **Impersonation is refused** because it silently swaps the identity every subsequent audit line is attributed to. Note that `-I` is its short alias and, being a global flag, it rides on *any* command — a Tier A read with `-I serviceaccount-...` is still Tier C.

## Non-obvious hazards (repeat offenders)

- `edit` / `edit-by-name` open `$EDITOR` and **hang** a non-interactive shell. Always use `update` (explicit flags or `-f <file>`).
- `-i` / `--interactive` renders alternate-screen pagination and waits for keypresses. Always use `--all` or explicit paging.
- `--follow` streams until killed and **hangs** an unattended session. It exists on `compute instance logs` (not just `logging query`) — read logs as a bounded, one-shot call.
- `nebius profile create` opens a browser for SSO — human-only.
- `update` without care can clear fields: `-f <file>` implies `--full` (the file *replaces* the spec). For small changes prefer explicit field flags; for file-driven updates, start from `get --format yaml` output so the file carries the complete current spec.
