# SDK logging

Use installed SDK version APIs. Keep existing app credentials + endpoint config.
Use existing logs first. Enable logger before SDK construction for an explicitly requested new operation.
Fresh private output directory per attempt; no mixed logs.
Snippets configure logging only; keep request/auth setup. Never repeat failed call just to obtain logs.

## Go

Pass debug-level `log/slog` logger to `gosdk.WithLogger` or `gosdk.WithLoggerHandler`:

```go
logFile, err := os.OpenFile("nebius-sdk.debug.log", os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0600)
if err != nil {
    return err
}
defer logFile.Close()
logger := slog.New(slog.NewJSONHandler(logFile, &slog.HandlerOptions{Level: slog.LevelDebug}))
// Add gosdk.WithLogger(logger) to gosdk.New(ctx, ...) before the explicitly requested operation.
```

Public Go package: `github.com/nebius/gosdk`.
gRPC: capture response headers/trailers with `grpc.Header(&headers)` + `grpc.Trailer(&trailers)`.
Read `x-trace-id` + `x-request-id` even on failure. Keep IDs from structured SDK error.
Different transport in installed SDK → use its response-metadata API.

## Python

Configure `nebius` logger; avoid app-wide debug:

```python
import logging

sdk_log = logging.getLogger("nebius")
previous_level, previous_propagate = sdk_log.level, sdk_log.propagate
handler = logging.FileHandler("nebius-sdk.debug.log", mode="w", encoding="utf-8")
handler.setLevel(logging.DEBUG)
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
sdk_log.setLevel(logging.DEBUG)
sdk_log.addHandler(handler)
sdk_log.propagate = False
try:
    ...  # Perform only the explicitly requested new operation; collect its metadata.
finally:
    sdk_log.removeHandler(handler)
    handler.close()
    sdk_log.setLevel(previous_level)
    sdk_log.propagate = previous_propagate
```

Keep service method `Request` before await or `wait()`.
Async: `await request.trace_id()` + `await request.request_id()`.
Sync: `request.trace_id_sync()` + `request.request_id_sync()`.
Failed call: inspect request metadata + structured exception. ID collection must preserve original error.
`finally`: remove/close diagnostic handler; restore logger settings even on failure.

## JavaScript and TypeScript

`@nebius/js-sdk`: SDK handler + dedicated output file:

```ts
import { defaultHandler, Level } from '@nebius/js-sdk/runtime/util/logging';

const logger = defaultHandler({
  level: Level.DEBUG,
  output: 'nebius-sdk.debug.log',
  useJson: true,
});
// Pass logger to new SDK({ ..., logger }) for the explicitly requested operation.
```

Keep request object before awaiting `request.result`.
Read `traceId` + `requestId` promises and structured-error IDs, including after failed result.
Metadata-collection failure must preserve original request error.
Use private output directory. Close SDK after pending calls + metadata collection finish.

## Other SDKs and transports

Find supported SDK debug logger + response-metadata hooks in source/official docs.
Never assume Go/Python/JavaScript config APIs apply to other languages/SDK versions.
No SDK logger → capture request metadata through supported transport hooks.
Artifact notes: limitation, app error + available transport diagnostics.
Never replace redacted SDK logs with unfiltered HTTP/gRPC payload dump.
