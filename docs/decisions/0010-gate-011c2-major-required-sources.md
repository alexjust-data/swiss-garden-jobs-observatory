# ADR-0010 — GATE-011C-2 major required federal and canton sources

- Status: accepted for GATE-011C-2 implementation
- Date: 2026-08-11
- Baseline: `f8f4e1562f5b250b2bc5c5ddd6bc052c951ad559`

## Decision

GATE-011C-2 authorizes exactly these frozen Source identities:

```text
SRC-OFF-JOBS-ADMIN
SRC-OFF-CANTON-AG
SRC-OFF-CANTON-BE
SRC-OFF-CANTON-BS
SRC-OFF-CANTON-LU
SRC-OFF-CANTON-SG
```

Live reconnaissance precedes implementation. Frozen platform-family labels identify the
governed Source rows; they do not prove the current wire protocol. `FULL_SOURCE` means all
observable vacancy surfaces belonging to one canonical Source identity. A Source with an
unresolved mandatory surface is not partially promoted.

The gate accepts two implementations and four governed blockers:

| Source | Terminal state | Decision |
| --- | --- | --- |
| Federal Administration | `ACCEPTED_IMPLEMENTED` | One unfiltered Prospective API exhausts jobs, internships, traineeships and apprenticeships. |
| Aargau | `ACCEPTED_BLOCKED` | The official component's only complete feed is under `/io/jobs-proxy/*`, while `www.ag.ch/robots.txt` disallows `/io/*`. |
| Bern canton | `ACCEPTED_BLOCKED` | The canonical hub has separate ordinary, apprenticeship, teacher and substitute-teacher surfaces; mandatory teaching origins do not expose an accepted access contract and the substitute origin returns 403. |
| Basel-Stadt | `ACCEPTED_IMPLEMENTED` | The current official employer hub governs ordinary jobs and a distinct apprenticeship surface on `stellenmarkt.bs.ch`; both are exhausted under one Source identity. |
| Luzern canton | `ACCEPTED_BLOCKED` | Administration and teaching are Refline vacancy surfaces, but the mandatory `lehre.lu` surface exposes training profiles and aggregate availability without a proven vacancy-native ID-to-detail contract. |
| St. Gallen canton | `ACCEPTED_BLOCKED` | The official employer universe separates Umantis administration jobs, teacher jobs and training; only the Umantis sub-universe has a proven static contract. |

Blocked Sources remain `DAY0_REQUIRED`, remain in the denominator of 29, receive no adapter,
no `SourceEndpoint`, and no collection run. No unofficial mirror or reduced sub-universe is a
substitute for a complete Source.

## Architecture

Accepted adapters translate into existing `ListingEntry`, `ListingPage` and
`ParsedSourcePosting` values. The shared pipeline remains the sole owner of governed HTTP,
RAW/SHA-256 evidence, observations, green classification, lifecycle and source health.
Adapter selection remains exact-Source safe.

Basel-Stadt proves the existing multi-surface model with two governed seeds. Its listing is
cumulative: each successive response repeats prior rows and adds rows. Completeness is proven
by monotonic page progression and equality between the per-surface reported total and the
unique `(publication_id, canonical_detail)` set. A repeated terminal link is ignored only after
that equality is reached. A conflicting identity fails closed.

## Preserved contracts

- Blocked Sources stay required.
- Access decisions are Source- and origin-specific.
- Incomplete multi-surface discovery creates no negative lifecycle evidence.
- Dedup, premium, dashboard and readiness remain downstream PIT processes.
- `green-relevance-v0.1` / `research-v0.4` remains unchanged.
- Day-0 threshold and freshness policies remain `PENDING`.
- No Day-0 market figure is authorized.
- `docs/research/v0_4/` remains frozen.
- GATE-008, GATE-009, GATE-010, GATE-011A, GATE-011B and GATE-011C-1 semantics remain closed.

