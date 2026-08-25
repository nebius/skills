# Output formats and pagination

## Formats

`--format` accepts `yaml|json|jsonpath|table|text` on every command.

- **`json`** — the default choice for agents. Parse with jq or a script.
- **`yaml`** — useful to eyeball a resource's full shape before writing an update spec (`get ... --format yaml`).
- **`jsonpath`** — server-side field extraction; pass the expression with `--jsonpath` when supported, but prefer `--format json` piped to jq: jq is easier to debug and its failure modes are visible.
- **`table` / `text`** — human-facing; never parse these.

## jq recipes

```bash
# id, name, state of every instance
nebius compute instance list --parent-id "$PROJECT" --format json --all \
  | jq -r '.items[] | [.metadata.id, .metadata.name, .status.state] | @tsv'

# find a resource by label
nebius compute disk list --parent-id "$PROJECT" --format json --all \
  | jq '.items[] | select(.metadata.labels.env == "prod")'

# count by state
nebius compute instance list --parent-id "$PROJECT" --format json --all \
  | jq '[.items[].status.state] | group_by(.) | map({state: .[0], n: length})'
```

List responses put resources under `.items[]`; each resource has `metadata` (id, name, parent_id, labels, resource_version), `spec` (desired configuration), and `status` (observed state). Confirm exact field names on the first call — run one `get --format yaml` and read it rather than assuming.

## Pagination

List calls take `--page-size` (often capped at 1000) and `--page-token`, and return a `next_page_token` when more pages exist.

- For bounded work, pass `--all` — the CLI follows pages itself and returns everything.
- Only page manually (`--page-size` + `--page-token` loop) when a list is huge and you need to stop early.
- **Never** pass `-i`/`--interactive`: it renders pages on an alternate screen and waits for keypresses — an unattended session hangs forever.

The same applies to any streaming/following mode — `compute instance logs --follow`, and `logging query --follow` in other service families: always use bounded queries.
