# Swiss Garden Jobs Observatory — Research & Engineering Package v0.4.0

**Fecha de corte:** 2026-08-07  
**Snapshot geográfico BFS:** 2026-01-01  
**Idioma de trabajo:** castellano; términos laborales conservados en alemán.

## Objetivo

Construir un observatorio point-in-time de ofertas de jardinería y mantenimiento verde en la Suiza alemana, preparado para evolucionar hacia una aplicación con seguimiento diario, deduplicación, estadísticas, alertas y análisis de accesibilidad laboral.

## Resultado de esta iteración

```text
W1  PUBLIC EMPLOYER UNIVERSE       CLOSED v0.1
W2  MASTER SOURCE REGISTRY         CLOSED v0.1
W3  OBSERVATION MODEL              CLOSED v0.4
    DEDUP / REPOST CONTRACT        CLOSED v0.1
    DAILY MARKET STATE             CLOSED v0.4
    SALARY / COMPENSATION           CLOSED v0.4
    CODEX HANDOFF                  READY v0.1

FULL DAY-0 UNIQUE VACANCY COUNT    NOT CLAIMED
PRODUCTION COLLECTORS              NOT IMPLEMENTED
AUTOMATION LEGAL REVIEW            REQUIRED PER SOURCE
```

La palabra **completo** tiene aquí una definición controlada:

- El universo administrativo está enumerado de forma completa: **1 Confederación + 22 ámbitos cantonales + 1,374 municipios germanófonos = 1,397 registros públicos**.
- Los **22 portales cantonales** están registrados y verificados a nivel de directorio oficial.
- Las **127 ciudades estadísticas germanófonas** forman la cola P0 de auditoría municipal.
- No se finge que las 1,374 URLs municipales individuales estén verificadas: muchos municipios comparten ATS, publican mediante el cantón, Job-Room o plataformas públicas. Esa labor queda explícita en `city_portal_audit_queue_127.csv` y en los estados `DISCOVERY_PENDING`.
- El snapshot de ofertas actuales contiene **20 observaciones seed verificadas**, pero **no es un censo exhaustivo ni una cifra de vacantes únicas**.

## Archivos principales

| Archivo | Función |
|---|---|
| `01_PUBLIC_EMPLOYER_UNIVERSE.md` | Definición oficial de Suiza alemana y universo público |
| `public_employer_universe_1397.csv` | Confederación, cantones y municipios auditables |
| `city_portal_audit_queue_127.csv` | Cola prioritaria de ciudades estadísticas |
| `02_MASTER_SOURCE_REGISTRY.md` | Jerarquía de fuentes, canonicidad y acceso |
| `source_registry.csv` | Registro operativo de fuentes |
| `03_ROLE_AND_SEARCH_TAXONOMY.md` | Puestos visibles y títulos públicos ocultos |
| `role_search_taxonomy.csv` | Diccionario de términos para búsqueda/clasificación |
| `04_OBSERVATION_CONTRACT.md` | Contrato point-in-time y estado de publicaciones |
| `posting_observation_v1.schema.json` | Contrato técnico JSON |
| `05_DEDUPLICATION_REPOST_CONTRACT.md` | Posting→Vacancy→Position y episodios/reposts |
| `06_DAILY_MARKET_STATE.md` | Estadísticas diarias y calidad de cobertura |
| `07_DASHBOARD_PRODUCT_SPEC.md` | Producto, vistas y filtros |
| `dashboard_prototype.html` | Prototipo navegable con el seed actual |
| `08_IMPLEMENTATION_HANDOFF_CODEX.md` | Arquitectura y gates de implementación |
| `schema.sql` | Esquema PostgreSQL base |
| `schema_v0_3_salary_patch.sql` | Extensión relacional de salario/compensación |
| `11_SALARY_AND_TOTAL_COMPENSATION_CONTRACT.md` | Contrato salarial y reglas de normalización |
| `12_SALARY_MARKET_READOUT_2026_08_07.md` | Lectura humana de salarios, mínimos y anuncios observados |
| `salary_reference_2026.csv` | GAV, benchmark y ejemplos salariales versionados |
| `salary_evidence_seed_2026-08-07.csv` | Evidencia salarial observada, no exhaustiva |
| `current_public_green_seed_snapshot_2026-08-07.csv` | Muestra actual pública, no exhaustiva |
| `coverage_matrix.csv` | Qué está cerrado y qué sigue pendiente |
| `SOURCES.md` | Fuentes y provenance |

## Principios no negociables

1. `JOB_POSTING != JOB_VACANCY != POSITIONS_COUNT`.
2. Una desaparición observada no demuestra que el puesto se haya cubierto.
3. Una caída de una fuente no cierra sus publicaciones.
4. La fuente canónica prevalece sobre el agregador, pero ambas observaciones se conservan.
5. Las métricas de contratación observable no se presentan como prueba automática de escasez laboral.
6. Todo colector requiere revisión de términos, robots, feed/API o autorización antes de automatizarse.

## Ruta de ejecución

```text
ESTE PAQUETE
    │
    ▼
CREAR REPOSITORIO + CI
    │
    ▼
INGESTA BFS + SOURCE REGISTRY
    │
    ▼
COLECTORES P0 OFICIALES
    │
    ▼
RAW OBSERVATIONS INMUTABLES
    │
    ▼
NORMALIZACIÓN + DEDUP
    │
    ▼
DAY-0 DEDUPLICADO
    │
    ▼
ESTADO DIARIO + DASHBOARD + ALERTAS
```


## Corrección v0.4 — salarios

El salario se modela como evidencia temporal y trazable. Se separan estrictamente el importe publicado en una oferta, el mínimo GAV/escala pública potencialmente aplicable y el benchmark estadístico. El dashboard muestra `No publicado` cuando corresponde y no imputa un sueldo estimado como si fuera contractual.

- `13_JOB_DETAIL_AND_SOURCE_LINK_CONTRACT.md`: full job drawer and source-link provenance rules.
