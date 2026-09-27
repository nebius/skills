# Workspaces, access, and failed-job debugging

## Persistent workspace and extra data

- `--workspace-path` is an absolute container path, default `/workspace` for a custom image or the selected template's default. `--disk-size` is shared by the container and workspace; it is not an independent workspace allocation. The default is `250Gi`, or the source job's disk size with `--from-job`.
- Keep durable work in that path and export important artifacts before deletion. The CLI calls this a persistent workspace; it does not establish backup, deletion recovery, or persistence of every other directory.
- Extra `--volume SOURCE:CONTAINER_PATH[:MODE]` mounts must not overlap the workspace. Check identical paths and parent/child containment, not just string equality. Use read-only inputs where writes are unnecessary.
- S3 syntax: `--volume 's3://BUCKET:/data:ro:PROFILE@SECRET_SELECTOR'`. Devlab S3 mounts require a MysteryBox secret selector. `PROFILE` here is an AWS credentials profile, distinct from the Nebius CLI `-p` profile. Selectors accept a secret name, secret ID, version ID, or `SECRET_ID@VERSION_ID`.
- `--inject-file LOCAL_PATH:CONTAINER_PATH` accepts a local non-secret config file up to **64 KiB**, at an absolute destination, read-only in the container. It is not a dataset upload mechanism.
- `--env` is for non-secret configuration. Use `--env-secret KEY=SECRET_SELECTOR`; private registries use `--registry-secret` with `REGISTRY_USERNAME` and `REGISTRY_PASSWORD` payload keys. Do not invent plain registry-password flags for Devlabs.

## Managed web access

A template declares its primary route. Custom images need `--primary-route-port <port>` and a running web service reachable on that container port; exposing a port alone does not start Jupyter or an IDE. Set the container command/args when the image's defaults do not run the required service.

Retrieve the managed HTTPS URL from the returned status (`public_endpoints` in snake_case output, `publicEndpoints` in REST JSON); verify the actual output shape. Do not derive it from the VM IP or invent a hostname. Keep URLs containing credentials out of reports.

`--auth-token-secret` selects a MysteryBox secret with an `AUTH_TOKEN` payload key for bearer-token access. It is not the endpoint flag `--token-secret`. If no selector is supplied, establish the service's actual authentication flow instead of asserting that the UI is public or automatically protected. An unavailable secret is not a reason to disable authentication.

`--public` assigns the runtime VM a public IP, default false. It is distinct from a managed web route. Enable it only when the requested connection path requires that exposure; a notebook URL alone is not a reason to add it.

For an authorized UI smoke test, use a bounded request and avoid displaying credentials or notebook contents. Do not mint a token or read a secret payload just to automate the check. If the user must authenticate in the browser, provide the managed link and state that authenticated UI verification remains pending.

## SSH

Creation accepts repeatable `--ssh-key '<public-key-content>'`; read the user's selected `.pub` file, never a private key. Passing a path as the flag value is not documented as loading that file.

The CLI opens an interactive shell:

```bash
nebius ai devlab ssh <devlab-id> -p <profile> --identity-file <private-key-path>
# Private network path (requires connectivity to that private network):
nebius ai devlab ssh <devlab-id> -p <profile> --identity-file <private-key-path> --private
```

The default public SSH path requires a public IP (`--public` at create). Use `--private` only with an established network path. `--shell` selects the shell inside the container; do not assume it is a general remote-exec API. Hand the interactive command to the user unless the task explicitly needs an interactive terminal session. Do not run it in a non-interactive tool expecting it to terminate.

The SSH-local `-i` means identity file, unlike `--interactive` elsewhere; spell out `--identity-file` to avoid ambiguity with the shared preamble. Merely connecting does not authorize arbitrary changes in the workspace.

## Debug a failed job

`--from-job <job-id>` creates a **new billable Devlab using the failed job's configuration**. It is not a restart of that job or proof that files from its runtime disk are recovered.

1. Read the source job with `nebius ai job get --id <job-id> -p <profile> --format json`, summarize its failure and relevant configuration without exposing values, and ensure it is the intended failed job in the target context.
2. Inspect inherited resources, disk size, mounts, and secret selectors. Use the Devlab create help and dry-run to resolve the debugging UI. Do not assume `--from-job` removes the documented template or image/primary-route requirement; validate the intended combination.
3. If supplying a new `--image`, **registry credential inheritance is disabled**. Resolve an explicit `--registry-secret` for a private replacement image, even if the source job already used registry credentials.
4. Choose a fresh Devlab name and perform the same catalog check, duplicate lookup, dry-run, cost statement, and confirmation as an ordinary create. Do not silently inherit a costly GPU configuration.
5. Keep the failed job record and logs; neither deleting nor restarting the source job is required. Locate artifacts on explicitly persisted volumes instead of promising a snapshot of its container filesystem.

Source: [Devlab create CLI reference](https://docs.nebius.com/cli/reference/ai/devlab/create), [SSH CLI reference](https://docs.nebius.com/cli/reference/ai/devlab/ssh), and matching local CLI 0.12.277 help.
