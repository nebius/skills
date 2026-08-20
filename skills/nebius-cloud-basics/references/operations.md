# Async operations

Every mutation (create, update, start, stop, delete) is executed as an **operation** — a trackable unit of work.

## Blocking vs async

- **Default (no `--async`)**: the CLI waits for the operation to finish and prints the final resource. Simplest for single mutations; combine with `--timeout` if the caller needs a bound.
- **`--async`**: returns immediately with an operation id. Use when the user wants to fire-and-check-later, or when a create is slow (large disks, big instances).

## Waiting and inspecting

Each resource family has an `operation` subgroup:

```bash
nebius compute instance operation get <operation-id> --format json
nebius compute instance operation list --id <instance-id> --format json   # operations on one resource
nebius compute instance operation wait <operation-id> --format json       # block until done
nebius compute instance list-operations-by-parent --parent-id "$PROJECT" --format json  # recent activity in a project
```

The canonical async pattern:

```bash
op_id=$(nebius compute disk create ... --async --format json | jq -r '.metadata.id')
nebius compute disk operation wait "$op_id" --format json
```

`operation wait` is the right way to poll — do not write your own sleep loop.

## Failure handling

An operation that failed reports its error in the operation body (`operation get`). If a mutation's outcome is ambiguous (timeout, killed connection):

1. Do **not** re-run the mutation.
2. Check actual state: `list`/`get` the resource by name, and `list-operations-by-parent` to see whether the operation was accepted.
3. Report what you find and let the user decide.

## Timeouts and retries

Global flags: `--timeout` (whole command), `--per-retry-timeout`, `--retries` (default 3; `1` disables retrying). The CLI already retries transient gRPC failures on reads — do not add your own retry loop on top. Mutations should run with default retries and never be re-invoked manually after an unclear result.
