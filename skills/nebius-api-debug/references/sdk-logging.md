# SDK logging

Use the APIs supported by the installed SDK version. Keep the application's existing credentials and endpoint configuration.
Enable the logger before constructing the SDK or sending the failing request.
Use a fresh private output directory for each attempt so log files from different runs cannot mix.
The snippets configure logging; add them to the existing reproduction instead of replacing its request or authentication setup.

## Go

Pass a debug-level `log/slog` logger to `gosdk.WithLogger` or `gosdk.WithLoggerHandler`:

```go
logFile, err := os.OpenFile("nebius-sdk.debug.log", os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0600)
if err != nil {
    return err
}
defer logFile.Close()
logger := slog.New(slog.NewJSONHandler(logFile, &slog.HandlerOptions{Level: slog.LevelDebug}))
// Add gosdk.WithLogger(logger) to the existing gosdk.New(ctx, ...) options.
```

The public Go package is `github.com/nebius/gosdk`.
For a gRPC call, capture response headers and trailers with `grpc.Header(&headers)` and `grpc.Trailer(&trailers)`.
Read `x-trace-id` and `x-request-id` even when the call returns an error. Preserve any IDs in the structured SDK error.
If the SDK version exposes a different transport, use its response-metadata API instead.

## Python

Configure the `nebius` logger instead of enabling debug on the entire application:

```python
import logging

sdk_log = logging.getLogger("nebius")
previous_level, previous_propagate = sdk_log.level, sdk_log.propagate
sdk_log.setLevel(logging.DEBUG)
handler = logging.FileHandler("nebius-sdk.debug.log", mode="w", encoding="utf-8")
handler.setLevel(logging.DEBUG)
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
sdk_log.addHandler(handler)
sdk_log.propagate = False
```

Retain the `Request` returned by the service method before awaiting it or calling `wait()`.
Read `await request.trace_id()` and `await request.request_id()` in asynchronous code.
Use `request.trace_id_sync()` and `request.request_id_sync()` in synchronous code.
On a failed call, inspect the request metadata and structured exception; do not lose the original error while collecting IDs.
After the diagnostic run, remove and close the handler and restore the logger settings, including on failure:

```python
sdk_log.removeHandler(handler)
handler.close()
sdk_log.setLevel(previous_level)
sdk_log.propagate = previous_propagate
```

## JavaScript and TypeScript

For `@nebius/js-sdk`, configure an SDK handler with a dedicated output file:

```ts
import { defaultHandler, Level } from '@nebius/js-sdk/runtime/util/logging';

const logger = defaultHandler({
  level: Level.DEBUG,
  output: 'nebius-sdk.debug.log',
  useJson: true,
});
// Add logger to the existing new SDK({ ..., logger }) options.
```

Keep the request object before awaiting `request.result`.
Read its `traceId` and `requestId` promises and IDs in the structured error, including after a failed result.
Keep metadata-collection failures from replacing the original request error.
Use a private output directory, and close the SDK after pending calls and metadata collection finish.

## Other SDKs and transports

Find the SDK's supported debug logger and response-metadata hooks in its source or official documentation.
Do not assume Go, Python, and JavaScript configuration APIs apply to another language or SDK version.
If the SDK supplies no logger, capture request metadata through its supported transport hooks.
Record that limitation in the ticket, and include the application error and available transport diagnostics.
Do not replace redacted SDK logs with an unfiltered HTTP or gRPC payload dump.
