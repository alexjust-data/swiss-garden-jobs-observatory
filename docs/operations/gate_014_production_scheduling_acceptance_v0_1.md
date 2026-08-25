# GATE-014 — Production scheduling acceptance v0.1

## Authority and scope

- Upstream merged main: `99e39312535f33554a973110cba196c253628945`.
- Stacked GATE-013 head: `30aed57e9e547b2cc18c65c24d01b624ccd1ea5b`.
- Branch: `codex/gate-014-production-scheduling`.
- Contract-only commit: `7be211a50efbbd835bcc1818c01f07b7d65dd7ca`.
- Contract blob: `6619ac84e4776d7de6056dacef0b8986d5142014`.
- Validated code head: `98653a623775b775c91efd34142f019a4a2778d5`.
- Final documentation/H1 head: pinned in the draft PR.
- State: isolated acceptance; production activation not authorized.

The frozen contract was committed alone. GATE-014 adds deployment tooling only and changes no
scientific semantics, model or migration.

## Implemented behavior

The scheduled wrapper:

```text
validate environment names
-> validate exact Git SHA and clean checkout
-> run exactly one SCHEDULED daily cycle
-> preserve its exact exit code
-> read deterministic status
-> publish one bounded no-overwrite JSON envelope
```

A process timeout produces external exit 124. A process-launch failure produces 125. Failure to read
status is recorded separately while preserving the cycle result. Output payloads are hashed; only
bounded operational identifiers are retained.

The Windows task plan binds absolute paths, exact SHA, daily local start boundary, Europe/Zurich
civil-time equivalence, `IgnoreNew`, no catch-up, least privilege and bounded execution. The
authoritative registration path revalidates the deployment immediately before scheduler activity.
No `/F` overwrite is possible.

The backup wrapper creates one custom-format dump in an external root, validates its inventory,
hashes it and publishes one manifest. It has no restore or retention-delete path. Publication error
removes the dump created by the same invocation.

## Focused adversarial acceptance

The isolated suite proves:

- deterministic secret-free dry plans with zero governed writes/HTTP;
- missing environment and SHA/worktree drift fail before execution;
- log/backup roots inside Git worktrees are rejected;
- cycle exit propagation, timeout and status failure boundaries;
- bounded envelope content and stable-evidence fingerprinting;
- Windows no-overlap/no-catch-up/least-privilege XML;
- Europe/Zurich-equivalent Windows zones and wrong-zone refusal;
- exact task reuse, conflict refusal and create-without-force;
- registration validates deployment before task activity;
- backup dry plan, verified publication and secret exclusion;
- dump/restore execution failure and manifest failure publish nothing accepted.

Focused result before repository-wide validation:

```text
GATE-014 scheduling/backup tests    23 passed
Ruff focused                       PASS
mypy new domain modules            PASS
```

## Validation

The first full run used an extra operational-RAW environment override not present in CI and caused
one expected C2 scope test to fail (`561 passed, 1 failed`). It was rejected as an invalid validation
environment. The exact official-CI RAW environment then passed, and the final run after the portable
publication correction passed:

```text
full pytest                         563 passed
focused GATE-014                     23 passed
Playwright                            4 passed
Ruff                               PASS
mypy                               PASS — 172 source files
Django check                        PASS
makemigrations drift                NONE
```

### Real isolated PostgreSQL backup

A dedicated PostgreSQL 16 container on port 55435 contained only one acceptance table/row. The
governed backup wrapper ran from the exact clean code head. Its first real attempt exposed that the
external `G:` filesystem does not support hardlinks; no accepted dump or manifest was published.
The implementation was corrected to use Windows atomic no-replace rename (and POSIX hardlink
publication), with explicit collision tests.

The corrected execution produced:

```text
dump SHA-256
f85c1361c7f3566dcf70695ca8b7a3e6d521601dbd67cb510b794b55439f032b
dump bytes                           1770
inventory SHA-256
cae37a09fc465e563516cd370ec5e1607f0a3eabaa539dc03dad92ea8469bf66
stable evidence SHA-256
a282e8a93d9096354ba16f2b9f7d23596edb2f1391c77af39e2adc20d1d0001a
restore into second isolated DB      PASS
restored probe                       1|gate014
```

The real dry-run wrapper and Windows task plan both validated the exact clean SHA. The host reported
`Romance Standard Time`, an accepted Europe/Zurich civil-time equivalent. The dry runs created no
log directory and registered no task.

H1 evidence is added only after a draft PR has an exact GitHub head; it is not inferred here.

## Production boundary

The following remain forbidden before independent audit and merge:

```text
real Windows task registration       0
real operational backup writes       0
real scheduler-triggered cycles      0
real DB mutations                    0
canonical RAW mutations              0
Source HTTP                           0
geocoder/provider HTTP                0
human adjudication                    0
```

The tooling PR can become ready for semantic audit without crossing any of those boundaries.
