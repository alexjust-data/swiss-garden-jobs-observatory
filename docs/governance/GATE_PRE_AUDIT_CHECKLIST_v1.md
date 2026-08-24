# Gate Pre-Audit Checklist v1

## Purpose

`gate_pre_audit.py` is a read-only mechanical evidence collector and verifier.
It reduces repetitive gate bookkeeping. It does not interpret scientific
contracts and it never approves a pull request for merge.

```text
H1 mechanical evidence
        -> READY FOR SEMANTIC AUDIT

independent semantic audit
        -> APPROVED / NOT APPROVED FOR MERGE
```

## Result states

Every check has exactly one state:

- `PASS`: the stated fact was mechanically established.
- `FAIL`: a mechanically testable invariant was violated.
- `NOT_PROVEN`: no violation was established, but the fact could not be proved.

The overall result is:

- `FAIL` when any mandatory check fails;
- `NOT_PROVEN` when no mandatory check fails and at least one mandatory check is
  not proven;
- `PASS` only when every mandatory check passes.

Only overall `PASS` emits `READY FOR SEMANTIC AUDIT`. The harness must never emit
`APPROVED FOR MERGE`.

## Read-only boundary

The harness may read Git, the local checkout, committed profiles and GitHub. It
may run the standard validation commands declared by this version. It must not:

- run collectors, geocoders, daily operations or production acceptance;
- migrate or mutate an operational database;
- write RAW objects or scientific evidence;
- edit migrations, contracts, frozen research or source code;
- push, merge, comment on, close or otherwise mutate a pull request.

Reports are written only below `.gate-audit/` by default or an explicit
`--output-dir`. Python, pytest, Ruff and mypy caches used by harness-owned
commands must also be redirected or disabled so the audited checkout is not
modified.

## Deterministic evidence

The JSON report separates:

- `evidence`: canonical substantive facts and check results;
- `execution`: generated time, durations and command output used for diagnosis.

`evidence_sha256` is computed from canonical JSON for `evidence` only. Repeating
the audit against unchanged repository and PR evidence must reproduce that hash.
Volatile timestamps and durations must not enter it.

## Gate profile

A profile is intentionally small. Version 1 accepts only:

```json
{
  "schema_version": "gate-pre-audit-profile-v1",
  "gate": "GATE-010-C4",
  "pr": 30,
  "contract": "docs/day0/example_contract_v0_1.md",
  "contract_blob": "0123456789abcdef...",
  "frozen_paths": ["docs/research/v0_4/"],
  "focused_tests": ["src/core/tests/test_example.py"],
  "expected_migrations": []
}
```

Global defaults remain in the harness. A profile cannot add arbitrary shell
commands, network actions or mutation hooks.

## Mandatory mechanical checks

Version 1 verifies:

- local repository and clean tracked/untracked state;
- local `HEAD` equals the exact PR head;
- PR base and head Git objects are available;
- contract blob equals the profile's frozen blob;
- frozen paths have no base-to-head changes;
- changed-file and migration inventories are exact;
- focused tests and standard local validation when local validation is enabled;
- exact-head GitHub checks;
- exact-head GitGuardian result;
- unresolved review-thread count.

Standard local validation is:

```text
focused pytest
full pytest
Ruff
mypy
Django check
makemigrations --check --dry-run
```

The report records whether each result was executed locally or merely observed
from remote evidence. An observed aggregate CI result is not relabelled as a
specific local command result.

## Safe GitHub degradation

Missing `gh`, missing authentication, unavailable fields, rate limits or GitHub
errors must not crash the audit and must not pass silently. Affected checks are
`NOT_PROVEN` and the remaining local checks continue.

## Operational facts outside H1

H1 always exposes these informational checks:

- Source HTTP requests;
- geocoder/provider HTTP requests;
- real operational database mutations;
- exact PIT replay.

They are `NOT_PROVEN` unless a future explicitly governed evidence adapter can
prove them. They are not mandatory for H1 readiness because they belong to the
separate production-acceptance harness. H1 must never infer zero.

## Exit codes

- `0`: overall `PASS`;
- `1`: overall `FAIL`;
- `2`: overall `NOT_PROVEN`;
- `3`: invalid harness invocation or profile.
