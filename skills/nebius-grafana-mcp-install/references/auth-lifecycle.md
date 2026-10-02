# Human authentication and renewal

## Credential ownership

Setup pins one explicit human Nebius CLI profile and its resolved user identity.
Every token operation revalidates that identity. Ambient token/profile selectors
are stripped in the child CLI environment; service-account substitution, static
keys and impersonation are unsupported. The agent invokes only bundled setup; that helper and the fixed supervisor own credential operations.

The bundled helper captures CLI stdout directly into a private temporary file,
validates it and atomically replaces the token file. Errors use fixed messages;
raw CLI output is withheld. The proxy reads one frozen generation. Stock MCP
receives only an ephemeral credential for the local proxy.

## Asynchronous preparation

The local MCP frontend serves the checksum-bound public discovery catalog
immediately. A separate worker reuses a valid fresh token or refreshes it
noninteractively, then freezes one generation. Only then does the real stock
MCP start and obtain real Grafana frontend metadata. The bridge privately
initializes it and verifies all advertised tools and resources against the
pinned catalog before forwarding operations.

Preparation includes backend discovery and is limited to 240 seconds. While
pending, tool calls and resource reads return a fixed retryable `preparing`
error and perform no Grafana read. Calls are not queued or replayed. The caller
may retry; bundled setup retries within its existing verification budget.
Failed preparation, a mismatched catalog or backend failure closes the owned
connection. Background authentication never opens a browser.

## Observation-based scheduling

Nebius documents short-lived IAM access tokens, but the selected CLI command
does not supply authoritative expiry metadata to this runtime. `observed_at`
records when this helper first observed a token generation. It is not `issued_at`
and does not prove how long the credential remains valid.

- Startup credential inspection, freezing and backend loading require a
  generation observed within one hour. Once loaded, crossing that boundary
  does not invalidate the connection while its watchdog attaches.
- Renewal is scheduled ten hours after observation; bounded retries use delays
  of 60, 300 and 900 seconds.
- Each connection stops by its eleven-hour operational cap. Wall-clock and
  monotonic limits prevent clock rollback or a peer's token replacement from
  extending that connection's cap.
- Watchdog attachment validates the frozen generation against that original
  eleven-hour deadline. It neither refreshes the token nor changes its
  observation time; future-dated or already capped generations are refused.
- Identical token bytes retain the earlier observation time, including when
  only the CLI's line ending changes. Repeated cached bytes are not rotation.
- Successful rotation ends the old stdio connection with exit 75. A new client
  connection loads the new token. Automatic same-chat reconnection is not promised.

These limits do not guarantee pre-expiry renewal, uninterrupted access beyond
twelve hours or indefinite renewal of a human login. A cached token may expire
earlier. Ordinary Grafana/backend authorization failures remain visible as
sanitized statuses; they never cause credential or privilege substitution.

## Failure and recovery

Startup and background renewal use noninteractive bounded authentication. If
human authentication is required, invoke the skill for authentication recovery.
The agent runs bundled setup with `--apply --update`; complete browser sign-in
if it opens, then reconnect when required. Identical returned bytes still retain their original observation.
Do not paste tokens into
chat, edit identity bindings, weaken file permissions or change the bound URL.

Concurrent connections share one serialized renewal operation per state
location. Each connection retains its own frozen generation and deadline.
The writer captures its PID and process-start identity before lock acquisition,
without creating a PID temporary file. Concurrent reuse requires a complete
token/metadata pair with matching digest and a fresh observation. An incomplete
pair is left unchanged and returns a normal refresh failure: background renewal
uses the existing bounded retries, while foreground setup reports a sanitized failure with
recovery guidance. Recovery never invents metadata or relabels a token as newer.

A failed or stopped deadline/renewal worker stops the MCP connection. Shutdown
removes only owned temporary files and terminates the proxy and MCP processes.

The directory-lock protocol remains in place. These targeted repairs do not
establish that its age-based incomplete-lock recovery is safe against an
initializer paused beyond the age threshold; broader lock hardening is separate.

Directory permissions reduce accidental exposure; another process running as
the same OS user can still read private files. Runtime output protection is not
an operating-system isolation boundary.

Official references: [Nebius access tokens](https://docs.nebius.com/iam/authorization/access-tokens)
and [CLI token command](https://docs.nebius.com/cli/reference/iam/get-access-token).
