# 04 — Point-in-Time Observation Contract v0.1

## Entidades

```text
SOURCE
  └── SOURCE_ENDPOINT
        └── POSTING
              └── POSTING_OBSERVATION  (historial inmutable)
                    │
                    ▼
                 VACANCY               (oportunidad deduplicada)
                    └── VACANCY_EPISODE
                          └── POSITION_COUNT
```

### Posting

Una aparición concreta en una fuente, identificada por `source_id + source_native_id` o, en su ausencia, por la URL canónica de esa fuente.

### Posting observation

La evidencia de que un collector vio —o no pudo ver— una publicación en un instante. Nunca se sobrescribe el historial.

### Vacancy

La oportunidad laboral subyacente que puede estar distribuida en varias fuentes.

### Position count

Número de personas buscadas. Se deja `NULL` si el anuncio no lo declara; no se convierte automáticamente en 1 salvo para métricas que indiquen expresamente “mínimo observable”.

## Estados de observación

- `ACTIVE`
- `NOT_FOUND`
- `EXPIRED_EXPLICIT`
- `REDIRECTED`
- `BLOCKED`
- `ERROR`
- `SOURCE_OUTAGE`

## Máquina de estado

```text
                 ACTIVE
                   │
       ┌───────────┼────────────┐
       │           │            │
       ▼           ▼            ▼
  NOT_FOUND     REDIRECTED   EXPIRED_EXPLICIT
       │           │            │
       │           │            └────► CLOSED_OBSERVED
       │           └────► follow canonical target
       │
       ├── source unhealthy ───► KEEP ACTIVE / UNKNOWN
       │
       └── 2 successful negative scans
           separated by >= 48 h ───► CLOSED_OBSERVED
```

`BLOCKED`, `ERROR` y `SOURCE_OUTAGE` nunca cierran una publicación.

## Timestamps

- `first_seen_at`: primera evidencia en nuestro sistema; no equivale a fecha de publicación.
- `published_at`: sólo cuando la fuente lo declara de forma interpretable.
- `last_seen_at`: última observación `ACTIVE`.
- `closed_observed_at`: momento en que se confirma la desaparición conforme al gate.
- `filled_at`: no existe salvo evidencia explícita y verificable del empleador.

## NEW

Una vacante es `NEW` cuando:

1. aparece un posting no visto antes;
2. la deduplicación no lo vincula a una vacancy activa/anterior;
3. no es un repost dentro de la ventana definida.

Un nuevo dominio o una nueva URL de la misma vacancy no genera demanda nueva.

## Integridad raw

Cada payload bruto se conserva de forma inmutable fuera de la tabla relacional y se referencia por SHA-256. Los normalizadores y clasificadores son versionados; nunca destruyen el original.

## Source health gate

Cada run registra páginas, publicaciones, errores y salud. Un descenso abrupto a cero, cambios de layout, 403/429, captcha o errores generalizados deben activar `DEGRADED/OUTAGE`, bloquear cierres y abrir una alerta técnica.

## Privacidad

Se almacenan datos del anuncio y del empleador. Los nombres, teléfonos o correos de personas de contacto se minimizan y no se utilizan para construir perfiles personales. No se recolectan CVs ni perfiles de candidatos.

## Contrato técnico

`posting_observation_v1.schema.json` es la interfaz obligatoria de cada collector. Un collector no puede promover observaciones si el payload no valida contra el schema y no aporta hash raw.
