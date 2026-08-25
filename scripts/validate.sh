#!/usr/bin/env bash
# Full structural validation. Run from anywhere; CI runs exactly this.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== shared preamble sync =="
python3 scripts/sync-shared.py --check

echo "== frontmatter / portability lint =="
python3 scripts/check-frontmatter.py

echo "== skills-ref validate (Agent Skills spec) =="
for d in skills/*/; do
  npx --yes skills-ref validate "$d"
done

echo "== manifest lint + version sync (claude + codex) =="
python3 - <<'EOF'
import json, sys
versions = {
    ".claude-plugin/plugin.json": json.load(open(".claude-plugin/plugin.json"))["version"],
    ".claude-plugin/marketplace.json": json.load(open(".claude-plugin/marketplace.json"))["metadata"]["version"],
    ".codex-plugin/plugin.json": json.load(open(".codex-plugin/plugin.json"))["version"],
}
json.load(open(".agents/plugins/marketplace.json"))  # no version field; lint only
if len(set(versions.values())) != 1:
    sys.exit("version mismatch: " + ", ".join(f"{p}={v}" for p, v in versions.items()))
print(f"ok: {next(iter(versions.values()))}")
EOF

echo "== claude plugin validate =="
if command -v claude >/dev/null 2>&1; then
  claude plugin validate . --strict
else
  echo "claude CLI not found — skipped (runs in CI)"
fi

echo "ALL OK"
