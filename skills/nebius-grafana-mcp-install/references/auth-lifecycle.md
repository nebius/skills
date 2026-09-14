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

## Observation-based scheduling

Nebius documents short-lived IAM access tokens, but the selected CLI command
does not supply authoritative expiry metadata to this runtime. `observed_at`
records when this helper first observed a token generation. It is not `issued_at`
and does not prove how long the credential remains valid.

- Startup reuses a generation observed within one hour.
- Renewal is scheduled ten hours after observation; bounded retries use delays
  of 60, 300 and 900 seconds.
- Each connection stops by its eleven-hour operational cap. Wall-clock and
  monotonic limits prevent clock rollback or a peer's token replacement from
  extending that connection's cap.
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

Before updating a pre-fix runtime, stop every old or new runtime sharing the
selected state directory. A pre-fix owner-pid.tmp can remain inside iam-token.lock;
the updated code neither creates nor automatically deletes it. Only after all
writers are confirmed stopped may the human inspect ownership, file types and
the exact selected state path, remove that residue, and remove the now-empty
lock directory. Preserve unexpected contents and refuse symlinked paths; do not
use recursive deletion or infer quiescence from age alone. Then rerun owned
setup and reconnect. This is operator recovery, not an agent-run cleanup action.

The directory-lock protocol remains in place. These targeted repairs do not
establish that its age-based incomplete-lock recovery is safe against an
initializer paused beyond the age threshold; broader lock hardening is separate.

Directory permissions reduce accidental exposure; another process running as
the same OS user can still read private files. Runtime output protection is not
an operating-system isolation boundary.

Official references: [Nebius access tokens](https://docs.nebius.com/iam/authorization/access-tokens)
and [CLI token command](https://docs.nebius.com/cli/reference/iam/get-access-token).
