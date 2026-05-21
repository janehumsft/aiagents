## 6. Tradeoffs & Takebacks

| Tradeoff | Details |
|----------|---------|
| Slower P95 on terminal failures (by ~200ms) | First attempt now includes the retry-policy overhead even for terminal failures. Acceptable: P95 increase is well under the 3s budget. Mitigation: the policy short-circuits on terminal kinds; only the classification + dispatch cost remains. |
| Increased load on auth backend on flaky days | Retries amplify failed-call volume by up to 3x. Mitigation: backend already auto-scales on 429s; the `auth.retryPolicy.maxAttempts` flag lets ops cap retries during incidents. |
| Telemetry volume increase | New events emit on every retry attempt. Expected volume increase: ~5% over baseline. Mitigation: `auth.retryPolicy.telemetry` toggle can silence emission without disabling retries. |
| Behavior change opacity | Users no longer see transient failures, which can mask backend health issues to the support team. Mitigation: surface retry exhaustion in the user-facing error message ("we tried 3 times"). |
