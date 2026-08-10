# Decision 0006: GATE-010 Point-in-Time Map Dashboard

## Status

Accepted for implementation in GATE-010.

## Decision

DashboardSnapshot and DashboardVacancyRecord are immutable, versioned presentation evidence. They are built from one exact successful DedupRun, one exact successful PremiumSegmentRun, and a shared as_of. DedupRunVacancyState and DedupRunPostingAssignment remain the vacancy authority; mutable Vacancy projections are not dashboard inputs.

Only the canonical observation's exact green-relevance-v0.1 assessment can make a record public. Premium/private segments are referenced from the aligned premium run and are never reclassified in the view layer. Geospatial presentation uses only public_display_latitude and public_display_longitude from geospatial-v0.1 under the required privacy context. Protected records never fall back to a public resolution.

Source links use source-link-v0.1. Explicit source evidence takes priority. Individual canonical links may be labelled "Open original advert"; discovery and historical links use "Open observed source"; missing or review links expose no action. CLOSED_OBSERVED is not treated as explicit source expiration.

The public API is pinned to an immutable snapshot ID. The table contains all public green-confirmed records, while GeoJSON contains only safely mappable records. Date provenance, first/last observation, mapping precision, privacy generalization, source link status, and unavailable-field states remain explicit.

The frontend uses Django templates, lightweight JavaScript, and locally served MapLibre GL JS 6.2.0. Map and table share one query-string filter state and one detail drawer. An empty local style is used when no licensed style URL is configured. Browser tests block all external network access.

GATE-010 does not authorize Day-0. Headline market cards remain pending and a persistent coverage disclaimer states that implemented sources are not a complete Swiss market census. Salary extraction, access-level classification, new collectors, scheduling, geocoding, and upstream semantic changes remain outside scope.

Exact snapshot replay is fingerprinted and idempotent. PostgreSQL advisory locking prevents duplicate concurrent builds. A build is transactional and cannot publish partial record coverage. Frozen docs/research/v0_4 remains unchanged.

## Audit clarification: temporal and presentation authority

A geospatial derivation is eligible only when its immutable created_at is less than or
equal to the dashboard as_of. Rebuilding a historical snapshot cannot consume a later
resolution merely because it references the same observation. The dashboard fingerprint
covers the selected resolution identity, its availability timestamp, run assignments, and
all persisted presentation values.

Current means the supported dashboard version with the greatest as_of; deterministic
fingerprint and primary-key ordering resolve ties. Historical rebuild insertion time is not
currentness. Exact snapshot endpoints are immutable; table, GeoJSON, and detail requests
remain pinned to the selected snapshot UUID.

HTTP and HTTPS source links are accepted because historical public-sector evidence may
retain HTTP URLs. URL credentials, controls, whitespace obfuscation, malformed hosts, and
non-HTTP schemes fail closed. Portal and discovery statuses prefer the observed source URL
and never receive an original-advert label.
