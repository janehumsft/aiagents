## 10. Appendix

### POC results

A 2-day proof-of-concept on a 5,000-user internal ring confirmed:
- Recovery rate of 91.4% (target: >90%)
- P95 latency on success unchanged (no regression)
- P95 latency on terminal failure +180ms (within tolerance)
- Zero observed amplification of backend load (Retry-After honored
  correctly)

### Known limitations

- Retry budget is global (3 seconds total). A burst of transient
  failures across multiple components can starve later operations of
  retry budget. Acceptable for v1; future work could scope the budget
  per operation.
- Telemetry is best-effort; events are dropped if the local cache
  overflows during sustained failures. Mitigated by sampling.

### Links

- [Login Health dashboard](https://example.com/dashboards/login-health)
- [Auth SDK repo](https://example.com/repos/auth-sdk)
- [POC results doc](https://example.com/docs/login-retry-poc)
- [ADO feature #12345](https://dev.azure.com/example/_workitems/edit/12345)
