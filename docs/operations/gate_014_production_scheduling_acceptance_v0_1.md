# GATE-014 — Production scheduling acceptance v0.1

## Authority and scope

- Upstream merged main: `99e39312535f33554a973110cba196c253628945`.
- Stacked GATE-013 head: `30aed57e9e547b2cc18c65c24d01b624ccd1ea5b`.
- Branch: `codex/gate-014-production-scheduling`.
- Contract-only commit: `7be211a50efbbd835bcc1818c01f07b7d65dd7ca`.
- Contract blob: `6619ac84e4776d7de6056dacef0b8986d5142014`.
- Final implementation head: pinned after validation.
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
GATE-014 scheduling/backup tests    22 passed
Ruff focused                       PASS
mypy new domain modules            PASS
```

## Validation

Final repository-wide, PostgreSQL backup and H1 evidence are recorded after the implementation head
is frozen. No validation result is inferred before it is run.

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
