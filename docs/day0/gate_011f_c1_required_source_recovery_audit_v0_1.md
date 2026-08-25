# GATE-011F-C1 required-source recovery audit v0.1

Baseline: `99e39312535f33554a973110cba196c253628945`.

Contract-only commit: `0f3548065c4b957eec75b40897f70c6b2059d2d0`.

Evaluation date: 2026-08-25. The nine-candidate set and transition rules were
frozen before the detailed compatibility measurements. No outcome was selected
to close the four-Source Day-0 gap.

## Result

No candidate satisfies every frozen recovery condition. This gate therefore
authorizes no adapter, endpoint, reference-data disposition or policy change.
The required universe remains 29, the implemented ceiling remains 20/29 and
the Day-0 minimum remains 24/29.

| Source | Current bounded official evidence | Access, identity and exhaustion result | C1 outcome | Implementation |
|---|---|---|---|---|
| `SRC-OFF-CANTON-AI` | `www.ai.ch/robots.txt` permits anonymous public access. The ordinary Plone page returned HTTP 200 (`fb549657a8d824b1d531c8d678f288ec50b5cb0a2f1f1019a619bb70c0c2638a`). The apprenticeship page returned HTTP 200 (`6765f8ba6d661bb0524a732c30cc0e96b7b8ea9627af2de9bb3d18d39f32370b`) and still presents profession/year availability, including two Kaufmann/Kauffrau places for 2027, on a standing page. | Public readability improved, but the ordinary page does not expose an independently exhaustible server-side publication set and the apprenticeship surface still has no native opportunity identity separating its profession/cohort states. A count on a standing page is not a vacancy-level source identity. | `STILL_BLOCKED_SAME_REASON` | NO |
| `SRC-OFF-CANTON-AG` | The official jobs hub still routes its complete component through `www.ag.ch`; current robots SHA-256 `4b1eec006887d2c9f7555f3f20a82590b2d764163737cb72964c630573c6f02f` explicitly disallows `/io/*`. `jobs.ag.ch/robots.txt` allows `/` and search discovery finds UUID detail pages, but its root is empty and `/offene-stellen` redirects to a 403 S3 direct-link response. | Individual indexed details do not prove a complete official universe. The only observed complete feed remains prohibited and the alternate portal supplies no deterministic total, pagination or explicit zero contract. | `STILL_BLOCKED_SAME_REASON` | NO |
| `SRC-OFF-CANTON-BE` | The canton still defines KSML and SteZe as distinct mandatory teacher surfaces. Both public shells returned HTTP 200, while both `www.ksml.apps.be.ch/robots.txt` and `www.steze.apps.be.ch/robots.txt` returned HTTP 403. KSML search evidence contains current rows and SteZe remains the official short-substitution channel. | Ordinary Prospective cannot represent `FULL_SOURCE` alone. Applicable automation access for both mandatory teaching origins remains unproven, and their combined inventories cannot be exhaustively acquired under the frozen policy. | `STILL_BLOCKED_SAME_REASON` | NO |
| `SRC-OFF-CANTON-FR` | `jobs.fr.ch` returned HTTP 200 (`0602641f03f5c7427aa622b2166760337e5d98d52c9c5ede52787e641f34e4ec`). The official page still says migration is in progress, limits the new SuccessFactors surface to SPE, Police and SITel, and links all other jobs plus teaching separately. | The SuccessFactors, legacy and education surfaces still lack authoritative common identity and complete exhaustion. | `STILL_BLOCKED_SAME_REASON` | NO |
| `SRC-OFF-CANTON-JU` | The official four-category hub returned HTTP 200 (`7a042535b8c9186ef3a0237ac1b7daa36d5f8ac133a1ab51499c3bbd2421797b`). The teaching page returned HTTP 200 (`a5a8df8204885c1e227f3e4a6ed0fc4ccdf90debfc8b5a9939bf6248015626a3`) but contains contacts and calendars only, while official Journal publications demonstrate that teaching vacancies can exist. Magistracy has an explicit zero state (`f00b5b9d8e83c32cd34e1f6e7ea28284eb95cdb0bd2a7cd5b75968acb52bdbc7`). `Autres` returned an empty page without an explicit zero statement (`25a0cbde2b6710c8c0130e81121f27140c69cfe7134bdf59dc884ac7d05c5688`). | Teaching still has neither an exhaustive list nor an explicit empty contract. `Autres` still does not identify the employer boundary or an explicit zero state. Administration plus magistracy is not the complete Source. | `STILL_BLOCKED_SAME_REASON` | NO |
| `SRC-OFF-CANTON-NW` | The official apprenticeship page returned HTTP 200 (`65f37ab01c77f1b249fd02720b782695054b09b5b7e999986155f2517817362f`) and continues to present availability by profession/year. The practicum page returned HTTP 200 (`6514066e8f43be7ba62b408b0b1f09b585c644028dac848ea39fdd2a436399e6`) and continues to combine multiple routes behind standing program material. | The prior `NW-1616` ambiguity remains: no source-native identity distinguishes simultaneous cohort/route opportunities. Deriving an ID from title/year would fabricate authority. | `STILL_BLOCKED_SAME_REASON` | NO |
| `SRC-OFF-CANTON-OW` | The main canton `robots.txt` is empty, but the mandatory Zentraljob tenant still returns `User-agent: * / Disallow: /`. | The prohibited vacancy origin was not requested. No independently official complete alternate origin was found. | `STILL_BLOCKED_SAME_REASON` | NO |
| `SRC-OFF-CANTON-UR` | `www.ur.ch/robots.txt` eventually returned HTTP 200 with an empty body after 15.12 seconds. The current official listing is indexed with eight rows and an explicit `1 bis 8 von 8` total, but a direct governed listing GET timed out after 20 seconds. A previously indexed detail was already HTTP 404. | Identity and total shape remain promising, but mandatory listing/detail delivery is not reproducible from the execution environment. The two required consecutive healthy `FULL_SOURCE` runs cannot begin. | `STILL_BLOCKED_SAME_REASON` | NO |
| `SRC-OFF-CANTON-VS` | The official jobs landing returned HTTP 200 (`0776af0eb1d3d517b4bad7644c92f6882f03cb05b2af06347a5144ae9bffa2a3`) and still directs primary/orientation teaching to the official bulletin and apprenticeships/stages to separate channels. | Ownership, bilingual identity and common exhaustion across administration, teaching and training remain unresolved. | `STILL_BLOCKED_SAME_REASON` | NO |

## Access decisions

- No request was made to Aargau's prohibited `/io/*` path.
- No request was made to Obwalden's prohibited Zentraljob vacancy paths.
- Bern's two mandatory shells were inspected only at their public entry pages;
  their 403 robots responses do not authorize deeper automated acquisition.
- No authentication, session reuse, private token, alternate-agent evasion,
  browser bypass, mirror, aggregator or Job-Room substitution was used.
- Search discovery was used only to locate or corroborate official pages. It was
  not treated as completeness evidence.

## Consequence

All nine historical human-governed blocked dispositions remain immutable and
current. No Source receives a synthetic CollectionRun, no blocked row is
rewritten, and no threshold is relaxed. The observed implementation ratio
therefore remains `20/29 = 68.97%` and the structural authorization gap remains
at least four additional required Sources.

This is an external-evidence boundary, not unfinished adapter engineering. A
future recovery gate should re-open an individual Source only when its official
platform, access policy, identity or surface topology materially changes.

## Mutation and network accounting

- real operational database writes: `0`;
- canonical RAW writes: `0`;
- Source collector runs: `0`;
- prohibited-path requests: `0`;
- adapter changes: `0`;
- reference-data changes: `0`;
- frozen research changes: `0`.

