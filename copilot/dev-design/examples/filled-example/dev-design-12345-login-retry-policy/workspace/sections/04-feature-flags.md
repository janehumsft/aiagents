## 4. Feature Flags

| Flag | Purpose | Phase | Rollout Notes |
|------|---------|-------|---------------|
| `auth.retryPolicy.enabled` | Master switch for the retry wrapper | Phase 2 | Default off; rollout to internal ring first, then 1% / 10% / 100% over 2 weeks |
| `auth.retryPolicy.maxAttempts` | Override retry attempts (default 3) | Phase 2 | Numeric override; lets ops disable retries without flipping the master flag |
| `auth.retryPolicy.telemetry` | Independent toggle for emitting retry events | Phase 3 | Default on once Phase 3 ships; lets us silence telemetry if backend ingestion is unhealthy |
