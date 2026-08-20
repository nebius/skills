# Compute resources: verb matrix and notes

Verbs verified against nebius CLI 0.12.x. Trust `nebius compute <resource> --help` over this table when they disagree.

| Resource | Read verbs | Notes |
|---|---|---|
| `instance` | `list`, `get`, `get-by-name`, `batch-get`, `logs`, `list-operations-by-parent`, `list-instances-by-nvl-instance-group` | `status.state` carries run state. `batch-get` takes multiple IDs; per-ID errors come back in place of the instance. `logs` reads console output. |
| `disk` | `list`, `get`, `get-by-name`, `list-operations-by-parent` | Types: `network_ssd`, `network_hdd`, `network_ssd_non_replicated`, `network_ssd_io_m3` (create flags take lowercase; output shows them uppercase, e.g. `NETWORK_SSD`). Size in `spec` (bytes/gibibytes variants, serialized as strings). |
| `filesystem` | `list`, `get`, `get-by-name`, `list-operations-by-parent` | Types: `network_ssd`, `network_hdd`, `weka`. Shared between instances; attachment shown on the instance spec. |
| `gpu-cluster` | `list`, `get`, `get-by-name`, `list-operations-by-parent` | Groups instances on one InfiniBand fabric (`spec.infiniband_fabric`). Membership is on the instance (`spec.gpu_cluster`). |
| `image` | `list`, `list-public`, `get`, `get-by-name`, `get-latest-by-family`, `list-operations-by-parent` | Project images via `list`; OS marketplace images via `list-public`. `get-latest-by-family` resolves a family (e.g. ubuntu) to its newest image. |
| `platform` | `list`, `get` | Hardware platforms + their presets (vCPU/RAM/GPU combos). The authoritative source for valid `--resources-platform`/`--resources-preset` values in this region. |
| `node` | `list`, `get` | Physical-node view where exposed. Mutating verb `set-unhealthy` exists on some versions — that is Tier B at minimum; not an inventory concern. |
| `nvl-instance-group` | `list`, `get` | NVLink instance groups (GB200/NVL-class). Use `instance list-instances-by-nvl-instance-group` to see members. |

## Field paths worth knowing

Confirmed stable across resources:

- `.metadata.id` — the NID (`computeinstance-...`, `computedisk-...`, ...)
- `.metadata.name`, `.metadata.parent_id`, `.metadata.labels` (map)
- `.metadata.resource_version` — needed for optimistic-concurrency updates
- `.spec.*` — desired configuration (platform/preset for instances; type/size for disks/filesystems)
- `.status.*` — observed state; `.status.state` on instances

Exact spec layouts differ per resource and CLI version — one `get --format yaml` on a live resource is the reliable way to learn them.

## Cross-resource lookups

```bash
# Which disks does an instance use? (boot + secondary, from the instance spec)
nebius compute instance get <id> --format json | jq '.spec | {boot_disk, secondary_disks}'

# Which instances sit in a GPU cluster?
nebius compute instance list --parent-id "$PROJECT" --format json --all \
  | jq --arg gc "computegpucluster-..." '.items[] | select(.spec.gpu_cluster.id? == $gc) | .metadata.name'

# Operations (audit trail) in a project, most recent activity
nebius compute instance list-operations-by-parent --parent-id "$PROJECT" --format json
```
