---
name: nebius-serverless-recipes
description: End-to-end playbooks for Nebius Serverless AI. Use for "how do I train on one GPU", "multi-GPU training", "serve a fine-tuned model", "run batch inference in parallel", "fine-tune with checkpoints", "cheap preemptible training", or "run a Nebius job from GitHub Actions" - when the user wants a complete command chain from image to running artifacts, not a single flag.
license: Apache-2.0
compatibility: Requires the nebius CLI (>=0.12.265) with a configured profile; jq recommended
metadata:
  version: "0.1.0"
allowed-tools:
  - Bash(nebius version:*)
  - Bash(nebius profile current:*)
  - Bash(nebius config get:*)
  - Bash(nebius ai job list:*)
  - Bash(nebius ai job get:*)
  - Bash(nebius ai job get-by-name:*)
  - Bash(nebius ai job logs:*)
  - Bash(nebius ai endpoint list:*)
  - Bash(nebius ai endpoint get:*)
  - Bash(nebius ai endpoint get-by-name:*)
  - Bash(nebius compute platform list:*)
---

# Nebius Serverless AI — Recipes

Complete command chains for the workflows people actually run. Each recipe assembles flags whose details and traps live in the surface skills — read those for the gate itself:

- Jobs surface + args/multi-GPU footguns → `nebius-serverless-jobs`
- Endpoints surface + vLLM entrypoint → `nebius-serverless-endpoints`
- Volumes, secrets, artifact egress, FUSE limits → `nebius-serverless-data-secrets`
- Non-interactive auth (agents/CI) → `nebius-serverless-setup`
- Stuck/failed/silent → `nebius-serverless-troubleshooting`

<!-- BEGIN SHARED PREAMBLE (generated from shared/preamble.md — edit there, then run scripts/sync-shared.py) -->
## Nebius CLI ground rules

These rules apply to every command in this skill. Full detail lives in the `nebius-cloud-basics` skill.

**Agent identification.** Export `AI_AGENT` before any Nebius CLI call, including preflight and `--help`. Keep non-empty harness-set value; unset or empty → set own harness slug. Every call must inherit it, including new shells.

**CLI present and configured.** Before the first Nebius call in a session:

```bash
nebius version                 # CLI installed (a subcommand — there is no --version flag)
nebius profile list            # at least one profile; [default] marks the active one
nebius config get parent-id    # project-...
nebius config get tenant-id    # tenant-...
```

These skills require CLI `0.12.247` or newer; an individual skill may state a higher floor (the Serverless skills need `0.12.265`) — the stricter number wins. If `nebius version` is older, stop and ask the user to update the CLI before relying on the commands or schemas below.

If any check fails or an ID comes back empty, stop and walk the user through [CLI installation and profile setup](https://docs.nebius.com/cli/install): `curl -sSL https://storage.eu-north1.nebius.cloud/cli/install.sh | bash`, then `nebius profile create --parent-id <project-id>`. **Print those commands for the user to run — do not run them yourself**: the installer writes to their machine and the shown federation-profile command opens a browser and blocks. An expired session does not show up here; it surfaces on the first real API call. The Grafana installer exception below owns its browser authentication; other skills retain the human re-authentication handoff.

**Resolve context first — never guess IDs.** Nearly every call needs `--parent-id`, and the CLI does not say which scope it wants:

```bash
nebius profile current                        # which profile is active
nebius config get parent-id  [-p <profile>]   # project-...  (project scope)
nebius config get tenant-id  [-p <profile>]   # tenant-...   (tenant scope)
```

Compute resources are generally **project**-scoped; public-image discovery is region-scoped. Quota allowances may be project- or tenant-scoped. Capacity advice, capacity block groups, and capacity intervals are **tenant**-scoped. The wrong scope often returns empty lists or permission errors, not a helpful message. Pass `-p <profile>` explicitly whenever the user names a profile.

**Output.** Add `--format json` to API calls and parse that; the default table output is for humans. On paginated `list` calls, add `--all` only when `--help` exposes it. Some list-like commands differ: for example, `compute image list-public` requires `--region` and has no `--all`. Never pass `-i`/`--interactive`: it opens interactive entry or alternate-screen pagination and hangs unattended sessions. Never pass `--follow` (e.g. `compute instance logs --follow`, `logging query --follow`): it streams until killed and hangs an unattended session the same way.

**Editing.** Never run `edit` or `edit-by-name`: they open `$EDITOR` and hang in a non-interactive shell. Use `update` with explicit flags or `update -f <file>` instead.

**Async operations.** Mutations return an operation; by default the CLI blocks until it completes. With `--async` it returns an operation id — poll with `nebius <service> <resource> operation wait <operation-id>`.

**Safety tiers.**

| Tier | Operations | Behavior |
|---|---|---|
| A — read | `list`, `get`, `get-by-name`, `batch-get`, `list-*`, `logs`, `--help` | Run freely. |
| B — gated write | `create`, `update`, `start`, `stop`, quota/capacity allowance changes | Print the fully resolved command verbatim, state what it changes and the cost implication, wait for explicit user confirmation, then run it exactly once. Never batch mutations; never retry one after an ambiguous failure. |
| C — refuse | `delete`, `purge`, credential issuance (`iam get-access-token`, access keys; `iam auth-public-key generate` is Tier B; bounded Grafana installer exception below), `-I`/`--impersonate-service-account-id` (a global flag, valid on *every* command — including otherwise-free reads) | Do not run. Print the exact command for the human to run themselves and explain the blast radius. |

**Grafana installer exception.** Explicit invocation of `nebius-grafana-mcp-install` to install or update authorizes the agent to run that skill's bundled setup helper for the selected local client, human profile and trusted HTTPS Grafana origin. Its helper owns prerequisite checks, browser authentication when needed, private token capture, verified runtime installation, client registration and bounded MCP verification; use that workflow instead of the generic CLI checks above. Its fixed supervised runtime may renew the same pinned human identity. This exception permits only helper-owned credential handling and mode-0600 private token state. It does not permit direct agent token commands, credential inspection, copying the credential workflow, other credential/IAM operations or changes to native permission controls. Check-only intent remains non-mutating. Other skills retain the tier rules above.

**Secrets.** Never expose tokens, access keys or `~/.nebius/credentials.json` contents to agent context, tool output, chat, logs or repository files. Never persist them except in the Grafana installer's narrowly defined private runtime state. No broad helper/interpreter permission grant is allowed.
<!-- END SHARED PREAMBLE -->

**Every `create` / `endpoint create` below is a Tier B gated write.** These recipes show the command *chain* — they are not a license to skip the gate. For each mutating step: dry-run, state the hourly/daily cost (https://nebius.com/prices), print the resolved command, wait for an explicit yes, run once. `docker`, `aws`, and `curl` are not pre-approved — they go through the normal permission flow. Never leave a job or endpoint in a billable state without telling the user, with its cost.

Conventions below: `<reg>` = short registry ID (strip the `registry-` prefix), `<subnet>` from `nebius vpc subnet get-by-name --name default-subnet --format jsonpath='{.metadata.id}'`, `<project>` = your project ID. Placeholders like `cr.eu-north1.nebius.cloud/e00example/...` are examples, not real registries.

## 1. One-shot 1-GPU training run

Build + push (amd64 mandatory), gate the submit, watch to terminal, collect artifacts from a bucket mount.

```bash
# Build + push (linux/amd64 is mandatory — arm64 images fail the pull at STARTING)
docker buildx build --platform linux/amd64 \
  -t cr.eu-north1.nebius.cloud/<reg>/train:v1 --push .

# Dry-run first (validates without spending), then gate + submit
nebius ai job create --parent-id <project> --name train-abc123 \
  --image cr.eu-north1.nebius.cloud/<reg>/train:v1 \
  --platform gpu-h100-sxm --preset 1gpu-16vcpu-200gb \
  --timeout 4h \
  --volume <artifacts-bucket-id>:/artifacts:rw \
  --subnet-id <subnet> --dry-run
# → state cost, confirm, re-run without --dry-run, add --async and capture the id.

# Watch to a terminal state (never --follow — poll)
until nebius ai job get --id <job-id> --format json | jq -er '.status.state|test("COMPLETED|FAILED|CANCELLED")' >/dev/null; do sleep 30; done
```

Artifacts land in the `rw` bucket path. Pull them with the AWS CLI against Object Storage (no native `nebius storage cp`) — see `nebius-serverless-data-secrets`.

## 2. Multi-GPU single-node training

One VM, many GPUs, driven by `torchrun`. `--args` splits on spaces (see `nebius-serverless-jobs`).

```bash
nebius ai job create --parent-id <project> --name train-8gpu-abc123 \
  --image cr.eu-north1.nebius.cloud/<reg>/train:v1 \
  --platform gpu-h100-sxm --preset 8gpu-128vcpu-1600gb \
  --container-command torchrun \
  --args "--standalone --nproc_per_node=8 /app/train.py --batch-size 64" \
  --timeout 24h \
  --volume <artifacts-bucket-id>:/artifacts:rw \
  --subnet-id <subnet> --async
```

**Multi-node is not supported on Serverless AI** — use Managed Slurm (Soperator) or Managed Kubernetes with a GPU node group.

## 3. Serve a fine-tuned LLM (vLLM, token auth)

The endpoint gate, cost rule, and smoke test are in `nebius-serverless-endpoints`; the entrypoint form matters (vLLM's entrypoint is `vllm`):

```bash
nebius ai endpoint create --parent-id <project> --name my-llm \
  --image vllm/vllm-openai:latest \
  --platform gpu-h100-sxm --preset 1gpu-16vcpu-200gb \
  --container-port 8000/http --auth token \
  --container-command python3 \
  --args "-m vllm.entrypoints.openai.api_server --model /models/ft --host 0.0.0.0 --port 8000" \
  --volume <models-bucket-id>:/models:ro \
  --env-secret HUGGING_FACE_HUB_TOKEN=<mb-selector> \
  --subnet-id <subnet> --async
# → the managed https:// URL is in status.public_endpoints; smoke-test it before declaring success.
```

Keep weights **out of the image** — mount the bucket `ro` and load from the mount.

## 4. Batch inference fan-out (no native array jobs)

Serverless AI has no array-job primitive, so a fan-out is N `create`s in a loop — which is exactly the batched mutation Tier B forbids the agent from issuing. So the agent does **not** run the loop: it produces the parameterized script and states the **aggregate** cost (N × preset rate × timeout), and the *human* runs it — the same split as the CI recipe below. The agent still runs single, individually-gated jobs itself.

```bash
# Hand this to the user; the agent does not execute the fan-out itself.
for i in $(seq 0 15); do
  nebius ai job create --parent-id <project> --name infer-$i-abc123 \
    --image cr.eu-north1.nebius.cloud/<reg>/infer:v1 \
    --platform gpu-l40s-a --preset 1gpu-8vcpu-32gb \
    --timeout 2h \
    --env SHARD_INDEX=$i --env SHARD_TOTAL=16 \
    --volume <input-bucket-id>:/in:ro --volume <output-bucket-id>:/out:rw \
    --subnet-id <subnet> --async &
done
wait   # wait for all submit calls to return
```

Then track the shards (a read, so the agent can do this) with `nebius ai job list --parent-id <project> --format json` filtered by the `infer-` name prefix. Alternative that stays a single gated `create`: one multi-GPU job consuming a manifest.

## 5. Fine-tuning with checkpoints (survives restarts)

Checkpoint to a **filesystem** mount (bucket FUSE mounts choke on the small random writes — see `nebius-serverless-data-secrets`), and let the job resume on failure:

```bash
nebius ai job create --parent-id <project> --name ft-abc123 \
  --image cr.eu-north1.nebius.cloud/<reg>/ft:v1 \
  --platform gpu-h100-sxm --preset 1gpu-16vcpu-200gb \
  --timeout 72h \
  --restart-policy on-failure --restart-attempts -1 \
  --volume <checkpoint-fs-id>:/ckpts:rw \
  --env CKPT_DIR=/ckpts --env RESUME_FROM_LATEST=true \
  --subnet-id <subnet> --async
```

Training code must resume from the newest checkpoint at startup for the restart to help.

## 6. Cost-optimized preemptible training

`--preemptible` gets the spot discount but the VM can be reclaimed at any time — only safe when the job checkpoints frequently (every ~5–15 min of compute) and resumes. Not for tight wall-clock deadlines. Same shape as recipe 5, plus `--preemptible`:

```bash
nebius ai job create --parent-id <project> --name ft-spot-abc123 \
  --image cr.eu-north1.nebius.cloud/<reg>/ft:v1 \
  --platform gpu-h100-sxm --preset 1gpu-16vcpu-200gb \
  --timeout 72h --preemptible \
  --restart-policy on-failure --restart-attempts -1 \
  --volume <checkpoint-fs-id>:/ckpts:rw \
  --env CKPT_DIR=/ckpts --env RESUME_FROM_LATEST=true \
  --subnet-id <subnet> --async
```

State both the discounted rate and that each preemption loses progress since the last checkpoint.

## 7. Run a job from GitHub Actions (CI)

Authenticate non-interactively with a **service-account key** (see `nebius-serverless-setup` — the agent never generates or echoes the key; a human provisions the SA and stores `credentials.json` in the CI secret store). This YAML runs in *your* pipeline, not something the agent executes for you.

```yaml
jobs:
  train:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configure non-interactive profile
        run: |
          printf '%s' "${{ secrets.NEBIUS_SA_CREDENTIALS }}" > "$RUNNER_TEMP/creds.json"
          chmod 600 "$RUNNER_TEMP/creds.json"
          nebius profile create ci \
            --service-account-file-path "$RUNNER_TEMP/creds.json" \
            --parent-id ${{ secrets.NEBIUS_PROJECT_ID }}

      - name: Build + push (amd64)
        run: |
          docker buildx build --platform linux/amd64 \
            -t cr.eu-north1.nebius.cloud/${{ secrets.NEBIUS_REGISTRY }}/app:${{ github.sha }} \
            --push .

      - name: Validate then submit
        run: |
          COMMON="--parent-id ${{ secrets.NEBIUS_PROJECT_ID }} \
            --image cr.eu-north1.nebius.cloud/${{ secrets.NEBIUS_REGISTRY }}/app:${{ github.sha }} \
            --platform gpu-l40s-a --preset 1gpu-8vcpu-32gb --timeout 1h \
            --subnet-id ${{ secrets.NEBIUS_SUBNET_ID }}"
          nebius ai job create --name ci-${GITHUB_SHA:0:7} $COMMON --dry-run   # fail the build on a bad spec
          nebius ai job create --name ci-${GITHUB_SHA:0:7} $COMMON --async
```

Keep the registry login to the pipeline (per the Nebius Container Registry docs); `iam get-access-token` stays a human/CI concern, never an agent step.

## Reference

- Overview: https://docs.nebius.com/serverless/overview
- Jobs: https://docs.nebius.com/serverless/jobs
- Endpoints: https://docs.nebius.com/serverless/endpoints
- CLI index: https://docs.nebius.com/cli/reference/ai/
- Compute pricing (incl. preemptible): https://docs.nebius.com/compute/resources/pricing
