# GATE-011D-C2 Policy Artifact Lineage Audit v0.1

Status: COMPLETE — no historical row was edited or deleted.

## Conclusion

The PostgreSQL artifact `ce0e3c908a4c07c8ba3f4847c8cc9c84df362534c64db269c4f6b4d37d934230`
is an exact materialization of the pre-merge PR #19 representation. It was not the policy tree
merged into `main`. The accepted semantic policy remains `day0-authorization-v0.1`; C2 requires no
`v0.2`.

## Git-governance reconstruction

| Evidence | Policy representation |
|---|---|
| `2c07f634c8e5746fae9d8a03402951d87010968e` | Pre-merge v0.1: Federal 1, Canton 15, City 4; no `derived_canton_floor`; lowercase `healthy` in selected-run descriptor. |
| `75cab6b54ea9295cf9f3c072b0f69243ecf6d95c` | Final v0.1: Federal 1, City 4, derived Canton floor 17; uppercase `HEALTHY`; immutable collision guard. |
| `76c427ef9bf038872addfd32d1cfac3f633b04da` | Final PR tree and API alignment. |
| `1a1af1f5ac3fb2657d5b034cd6ff602a5c08cc5b` | Squash merge of PR #19. Its Day-0 tree is byte-identical to `76c427ef…`. |

The ordered PR history is `2c07f634… → 75cab6b54… → 76c427ef…`. Squash ancestry does not make
the intermediate commits ancestors of `main`; tree comparison proves which representation was
merged. Merged ADR 0015 explicitly records 24/29, Federal 1/1, City 4/6, derived Canton 17/22 and
the inclusive 72-hour freshness rule.

### Reconstructed pre-merge artifact

The canonical fingerprint envelope is `policy_version`, threshold/freshness statuses and the
following configuration. Mechanical SHA-256 reconstruction produces exactly
`ce0e3c908a4c07c8ba3f4847c8cc9c84df362534c64db269c4f6b4d37d934230`.

```json
{
  "alternatives_considered": ["1.00", "0.90", "0.80", "two_thirds"],
  "authorization_policy_version": "day0-authorization-v0.1",
  "coverage_policy_version": "day0-coverage-v0.1",
  "denominator": 29,
  "equal_source_weighting": true,
  "final_blocked_required_sources": {
    "SRC-OFF-CANTON-AG": "POLICY_BLOCKED",
    "SRC-OFF-CANTON-AI": "SEMANTIC_IDENTITY_BLOCKED",
    "SRC-OFF-CANTON-BE": "MULTI_SURFACE_BLOCKED",
    "SRC-OFF-CANTON-FR": "MULTI_SURFACE_BLOCKED",
    "SRC-OFF-CANTON-JU": "SOURCE_UNIVERSE_BLOCKED",
    "SRC-OFF-CANTON-NW": "SEMANTIC_IDENTITY_BLOCKED",
    "SRC-OFF-CANTON-OW": "POLICY_BLOCKED",
    "SRC-OFF-CANTON-UR": "TECHNICAL_RELIABILITY_BLOCKED",
    "SRC-OFF-CANTON-VS": "MULTI_SURFACE_BLOCKED"
  },
  "freshness": {
    "boundary": "inclusive",
    "clock": "wall_clock",
    "later_failed_activity": "preserves accepted evidence but invalidates current health",
    "maximum_age_hours": 72,
    "selected_run": "latest_causally_available_healthy_complete_FULL_SOURCE",
    "timestamp": "CollectionRun.finished_at"
  },
  "freshness_policy_version": "full-source-freshness-v0.1",
  "governed_disposition_required": 29,
  "market_semantics": "Observed active GREEN_CONFIRMED vacancies in fresh, healthy, complete required Sources at the exact PIT cutoff; never a national census or estimate.",
  "minimum_required_source_count": 24,
  "minimum_required_source_coverage": "0.8000",
  "stratum_minima": {"CANTON": 15, "CITY": 4, "FEDERAL": 1}
}
```

Envelope statuses are `threshold_policy_status=ACCEPTED` and
`freshness_policy_status=ACCEPTED`.

### Reconstructed final merged artifact

Mechanical reconstruction produces
`a72dd56dee6f6a580e1904c4e5427dd3dab9109775fd83722f2108cafb8d294e`.
All fields above remain identical except:

```json
{
  "derived_canton_floor": 17,
  "freshness.selected_run": "latest_causally_available_HEALTHY_complete_FULL_SOURCE",
  "stratum_minima": {"CITY": 4, "FEDERAL": 1}
}
```

The Canton value moved from an independently persisted minimum of 15 to the merged derived floor
of 17. This is a material artifact difference inside the same not-yet-merged semantic version, not
a post-merge policy change.

## Existing PostgreSQL lineage

Read-only measurement before C2 implementation found:

- legacy policy ID: `bedee7bb-f826-4584-9e0e-1e37b617b30b`;
- created: `2026-08-12T05:55:08.046077Z`;
- version: `day0-authorization-v0.1`;
- fingerprint: `ce0e…4230`;
- exact configuration: the reconstructed pre-merge JSON above;
- readiness reference: `6f189434-ab48-4c69-bfdd-0237101c4b06`;
- readiness fingerprint: `806dba637a1722d2cf56dfc90dfd238a1f08e683e5fb4a7f8a51c083b1132ef0`;
- readiness cutoff: `2026-08-12T07:30:00Z`;
- readiness result: `DAY_0_BLOCKED_BY_DATA_QUALITY`.

The row was created while the pre-merge implementation was being exercised and before the final
PR tree was merged. Its exact fingerprint—not timestamp proximity—is the decisive lineage proof.

The two semantic-v0.1 source universes are:

- `8a501ab0-566a-433a-9bd4-23d735354deb`, fingerprint `a6b99e…e04f`;
- `f1e65171-cdeb-49dd-8dd2-3cc74cfc904a`, fingerprint `9fb00f…d5cd`.

`Day0SourceUniverse` selects Sources and pins the semantic authorization version, registry hash,
coverage-matrix hash and entry evidence. Its material identity does not include thresholds,
freshness representation or an authorization-policy artifact. Readiness supplies the exact policy
FK and policy fingerprint. Multiple v0.1 artifacts therefore do not make historical universes
ambiguous, and no universe migration or rewrite is warranted.

Exact readiness API lookup dereferences the readiness row's preserved policy FK. There is no
downstream FK that retargets this historical assessment. The current convenience endpoint remains
a selection over immutable readiness rows; exact-ID history is unchanged.

The exact API response at
`/api/v1/day0/readiness/6f189434-ab48-4c69-bfdd-0237101c4b06/` has canonical JSON SHA-256
`d3267d4b02e59260f9613135489375eca564fc1f4f5f44c4f592d0a20b980243` both on the original
read-only database and on the migrated isolated copy.

## Isolated existing-database acceptance

The real database was not migrated. A PostgreSQL template copy was measured before and after C2:

- legacy policy ID/configuration/fingerprint/created-at: unchanged;
- legacy readiness ID/fingerprint/policy FK: unchanged;
- canonical artifact ID: `82506912-da6f-4b3d-b119-4e0943be5156`;
- canonical fingerprint: `a72d…294e`;
- designation ID: `dbb5e50c-b802-489e-b32f-99c6b3b14e18`;
- designation fingerprint: `72604ca0adbc604b68be028117f74b8dac4bb004e1b2c7ff02a77dfa5186c8eb`;
- second ensure: same artifact and designation; two v0.1 artifacts total.

A new canonical readiness was built from already-present immutable PIT artifacts, with no Source
request or GATE-012 cycle:

- readiness ID: `6c07b2c8-de74-406c-83d6-5c98c7a18df8`;
- fingerprint: `67ac00eb39f463cdbdaeb20b5c0c155da0c1748d2234a8a5ea3ec003fc9b91ac`;
- policy FK: canonical `82506912…`;
- result: `DAY_0_BLOCKED_BY_DATA_QUALITY`;
- required/implemented/fresh: 29/20/20;
- exact replay: same ID and fingerprint.

The review counts reflect that copied database at its existing cutoff and are not policy inputs or
C2 acceptance targets.

## Isolated clean-database acceptance

After clean migration and two reference imports:

- legacy `ce0e…` artifact created: NO;
- canonical artifact ID: `4a5a6f3b-f931-4dae-888c-9437ff5953b1`;
- canonical fingerprint: `a72d…294e`;
- designation ID: `612460f3-9329-4e07-876d-fb4ce4a947c6`;
- second ensure: reused both; one artifact and one designation.

These UUIDs identify isolated acceptance evidence only. Production identity is governed by exact
fingerprints and designation evidence.
