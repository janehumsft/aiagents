## 1. Summary and Goals

Sign-in failures from transient network errors currently surface as
hard failures to the user, who must manually retry. We want to add a
client-side retry policy that distinguishes transient failures (network
timeouts, 5xx, throttling) from terminal failures (bad credentials,
account lockout), retries the transient cases with bounded exponential
backoff, and emits clear telemetry so we can measure the recovery rate.

The current state is "first failure surfaces immediately." The desired
end state is "transient failures recover automatically within ~3
seconds for >90% of cases." This targets the desktop and web sign-in
surfaces only; mobile uses a different auth stack and is out of scope
for this design.

### Phases

1. **Classify failures** -- introduce a `LoginFailureKind` enum and
   tag every existing failure path. Pure refactor, no behavior change.
2. **Retry policy core** -- add a `RetryPolicy` that wraps the sign-in
   call, gated behind the `auth.retryPolicy.enabled` flag.
3. **Telemetry & dashboards** -- emit `login.retry.attempted` /
   `login.retry.succeeded` / `login.retry.exhausted` and build a
   recovery-rate dashboard.
4. **[Optional] Migrate mobile** -- only if the mobile auth stack
   converges with desktop in the next half.

> Note: Phases 1 and 2 must ship together — the retry policy depends
> on the classification work. Phase 3 can ship in parallel with Phase
> 2 behind the same flag.
