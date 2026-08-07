# 02 — Master Source Registry v0.1

## Jerarquía

```text
P0  OFFICIAL REFERENCE / DIRECT PUBLIC
    BFS · Job-Room · jobs.admin.ch · cantones · municipios

P1  SECTOR / PUBLIC DISCOVERY / AGENCIES
    g’plus · JardinSuisse · publicjobs · Gemeindestellen · ETT

P2  GENERAL / REGIONAL / SYNDICATED
    JobCloud · Indeed · LinkedIn · redes regionales · Jobchannel
```

Fuentes registradas: **61**.

| Familia | Fuentes registradas |
| --- | --- |
| GENERAL_JOB_BOARD | 4 |
| JOBCHANNEL_FAMILY | 1 |
| OFFICIAL_CANTON | 22 |
| OFFICIAL_FEDERAL | 1 |
| OFFICIAL_MUNICIPAL | 9 |
| OFFICIAL_NATIONAL | 2 |
| OFFICIAL_REFERENCE | 1 |
| OFFICIAL_STATISTICS | 1 |
| PUBLIC_JOB_DISCOVERY | 2 |
| REGIONAL_JOB_BOARD | 7 |
| SECTOR_ASSOCIATION | 1 |
| SECTOR_JOB_BOARD | 1 |
| STAFFING_AGENCY | 9 |

## Canonicidad

```text
OFFICIAL PUBLIC EMPLOYER
        ↓
DIRECT PRIVATE EMPLOYER
        ↓
OFFICIAL/SECTOR BOARD OR AGENCY ORIGINAL
        ↓
PUBLIC DISCOVERY PLATFORM
        ↓
GENERAL/REGIONAL AGGREGATOR
```

La canonicidad decide qué versión domina los campos normalizados, pero **no elimina** las publicaciones de otras fuentes: son evidencia de distribución y permiten medir sindicación.

## Source family y platform family

Dos dominios pueden formar parte de la misma red. Por eso cada fuente guarda:

- `source_id`: dominio/end-point observado;
- `source_family`: familia económica de distribución;
- `platform_family`: ATS o infraestructura técnica compartida.

Ejemplos: JobCloud; redes regionales; Jobchannel; Solique; Prospective; Umantis; SuccessFactors; REXX. Esta separación evita contar una misma campaña como varias señales independientes y permite reutilizar collectors por plataforma.

## Job-Room

Job-Room es una fuente institucional P0. La interfaz API documentada se registra como interfaz de notificación/gestión, no como feed público de lectura masiva hasta que su alcance se confirme. La implementación debe investigar acceso oficial, partnership o feed antes de cualquier automatización.

## Gate legal/técnico por fuente

```text
DISCOVERED
    ↓
OFFICIALITY VERIFIED
    ↓
TERMS / ROBOTS / API / FEED REVIEWED
    ↓
COLLECTION METHOD AUTHORIZED
    ↓
CONTRACT TESTS PASS
    ↓
PRODUCTION ACTIVE
```

`source_registry.csv` no afirma que el scraping esté autorizado. `automation_status` y `legal_review_status` impiden esa inferencia.

## Estrategia de cobertura

1. Implementar primero BFS y portales oficiales de alto rendimiento.
2. Reutilizar colectores por ATS.
3. Usar publicjobs/Gemeindestellen/g’plus como radares y para descubrir fuentes canónicas.
4. Añadir ETT para demanda temporal y campañas difíciles de cubrir.
5. Incorporar agregadores generales al final, cuando la deduplicación ya esté calibrada.
