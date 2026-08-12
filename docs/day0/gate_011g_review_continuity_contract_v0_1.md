# GATE-011G review continuity contract v0.1

Status: **FROZEN BEFORE CORPUS LINEAGE MEASUREMENT**  
Baseline: `0d0acd753b42d004d3243866d4daf7449dafebe8` (merged GATE-011F)  
Policy scope: review continuity only; no classifier, dedup, source-disposition, or Day-0 policy change.

## Purpose and separation of evidence

A new observation always receives a new immutable classifier assessment. A human review decision remains attached to the exact assessment actually reviewed. This contract permits a separate append-only application of that prior human knowledge only when a later assessment has the same governed Posting identity and exactly the same predeclared decision-relevant material evidence.

The application is not a new human decision. It must identify the source human decision, target assessment, material fingerprint and version, causal availability, application method, and both raw hashes as provenance. Any material difference leaves the new assessment governed by its own original result.

No fuzzy comparison, embeddings, LLM similarity, title-only matching, or raw-byte equality is used.

## Green material contract

Version: `green-review-material-v0.1`  
Review governance: `green-review-v0.1`  
Normalization: `NFKC_CASEFOLD_WHITESPACE_V0.1`, exactly `observations.green_relevance.normalize_for_matching`.

### Identity boundary

Reuse requires exact equality of:

- `source_id`;
- governed Posting identity (`Posting.id` and `source_native_id`);
- green classifier version;
- taxonomy version and taxonomy SHA-256;
- review-governance version; and
- material fingerprint version.

Text equality across different Postings never permits reuse.

### Material representation and fingerprint

The canonical JSON payload is serialized with sorted keys and compact separators, then SHA-256 hashed. It contains:

- identity and all versions above;
- normalized `TITLE` from `PostingObservation.title`;
- normalized `TEXT` from the exact ordered concatenation used by `green-relevance-v0.1`: description, responsibilities, qualifications, and benefits;
- normalized `ORGANIZATION` from `hiring_organization`;
- original classifier result;
- complete, deterministically sorted positive, conditional, and exclusion match evidence;
- classifier reason codes, normalization identifier, and matching method.

The three normalized surfaces are complete because they are the only source surfaces read by the frozen classifier and by the GATE-011E human adjudication contract. Dates, URL presentation, transport markup outside those fields, and raw artifact identity do not independently determine green relevance.

### Raw provenance

Source and target raw SHA-256 values are retained on every application, but raw SHA is not part of the material fingerprint. A raw payload may change while the complete normalized decision-relevant representation remains equal; in that case reuse is allowed and both hashes make the byte-level difference explicit.

### Outcome and invalidation

An exactly matching prior outcome maps as follows:

| Human outcome | Target effective result |
|---|---|
| `CONFIRMED_GREEN` | `GREEN_CONFIRMED` |
| `CONFIRMED_NOT_GREEN` | `NOT_GREEN` |
| `INSUFFICIENT_EVIDENCE` | `REVIEW` |

Any change to identity, any normalized material surface, classifier matches or reasons, classifier version, taxonomy version/hash, review-governance version, or fingerprint version invalidates reuse. Changes outside this representation do not.

One target assessment and review-governance version may have either one direct human decision or one inherited application, never contradictory authority. Exact concurrent application attempts are idempotent. A different source decision or fingerprint fails closed. A later direct override requires a separately governed future revision mechanism.

### Causality

At cutoff `T`, reuse is available only when all of these are `<= T`:

- target assessment `created_at`;
- original decision `reviewed_at` and `created_at`;
- application `created_at`.

The source decision must predate or equal the application. No application changes historical Premium, Dashboard, or Day-0 artifacts already persisted.

Premium must pin the origin as exactly one of `ORIGINAL_CLASSIFIER`, `DIRECT_HUMAN_DECISION`, or `MATERIAL_IDENTICAL_HUMAN_REUSE`, plus the relevant decision/application IDs. Those IDs, the material fingerprint/version, and origin participate in the Premium input fingerprint and persisted evidence.

## Dedup material contract

Version: `dedup-review-material-v0.1`  
Dedup version: `dedup-v0.1`  
Normalizer: `dedup-normalizer-v0.1`.

### Pair identity

Reuse is confined to the same unordered governed Posting pair, canonically sorted by `Posting.id`. Each side pins `source_id`, `source_native_id`, and `Posting.id`. A different pair never inherits a decision.

### Material representation and fingerprint

The canonical sorted JSON payload binds every input capable of changing the frozen GATE-008 identity decision:

- dedup and normalizer versions;
- complete dedup configuration, weights, thresholds, repost window, and source-precedence version;
- for each canonically ordered Posting: normalized employer, title, location, duties/text, pensum-contract-start, and canonical URL;
- explicit requisition value and provenance;
- explicit redirect target;
- derived feature scores;
- hard-key evidence;
- hard barriers, including any repost-window barrier;
- algorithm method, score, and pre-human outcome;
- lifecycle material state described below.

It deliberately excludes PostingObservation UUID, raw SHA, collection-run ID, and lifecycle-event UUID. These identify immutable evidence instances but do not themselves change economic identity.

### Lifecycle material representation

For each Posting, material lifecycle is:

- economic state: `ACTIVE` for `NEW`, `STILL_ACTIVE`, and `DISAPPEARED_PENDING`; or `CLOSED_OBSERVED`;
- run-scoped `episode_number`; and
- closure/reappearance facts used by the repost-window rule, represented by their governed timestamps/gap consequence rather than event UUID.

A routine later `STILL_ACTIVE` observation in the same active episode does not invalidate an otherwise identical identity decision. `DISAPPEARED_PENDING` likewise remains economically active. `CLOSED_OBSERVED`, reappearance, episode-number change, repost-window consequence, canonical identity consequence, or any other identity input change invalidates reuse.

### Reuse and effects

Only prior human `KEEP_SEPARATE` or `MERGE` decisions for the same pair, material fingerprint, and versions may be applied. The application is append-only and pins the target algorithm decision/review item, source human decision, fingerprint/version, method, and causal timestamps.

`KEEP_SEPARATE` prevents the equivalent later review from reopening. `MERGE` may alter economic Vacancy identity and therefore is applied only after the complete fingerprint matches; it follows the existing `merge_vacancies` and projection reconciliation path without changing thresholds or identity rules.

Exact concurrent applications are idempotent; conflicts fail closed. A direct target human resolution and inherited application cannot both be authoritative under the same material/governance versions.

### Dedup causality

At cutoff `T`, the source human decision and reuse application must have been created/resolved by `T`, and all target pair evidence must be causally selected by the target Dedup run at `T`. Future decisions never affect historical runs or snapshots.

## Measurement and acceptance protocol

Only after this contract is committed alone may GATE-011G:

1. measure the 54 green and one dedup critical reviews at the GATE-011F cutoff;
2. classify lineage without adjudicating changed/new evidence;
3. implement the append-only application mechanisms;
4. reconstruct the exact cutoff; and
5. perform a second controlled refresh of the 20 implemented required Sources.

No target reuse count is stipulated. Material equality decides the result. The nine blocked Sources remain excluded from collection, the required denominator remains 29, and Day-0 coverage remains governed by the unchanged 24/29 minimum.
