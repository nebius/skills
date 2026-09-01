# Platforms and presets for Serverless jobs/endpoints

Verified against a live project on CLI 0.12.265 (2026-08). Platform/preset catalogs are **per-region** — always confirm in the target project before quoting availability:

```bash
nebius compute platform list --parent-id <project-id> --format json --all \
  | jq -r '.items[] | .metadata.name + ": " + (.spec.presets | map(.name) | join(", "))'
```

## GPU platforms

| Platform | GPU | Presets (gpu-vcpu-ram) |
|---|---|---|
| `gpu-h100-sxm` | H100 SXM | `1gpu-16vcpu-200gb`, `8gpu-128vcpu-1600gb` |
| `gpu-h200-sxm` | H200 SXM | `1gpu-16vcpu-200gb`, `8gpu-128vcpu-1600gb` |
| `gpu-l40s-a` | L40S | `1gpu-8vcpu-32gb`, `1gpu-16vcpu-64gb`, `1gpu-24vcpu-96gb`, `1gpu-32vcpu-128gb`, `1gpu-40vcpu-160gb` |
| `gpu-l40s-d` | L40S | `1gpu-16vcpu-96gb`, `1gpu-32vcpu-192gb`, `1gpu-48vcpu-288gb`, `2gpu-64vcpu-384gb`, `2gpu-96vcpu-576gb`, `4gpu-128vcpu-768gb`, `4gpu-192vcpu-1152gb` |
| `gpu-gb300` | GB300 | `4gpu-112vcpu-800gb` |

RTX 6000-class platforms exist in some regions only (e.g. KCS) and did not appear in the region verified above — discover with the command at the top, never assert their names from memory. When a platform is exhausted (`RESOURCE_EXHAUSTED`), an RTX 6000 or L40S region is often the working fallback.

## CPU platforms (validation runs, preprocessing)

| Platform | Presets (vcpu-ram) |
|---|---|
| `cpu-d3` | `4vcpu-16gb` … `128vcpu-512gb` (4/8/16/32/48/64/96/128 vCPU steps) |
| `cpu-e2` | `2vcpu-8gb` … `80vcpu-320gb` |

## Rules of thumb

- H100/H200 presets are 1-GPU or 8-GPU only — there is no 2- or 4-GPU H100 preset; mid-sizes exist on L40S.
- Preset RAM is the container's memory budget; `--shm-size` (default 16Gi on GPU platforms, 0 on CPU) carves `/dev/shm` out of it — PyTorch dataloaders commonly need it raised.
- Defaults if flags are omitted: platform `gpu-h100-sxm` in eu-north1 / `gpu-h200-sxm` elsewhere, minimum preset of the platform. Fine for endpoints prototyping; for jobs, state the choice explicitly so the cost is visible.
- Prices are per preset per hour — current list at https://nebius.com/prices; state the number before every create.
