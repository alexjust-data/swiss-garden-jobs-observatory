# 08 — Implementation Handoff to Codex v0.2

## Decisión de herramienta

Work ha cerrado la semántica, taxonomías, evidencia premium, fechas, geolocalización, privacidad y UX. Codex debe implementar collectors, normalización, geocoder, base de datos, API, mapa y tests.

## Arquitectura

```text
SOURCE REGISTRY
      │
      ▼
COLLECTOR ORCHESTRATOR
      │
      ├── platform adapters
      ├── source-specific adapters
      └── private-household channels
      │
      ▼
RAW OBJECT STORE + SHA-256
      │
      ▼
POSTING OBSERVATIONS (append-only)
      │
      ▼
NORMALIZATION
      │
      ├── published-date parser
      ├── employer resolver
      ├── BFS / geo.admin geocoder
      ├── role/access classifier
      ├── premium-segment evidence engine
      └── requirements parser
      │
      ▼
DEDUP + REVIEW QUEUES
      │
      ├── duplicate review
      ├── segment review
      └── geocoding review
      │
      ▼
VACANCIES + EPISODES
      │
      ▼
DAILY MARKET STATE
      │
      ├── API
      ├── MapLibre dashboard
      └── alerts
```

## Gates

### GATE-001 — Repository baseline

- Python typing/lint/tests;
- PostgreSQL migrations;
- object storage abstraction;
- deterministic config and secrets handling.

### GATE-002 — Reference data

- importar BFS snapshot;
- validar 1.374 municipios germanófonos del snapshot usado;
- cargar source registry y taxonomías;
- cargar reglas de segmento premium.

### GATE-003 — One direct source end-to-end

Winterthur:

```text
list → details → raw → observation → dates → geocode → vacancy → API
```

### GATE-004 — Date semantics

Tests obligatorios:

- fecha exacta estructurada;
- fecha sólo día;
- `vor 3 Tagen` resuelto contra `observed_at`;
- fecha ausente;
- agregador con fecha diferente de la fuente canónica;
- `first_seen_at` nunca sobrescribe `source_published_at`.

### GATE-005 — Geospatial pipeline

- resolver BFS code y municipio;
- geo.admin SearchServer como adaptador geocoder;
- cache e idempotencia;
- precisión y confianza;
- cola de ambigüedad;
- generalización de villas al centroide municipal;
- nunca enviar dirección privada exacta al frontend.

### GATE-006 — Platform reuse

- REXX;
- Umantis;
- SuccessFactors;
- Solique;
- Prospective.

### GATE-007 — Source health/closure safety

- portal devuelve cero por fallo;
- 403/429;
- cambio de layout;
- redirect;
- dos negativos sanos separados por 48 h;
- outage no cierra postings.

### GATE-008 — Dedup

- mismo anuncio oficial + agregador;
- títulos iguales pero IDs/regiones distintos;
- repost;
- campaña multi-plaza;
- plantilla genérica de ETT.

### GATE-009 — Premium segment

Fixtures mínimos:

- Enea: `exklusive Kundschaft`;
- Randstad: `hochwertige Privatgärten`;
- Glowing Grass: perfil de empleador premium;
- villa privada: `PRIVATE_ESTATE_DIRECT`;
- Homeservice24: privado estándar, no premium por defecto;
- municipio rico sin otra evidencia: no clasificar premium.

La respuesta debe incluir evidencia, método y confianza.

### GATE-010 — Map dashboard

- MapLibre GL JS;
- markers, clustering y popup;
- tabla y mapa sincronizados;
- filtros temporales y geográficos;
- indicador de precisión;
- privacidad de estate roles;
- tests de API para GeoJSON.

### GATE-011 — Day-0

Sólo emitir cifra de mercado cuando:

- fuentes P0 seleccionadas completan el run;
- cobertura supera el umbral acordado;
- review queues están bajo control;
- cifras distinguen postings/vacancies/positions;
- se muestra cobertura de fecha y geocodificación.

### GATE-012 — Daily operation

- scheduler;
- idempotencia;
- alertas;
- backups;
- observabilidad;
- dashboard con quality banner.

## Orden recomendado

1. BFS + registry + migrations.
2. Winterthur end-to-end, incluyendo fechas y GeoJSON.
3. mapa de ofertas con datos seed.
4. ciudades/cantones y familias ATS.
5. Enea + un empleador premium + un private household channel.
6. g’plus/publicjobs/Gemeindestellen.
7. ETT y agregadores.

## Definition of Done del MVP

- 30 días de historial PIT;
- fecha publicada y primera observación visibles por separado;
- mapa municipal interactivo;
- privacidad de residencias privadas;
- dedup auditable;
- clasificación premium explicable;
- filtros públicos, privados, premium y estate;
- export CSV/API/GeoJSON;
- cobertura y calidad visibles;
- alertas de nuevas vacantes relevantes.


## Gate salarial v0.3

```text
GATE-SAL-001  compensation_observation migration + constraints
GATE-SAL-002  extraction fixtures: fixed/min/max/range/qualitative/missing
GATE-SAL-003  12/13-pay and pensum normalization guardrails
GATE-SAL-004  GAV/public-scale reference versioning and applicability state
GATE-SAL-005  salary dashboard with coverage + n + provenance
GATE-SAL-006  benefits/total-compensation extraction
```

Acceptance criteria:

- no benchmark/GAV value written into advertised salary fields;
- no annualisation with unknown payments or workload basis;
- exact raw salary text retained;
- same posting may accumulate salary observations over time without overwriting history;
- salary updates produce a change event;
- slices with `n < 5` are marked low-sample or suppressed;
- public/private-estate compensation components remain separately queryable.


## Required UI vertical slice — job detail and provenance

The production implementation must expose `GET /postings/{posting_id}` and render the same detail drawer from both map markers and table rows. Persist `canonical_url`, `source_url`, `canonical_url_status`, source name/type, publication timestamps and observed state. Do not silently redirect discovery URLs or label them as canonical adverts. Add end-to-end tests for: direct canonical URL, portal-level URL pending, expired URL, no URL, and privacy-generalized private estate location. See `13_JOB_DETAIL_AND_SOURCE_LINK_CONTRACT.md`.
