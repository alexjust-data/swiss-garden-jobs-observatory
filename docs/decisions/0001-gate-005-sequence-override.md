# Decision 0001: GATE-005 sequence override

## Status

Authorized on 2026-08-08.

## Decision

The newer approved delivery sequence overrides only the older gate numbering in the frozen implementation handoff where they conflict.

- GATE-005 is **Winterthur Temporal Replay, Posting Lifecycle & Source Health**.
- The geospatial pipeline is deferred to a later gate.
- The frozen `docs/research/v0_4/` package remains read-only.
- Technical contracts in the frozen package remain authoritative.

This changes sequencing only and does not weaken any frozen technical rule.
