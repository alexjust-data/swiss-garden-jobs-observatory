# JOB DETAIL AND SOURCE LINK CONTRACT v0.1

## Objective

Every job represented on the map or in the results table must expose a human-readable detail view and a traceable route back to the publication where it was observed.

## User interaction

```text
MAP MARKER
    ↓
SUMMARY POPUP
    ├── View full job details
    └── Open publication/source
            ↓
FULL DETAIL DRAWER
    ├── salary and pensum
    ├── dates and observed state
    ├── role, access level and qualifications
    ├── employer and employment relationship
    ├── location and privacy precision
    ├── source quality
    └── external publication link
```

Rows in the jobs table open the same detail drawer. Keyboard access with Enter/Space and closing with Escape are required.

## Link semantics

The interface must never label every URL as an original job advert. The visible action is determined by `canonical_url_status`:

| Status family | Visible label | Meaning |
|---|---|---|
| `CANONICAL`, `AGENCY_CANONICAL`, `ORIGINAL_ATS_LINKED` | Open original advert | Individual canonical publication |
| portal known / URL pending | Open source where published | Source identified; direct individual URL pending |
| `DISCOVERY_OR_HISTORICAL` | Open observed source | Discovery/search/historical evidence |
| `EXPIRED_SOURCE` | Open expired link | Publication was explicitly expired |

Preferred URL order:

```text
canonical_url
    ↓ fallback
source_url
    ↓ fallback
no link available
```

## Minimum detail fields

- original title and employer;
- posting state;
- source publication date, first seen and last observed;
- municipality/region, canton and location precision;
- workload;
- salary as published and salary interpretation note;
- role family, access level and qualification signal;
- client segment and employment relationship;
- public service area where applicable;
- source name/type and canonical URL status;
- internal observation identifier;
- research notes.

## Privacy

Private villas and households use municipality/region centroids in the public interface. The detail drawer must explicitly state that the map location is approximate.

## Historical behaviour

An expired or closed job remains inspectable. Its original/observed URL may be opened, but the interface must warn that the external page can be unavailable or changed.
