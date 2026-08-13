# PIT History Accumulation v0.1

Routine cadence is one real governed cycle per calendar day. The external scheduler controls clock
time. `PIT_HISTORY_START` is the first production-intended successful cycle after GATE-012 live
acceptance and is recorded in the operational baseline.

Retain CollectionRuns, observations, lifecycle events, review applications, DedupRuns, Premium runs,
Dashboard snapshots, Day0ReadinessAssessments, ObservatoryCycles, Source attempts, events, and RAW
provenance. No destructive retention or synthetic backfill exists in this gate.

Successful and missed cycles are derived from persisted cycle evidence. A missed scheduler date is
recorded as a truthful gap when inspected; it does not create an observation. Thirty real daily
cycles is a future program milestone and does not hold the implementation PR open.
