"""Explicit operator-owned HTTPS origin binding; no embedded service endpoint."""

import ipaddress
from pathlib import Path
import re
from urllib.parse import urlsplit

from common import SetupError, atomic_write, check_path, json_bytes, json_read


def canonical_origin(value):
    try:
        if not isinstance(value, str) or not value.isascii() or re.search(r"[\s\\%]", value):
            raise ValueError
        parsed = urlsplit(value)
        host = parsed.hostname
        if (parsed.scheme != "https" or not host or parsed.username is not None
                or parsed.password is not None or parsed.path not in ("", "/")
                or parsed.query or parsed.fragment or "?" in value or "#" in value
                or not re.fullmatch(r"[A-Za-z0-9.-]+", host) or host.endswith(".")):
            raise ValueError
        # The upstream target is a named, TLS-authenticated service. Loopback
        # addresses are reserved for the internal proxy, not cloud credentials.
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError
        if "." not in host or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part)
                                  for part in host.split(".")):
            raise ValueError
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError
        if parsed.netloc.endswith(":"):
            raise ValueError
        return "https://" + host + (f":{port}" if port not in (None, 443) else "") + "/"
    except (ValueError, TypeError, AttributeError) as exc:
        raise SetupError("Provide a trusted HTTPS Grafana origin without credentials, path, query or fragment.") from exc


def binding(state, home, value, *, create=False):
    value = canonical_origin(value)
    path = Path(state) / "origin.json"
    check_path(path, home, private=True, missing=True)
    expected = {"version": 1, "origin": value}
    if path.exists():
        if json_read(path, private=True) != expected:
            raise SetupError("Grafana origin binding changed; use a distinct installation name.")
    elif create:
        atomic_write(path, json_bytes(expected), home)
    else:
        raise SetupError("Grafana origin binding is missing; human-run setup is required.")
    return value
