# Operational RAW lineage runbook

This runbook operates GATE-010-C4 storage lineage. It does not collect Sources, geocode jobs or
change PostgreSQL scientific rows.

## Required configuration

Production mutable execution requires three explicit values:

```text
JOB_OBSERVATORY_RAW_STORE_PATH=<absolute canonical root>
JOB_OBSERVATORY_OPERATIONAL_RAW_STORE_PATH=<same absolute canonical root>
JOB_OBSERVATORY_RAW_LINEAGE_MANIFEST_SHA256=<committed designation SHA>
```

Do not use `./data/raw` for the operational database. The canonical root must be outside every Git
worktree and must contain the matching `.operational-raw-lineage-v0.1.json` sentinel.

## Build an audit candidate

Use a PostgreSQL account with read access and declare every historical source root with a stable,
non-secret label:

```powershell
python manage.py build_raw_lineage_manifest --source-root "historical_a=X:\absolute\raw-a" --source-root "historical_b=X:\absolute\raw-b" --output "X:\audit\manifest.json" --designation-output "X:\audit\designation.json" --json
```

Candidate designation output is not authority. Only the designation committed after isolated
acceptance is trusted by the mutation command.

## Dry-run

The destination may be absent. Dry-run must not create it:

```powershell
python manage.py consolidate_operational_raw_lineage --manifest "X:\audit\manifest.json" --source-root "historical_a=X:\absolute\raw-a" --source-root "historical_b=X:\absolute\raw-b" --destination-root "X:\canonical-raw" --dry-run --json
```

Any missing, ambiguous, conflicting or unsafe identity is a hard stop.

## Apply

Back up PostgreSQL and every historical root first. Then use the exact independently audited
manifest:

```powershell
python manage.py consolidate_operational_raw_lineage --manifest "X:\audit\manifest.json" --source-root "historical_a=X:\absolute\raw-a" --source-root "historical_b=X:\absolute\raw-b" --destination-root "X:\canonical-raw" --apply --json
```

The command may be interrupted safely. Complete objects remain immutable but have no root
authority until the sentinel is published. Retry the exact command; never delete partial final
objects.

## Verify replay

Run the exact apply command a second time. Required result:

```text
created = 0
reused = expected_object_count
sentinel_created = false
sentinel_reused = true
```

## Restore smoke test

Restore the PostgreSQL custom-format dump into a new isolated database. Restore both RAW root
snapshots into isolated absolute paths. Build a new read-only manifest and compare:

- RawArtifact inventory fingerprint;
- source inventory fingerprint;
- object count;
- aggregate byte count;
- representation counts.

Snapshot and manifest SHA values should differ because the transaction and root identities are
new. The above scientific/storage inventory values must be identical.

For Windows paths exceeding `MAX_PATH`, use the `\\?\X:\...` extended-path form during read-only
restore validation.

## After C4 merge

1. synchronize merged `main`;
2. verify the audited manifest and backups;
3. consolidate into a new absolute real operational root;
4. set the three required environment values;
5. run `resolve_premium_locations --dry-run`;
6. run the governed real geospatial retry;
7. run the exact retry and require zero provider requests;
8. construct a new causal PIT.

Never modify or remove either historical source root inside C4.
