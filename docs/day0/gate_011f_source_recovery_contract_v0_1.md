# GATE-011F required-source recovery contract v0.1

Status: frozen before GATE-011F current-state reconnaissance. Baseline:
`cbf1054b329843ea3fff7eeac77ea9342df60147` (merged GATE-011E).

## Purpose and invariants

This contract independently re-evaluates all nine C-6 `ACCEPTED_BLOCKED`
required Sources. It does not target the four-Source Day-0 gap and it does not
change `day0-coverage-v0.1`, `full-source-freshness-v0.1`, the fixed 29-Source
denominator, source identity, vacancy identity, access governance, classifiers,
deduplication or geography.

A recovery decision is new append-only evidence. It never rewrites C-6, the
historical `day0-authorization-v0.1` configuration, a historical source universe
or an existing readiness assessment. Each candidate ends as exactly one of:

- `RECOVERED_IMPLEMENTED`;
- `STILL_BLOCKED_SAME_REASON`;
- `STILL_BLOCKED_NEW_EVIDENCE`;
- `BLOCKER_CLASS_CHANGED`; or
- `SOURCE_CONTRACT_DRIFT`.

Insufficient proof is `STILL_BLOCKED_NEW_EVIDENCE`, not implementation.

## Common transition requirements

`RECOVERED_IMPLEMENTED` requires all of the following:

1. the canonical employer Source and every mandatory vacancy surface are known;
2. official ownership and the applicable access contract are evidenced;
3. source-native publication identity, or a frozen-contract canonical-URL
   fallback, identifies one economic appearance without conflation;
4. pagination, explicit zero state and exhaustion are deterministic;
5. all mandatory surfaces fail the entire `FULL_SOURCE` run if incomplete;
6. the existing pipeline can produce immutable RAW evidence, observations,
   green assessments, health and equal completeness counters; and
7. a real `FULL_SOURCE` acceptance run is `SUCCEEDED`, `HEALTHY`, complete and
   exactly replayable without hidden manual intervention.

No prohibited request, authentication/session reuse, private token, browser
collector, mirror, Job-Room substitute, synthetic identity, imputation or fake
zero run is permitted.

## Class-specific evidence

### Semantic identity — AI and NW

Every current opportunity must map causally to one stable source object. The
evidence must distinguish inactive profiles, recurring single opportunities,
simultaneous cohorts/routes and generic career material. A persistent profile is
not active evidence by itself. A shared object representing materially distinct
concurrent opportunities remains blocked unless the source publishes their own
distinct identities. Reappearance must retain one Posting/Vacancy and create a
new episode only where the object truly represents one recurring opportunity.

AI additionally requires a complete authorized ordinary-employment contract.
NW specifically requires official evidence resolving `NW-1616` as one continuous
standing opportunity, or source-native cohort/application identities for its
simultaneously active routes. Occupation/year strings may not be fabricated.

### Access policy — AG and OW

Recovery requires an independently official origin exposing the complete Source
universe through governed GET/POST, with explicit official linkage, stable
identity and deterministic exhaustion. Applicable robots evidence must permit
every required path. Absence of a visible prohibition alone is not authorization.
An unchanged prohibited canonical path, a browser-only path or a partial
alternate origin remains `POLICY_BLOCKED`.

### Multi-surface — BE, FR and VS

Before implementation, enumerate every mandatory same-employer surface,
separate employer, non-vacancy surface and duplicate presentation. The complete
union must have authorized origins, stable identities, explicit empty states and
deterministic exhaustion. Bilingual presentations are one Posting where native
identity proves equality. A functioning ordinary feed cannot compensate for an
unresolved teacher, substitute, training or gazette surface.

BE must resolve KSML and STEZE or prove them outside the canonical employer.
FR must prove a completed migration or exhaust an authoritative cross-platform
inventory. VS must reconcile e-recruitment, official-gazette teaching and
training channels, including bilingual identity.

### Source universe — JU

Recovery requires an explicit teaching list/zero-state contract and item-level
classification of `Autres` as same canonical employer or separate employer.
Contacts, calendars, replacement pools and generic training information are not
vacancy or zero-state evidence. No collector is authorized before the canonical
surface union is resolved.

### Technical reliability — UR

The predeclared reliability experiment is two consecutive governed
`FULL_SOURCE` runs, started only after one successful listing probe, using the
existing timeout/retry policy. Each run must exhaust the same official listing
and every mandatory detail, be `SUCCEEDED`, `HEALTHY`, complete, have equal
listing/in-scope/detail/observation/green counters and require no manual retry.
The second run must preserve stable native identities and deterministic
collection results, allowing legitimate live content change. Any timeout,
incomplete detail, degraded health or manual intervention leaves UR
`TECHNICAL_RELIABILITY_BLOCKED`.

## Per-source frozen recovery conditions

| Source | C-6 blocker | Evidence required for transition |
|---|---|---|
| `SRC-OFF-CANTON-AI` | `SEMANTIC_IDENTITY_BLOCKED` | Vacancy-level apprenticeship identity/state/exhaustion plus complete authorized ordinary contract. |
| `SRC-OFF-CANTON-AG` | `POLICY_BLOCKED` | Independently official, complete and robots-permitted public origin. |
| `SRC-OFF-CANTON-BE` | `MULTI_SURFACE_BLOCKED` | Authorized/exhaustible KSML and STEZE replacement contracts, or governed proof they are outside the Source. |
| `SRC-OFF-CANTON-FR` | `MULTI_SURFACE_BLOCKED` | Completed migration or authoritative cross-platform identity and exhaustion. |
| `SRC-OFF-CANTON-JU` | `SOURCE_UNIVERSE_BLOCKED` | Explicit teaching list/zero state and resolved `Autres` employer boundary. |
| `SRC-OFF-CANTON-NW` | `SEMANTIC_IDENTITY_BLOCKED` | `NW-1616` proven one standing opportunity, or native identities separating concurrent routes/cohorts. |
| `SRC-OFF-CANTON-OW` | `POLICY_BLOCKED` | Authorized complete alternate official origin or applicable official platform/access change. |
| `SRC-OFF-CANTON-UR` | `TECHNICAL_RELIABILITY_BLOCKED` | Two consecutive complete healthy governed `FULL_SOURCE` runs under the bounded experiment above. |
| `SRC-OFF-CANTON-VS` | `MULTI_SURFACE_BLOCKED` | Deterministic ownership, bilingual identity and exhaustion across every mandatory surface. |

## Disposition evidence and historical replay

Every decision must pin Source, prior/new disposition and blocker class,
outcome, recovery condition, bounded official evidence, `effective_at`, decision
time, governance version and implementation authorization. The current
disposition at cutoff `T` is the latest decision with `effective_at <= T` under
the explicitly selected disposition governance version. Equal-effective-time
ties are forbidden within a version.

Historical assessments continue using their pinned historical configuration and
the C-6 20/29 ceiling. A new readiness assessment may use recovered disposition
evidence only by explicitly fingerprinting its disposition version and exact
decision IDs. Numeric coverage and freshness policy versions remain unchanged.
