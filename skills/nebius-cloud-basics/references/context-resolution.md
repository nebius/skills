# Context resolution: profiles, parent-id, tenant-id

## Profiles

The CLI stores named profiles in `~/.nebius/config.yaml`:

```yaml
default: default-profile          # the active profile
profiles:
  default-profile:
    endpoint: <api endpoint>
    auth-type: federation         # or service account credentials
    federation-endpoint: <sso endpoint>
    parent-id: project-e00...     # default project for this profile
    tenant-id: tenant-e00...      # tenant this project belongs to
  testing:
    ...
```

Commands to inspect it (never parse the YAML directly when a command exists):

```bash
nebius profile list          # all profiles; "[default]" marks the active one
nebius profile current       # profile in effect for this invocation
nebius config get parent-id  # this profile's default project id
nebius config get tenant-id  # this profile's tenant id
nebius config list           # all config keys for the profile (plain text, not JSON)
```

All of these accept `-p <profile>` to target a non-active profile.

Not every profile carries `parent-id`/`tenant-id` — a freshly created or minimal profile may only have endpoints. If `config get` errors or returns nothing, ask the user for the target project/tenant instead of guessing or borrowing from another profile.

## NID formats

Nebius IDs ("NIDs") are typed by prefix — the prefix tells you what scope an ID is:

| Prefix | Resource |
|---|---|
| `tenant-...` | tenant (the top-level org container) |
| `project-...` | project (container for compute/storage/network resources) |
| `computeinstance-...` | VM instance |
| `computedisk-...` | disk |
| `computefilesystem-...` | shared filesystem |
| `computegpucluster-...` | GPU cluster |
| `computeimage-...` | image |
| `serviceaccount-...` | service account |
| `vpcsubnet-...` | subnet |

If a command wants a tenant and you pass a `project-...` id (or vice versa), you get empty results or a permission error — check the prefix before every call.

## Hierarchy

Tenant → projects → resources. A profile pins one project (`parent-id`) and its tenant (`tenant-id`). Region is encoded in the project (a project lives in one region), so there is no separate `--region` flag on most compute calls — but quota allowances are keyed by region explicitly.

## Auth

- **Federation (human)**: `nebius profile create` opens a browser SSO flow. This is interactive by design — never attempt it from an unattended session; hand it to the user.
- **Service accounts (automation)**: authorized keys in `~/.nebius/credentials.json`, or `--impersonate-service-account-id` (Tier C — refuse; impersonation escalates privileges silently).
- `nebius iam whoami --format json` confirms which identity is in effect. Use it in the grounding sequence and whenever permission errors appear.

Never print, copy, or persist anything from `~/.nebius/credentials.json`, and never run `nebius iam get-access-token` — an agent transcript is not a safe place for a bearer token.
