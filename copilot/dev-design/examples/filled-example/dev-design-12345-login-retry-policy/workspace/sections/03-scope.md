## 3. Scope

### In Scope

**Surfaces covered:**
- Desktop sign-in dialog (Win32, macOS)
- Web sign-in modal (embedded in the desktop shell)
- Programmatic refresh-token renewal initiated by the SDK

**Behavior changes:**
- Automatic retry for transient failure kinds (network timeout, 5xx,
  HTTP 429 with `Retry-After`)
- Bounded exponential backoff (max 3 attempts, total budget 3 seconds)
- New telemetry events for retry attempts, successes, and exhaustion
- Backward compatibility: existing manual-retry UI remains unchanged

### Out of Scope

- Mobile sign-in (iOS / Android) — uses a separate auth stack, tracked
  in a follow-up design
- Server-side retry for service-to-service auth — already handled by
  the platform's grpc retry middleware
- Account lockout / suspicious-activity flows — terminal failures,
  must NOT be retried
- Captcha / proof-of-presence challenges — also terminal

### Current vs. Proposed Comparison

| Aspect | Current (manual retry) | Proposed (auto-retry) |
|--------|------------------------|------------------------|
| **APIs** | Single `signIn()` call; throws on first failure | `signIn()` wrapped in `RetryPolicy.execute()` |
| **Latency** | P50 1.1s on success; P95 18s with manual retry | P50 unchanged; P95 ~4s end-to-end including retries |
| **Throttling/Limits** | No retry; user retries cause repeated 429s | Honors `Retry-After`; client-side budget of 3 attempts |
| **Auth** | No change | No change — retries reuse the same credential blob |
| **Availability** | Recovery rate ~62% (user manually retries) | Target >90% transparent recovery |
