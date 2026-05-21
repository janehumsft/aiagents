## 9. Test Scenarios

### Per-phase scenarios

**Phase 1 (Classify failures):**
- Each known backend error code maps to a non-`Other` `LoginFailureKind`.
- Unknown error codes map to `Other`.
- Legacy `catch (SignInException)` sites still observe the same exception
  type.

**Phase 2 (Retry policy):**
- 2 transient failures followed by success -> single visible result, 3
  events emitted (2 attempts + 1 succeeded).
- 3 transient failures -> single visible failure, retry-exhausted event
  emitted.
- 1 terminal failure (bad credentials) -> single visible failure, no
  retries attempted.
- `Retry-After: 5` header on the first failure -> second attempt occurs
  after >= 5s.
- Flag off -> behavior identical to legacy code.

**Phase 3 (Telemetry):**
- Synthetic 1000-call load with 20% injected transient failures yields
  `login.retry.succeeded` count within 10% of expected.
- Dashboard renders correctly with mock data fed via the AuthInsights
  sandbox.

### Cross-cutting

- **All flags off:** entire skill works identically to today.
- **Offline:** sign-in surface returns the same "no network" error path
  it does today (the retry policy short-circuits on
  `NetworkTimeout` + zero connectivity).
- **Backward compatibility:** existing automated UI tests pass without
  modification.
