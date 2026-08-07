# 05 — Deduplication and Repost Contract v0.1

## Objetivo

Separar tres magnitudes:

```text
PUBLICACIONES OBSERVADAS     n URLs / IDs
VACANTES ÚNICAS              n oportunidades económicas
POSICIONES ESTIMADAS         n personas buscadas
```

## Nivel 1 — Identidad dentro de una fuente

Merge automático por:

1. `source_id + source_native_id`;
2. requisition ID estable;
3. URL canónica normalizada;
4. redirección explícita al mismo target.

Los parámetros de tracking no forman parte de la identidad.

## Nivel 2 — Duplicado entre fuentes

### Blocking de candidatos

Sólo se comparan pares plausibles por:

- empleador normalizado;
- municipio/región compatible;
- familia de rol compatible;
- ventanas temporales solapadas o próximas.

### Score v0.1

| Señal | Peso |
|---|---:|
| Empleador | 0.25 |
| Título/rol | 0.25 |
| Localización | 0.15 |
| Tareas/texto | 0.20 |
| Pensum, contrato, inicio | 0.10 |
| Contacto/requisition | 0.05 |

```text
score >= 0.90          AUTO_MERGE
0.78 <= score < 0.90   REVIEW_QUEUE
score < 0.78           KEEP_SEPARATE
```

Los pesos son un contrato inicial, no una verdad estadística. Deben calibrarse con pares etiquetados.

## Barreras duras de no-merge

- IDs de requisición explícitos y distintos del mismo empleador.
- Localizaciones materiales distintas.
- Especialidades incompatibles.
- Fechas de inicio o pensum que prueban puestos distintos.
- Dos regiones/equipos declarados por el empleador, aunque el título sea idéntico.
- `positions_count` o descripciones que distingan campañas separadas.

Ejemplo: dos Greenkeeper de Grün Stadt Zürich con referencias y regiones distintas siguen siendo vacancies distintas.

## Fuente canónica

Orden de precedencia para campos normalizados:

```text
empleador público oficial
> empleador privado directo
> ETT que posee el anuncio
> bolsa sectorial
> plataforma de descubrimiento público
> agregador general/regional
```

Las publicaciones subordinadas no se borran; quedan vinculadas a la vacancy.

## Repost

Un repost es un nuevo episodio de la misma vacancy, no una nueva vacancy, cuando:

- reaparece el mismo requisition ID; o
- la similitud supera el gate y el intervalo de ausencia es <= 90 días; o
- el empleador confirma explícitamente la republicación.

Cada reapertura crea `VACANCY_EPISODE(n+1)` con `reappearance_gap_days`.

## Cierre

Una vacancy se considera `CLOSED_OBSERVED` cuando todos sus postings canónicos están cerrados conforme al Observation Contract. No se etiqueta `FILLED`.

## Posiciones

- Texto explícito “2 Mitarbeitende” → `positions_count=2`.
- Plural genérico o campaña continua → `NULL` + flag `MULTI_HIRE_POSSIBLE`.
- Una publicación sin dato explícito → `NULL`; para un mínimo observable puede usarse 1 en una métrica separada.

## Auditabilidad

Toda decisión de merge guarda:

- score total;
- features y pesos;
- versión del normalizador/modelo;
- método (`HARD_KEY`, `RULE_SCORE`, `MODEL_SCORE`, `HUMAN`);
- estado de revisión.
