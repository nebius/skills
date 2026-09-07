# Granting a service account its roles (human step)

Nebius has **no `iam role-binding`** command. Roles are granted through **group membership**, and the built-in groups live at the **tenant** level. The agent does not run any of this — granting roles changes who can do what across the tenant. This file is the exact sequence for the **human** performing the grant, so the agent can hand it over accurately instead of improvising.

Placeholders: `$TENANT` = `tenant-…`, `$PROJECT` = `project-…`, `$SA_ID` = the service account's ID.

## Coarse: put the SA in a built-in group

`editors` = read/write on resources; `admins` = also manages IAM. Both are **tenant-wide** — prefer a narrower project-scoped group if the project defines one.

```bash
GROUP=$(nebius iam group get-by-name --name editors --parent-id $TENANT \
  --format jsonpath='{.metadata.id}')
nebius iam group-membership create --parent-id $GROUP --member-id $SA_ID
```

Add `--revoke-after-hours N` to `group-membership create` to make the grant temporary (good for a one-off CI job).

## Fine: object-storage access for the SA

Object-storage roles are granted with `access-permit`, whose parent must be a **group** (not the SA directly, and not a nonexistent role-binding):

```bash
GROUP=$(nebius iam group create --parent-id $TENANT --name serverless-storage \
  --format jsonpath='{.metadata.id}')
nebius iam group-membership create --parent-id $GROUP --member-id $SA_ID
nebius iam access-permit create --parent-id $GROUP --resource-id $PROJECT --role storage.editor
```

Roles for read/write objects: `storage.editor` or `storage.object-editor`.

## Least privilege

- Prefer a dedicated group per purpose over dropping the SA into tenant-wide `editors`/`admins`.
- If the project has its own groups, grant there so a key compromise stays inside the project.
- Time-box CI grants with `--revoke-after-hours`.

## What this is not

- Not the agent's job — every command here is a role change; print it for the human.
- Not credential issuance — that (`iam auth-public-key generate`) is in the setup skill and is gated, not refused.
