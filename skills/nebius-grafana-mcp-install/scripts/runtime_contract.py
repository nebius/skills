"""The single immutable runtime inventory and upstream argument contract."""

FILES = (
    "run-nebius-grafana-mcp.sh", "common.py", "token_state.py", "runtime_check.py",
    "origin.py", "runtime_contract.py", "credential_proxy.py", "mcp_bridge.py",
)

MCP_ARGS = (
    "--transport", "stdio", "--disable-write", "--disable-proxied",
    "--enabled-tools", "search,datasource,dashboard,prometheus,loki,api",
    "--max-loki-log-limit", "20",
)
