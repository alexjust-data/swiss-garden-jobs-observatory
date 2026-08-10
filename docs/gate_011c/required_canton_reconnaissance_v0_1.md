# GATE-011C-1 required canton reconnaissance v0.1

Reconnaissance date: 2026-08-10. Official endpoints only.

| Source | Frozen family | Verified contract | Authorized origins | Pagination/completeness | Strategy | Terminal target |
|---|---|---|---|---|---|---|
| `SRC-OFF-CANTON-ZH` | `SOLIQUE_LINKED` | Solique `KTZH` JSON API plus Solique detail | `www.zh.ch`, `live.solique.ch` | API job universe; `filters.position.count` must equal unique IDs | New reusable Solique API translator | `ACCEPTED_IMPLEMENTED` |
| `SRC-OFF-CANTON-AR` | `SOLIQUE_EMBEDDED` | Solique legacy `api/json/` plus `Microsites/showPublication` | `ar.ch`, `live.solique.ch` | Client-side feed contains complete job array | New reusable Solique legacy translator | `ACCEPTED_IMPLEMENTED` |
| `SRC-OFF-CANTON-ZG` | `PROSPECTIVE` | Prospective legacy listing plus official `www.zg.ch` JSON-LD detail | `zg.ch`, `zg.prospective.ch`, `www.zg.ch` | POST offsets of 10 until no forward page | Configured shared Prospective translator | `ACCEPTED_IMPLEMENTED` |
| `SRC-OFF-CANTON-BL` | `PROSPECTIVE_UMANTIS_LINKED` | Prospective career center plus official `jobs.baselland.ch` JSON-LD detail | `www.baselland.ch`, `ohws.prospective.ch`, `jobs.baselland.ch` | POST offsets of 15; reported total must equal unique IDs | Configured shared Prospective translator; Umantis not authorized | `ACCEPTED_IMPLEMENTED` |

## Identity and evidence

- Zurich: `title.id` is the source publication identity. The API supplies title, organization, office, location, modification evidence and job HTML. `dateModified` is not treated as publication evidence.
- Appenzell Ausserrhoden: `sPublicationId` is the source publication identity. `deepLink` remains on `live.solique.ch`; `startDate` and `dateModified` retain separate provenance.
- Zug and Basel-Landschaft: the terminal UUID in the official detail URL is the source publication identity. Details expose `JobPosting` JSON-LD with publication and location evidence.

## Access result

All four official contracts were readable under their recorded automation-review requirement. Implementation remains acknowledgement-gated. Robots evidence did not prohibit the verified listing/detail paths. No redirect or request to an unregistered origin is permitted.

## Platform mismatch result

No material frozen/live family mismatch was found. The labels describe vendors, not identical wire formats, so source-specific configuration is retained inside two shared vendor modules rather than forcing one parser contract.

## Day-0

These sources remain required identities regardless of operational outcome. Threshold and freshness policy remain pending, and no Day-0 figure is authorized by this artifact.