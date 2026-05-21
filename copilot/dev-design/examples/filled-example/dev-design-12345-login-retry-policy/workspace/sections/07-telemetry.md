## 7. Telemetry & Monitoring

> **How to query**: AuthInsights cluster (`https://kusto.example/AuthInsights`),
> `AuthLogs` database. All retry events land in the `LoginEvents` table.

Existing dashboard: [Login Health](https://example.com/dashboards/login-health)

### 7.1 Retry Scenarios

| Scenario / Event Name | Exists? | Baseline | Description | Post-Rollout Expectation |
|------------------------|---------|----------|-------------|--------------------------|
| `login.attempted` | Yes | ~12k/min | Every sign-in attempt | No change |
| `login.failed` | Yes | ~1.3k/min | Every sign-in failure | -60% (transient failures now retried) |
| `login.retry.attempted` | No (new) | n/a | Per-retry instrumentation | ~900/min |
| `login.retry.succeeded` | No (new) | n/a | Retry recovered the call | ~720/min (target >90% of retries) |
| `login.retry.exhausted` | No (new) | n/a | Budget hit; user sees failure | ~180/min |

### 7.2 New Telemetry Needed

1. **`login.retry.attempted`** (P1) -- emitted on every retry with
   dimensions `attemptNumber`, `failureKind`, `elapsedMs`, `flightId`.
   Needed to compute recovery rate.
2. **`login.retry.succeeded`** (P1) -- emitted when a retry recovers.
   Carries the same dimensions plus `totalElapsedMs`.
3. **`login.retry.exhausted`** (P1) -- emitted on budget hit. Includes
   the last `failureKind` so we can spot persistent backend issues.

### 7.3 Monitoring Plan

| Metric | How to Monitor |
|--------|----------------|
| Recovery rate | `LoginEvents \| where name in ("login.retry.succeeded","login.retry.exhausted") \| summarize rate=countif(name=="login.retry.succeeded")/count() by bin(timestamp,10m)` |
| Retry volume | `LoginEvents \| where name == "login.retry.attempted" \| summarize count() by bin(timestamp,1m)` |
| Backend health proxy | Alert when `login.retry.exhausted` exceeds 5% of attempts for 10m |
