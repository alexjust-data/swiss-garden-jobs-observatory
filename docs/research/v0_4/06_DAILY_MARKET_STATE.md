# 06 — Daily Market State v0.1

## Grano

Una fila por:

```text
state_date
× geography_type/geography_id
× role_family
× employment_relationship
```

Geografías: Suiza alemana, cantón, municipio, región funcional y radio de desplazamiento cuando exista geocodificación.

## Métricas núcleo

| Métrica | Definición |
|---|---|
| `active_postings` | Publicaciones activas observadas |
| `active_unique_vacancies` | Vacantes deduplicadas activas |
| `estimated_positions` | Suma de positions_count conocido; mostrar cobertura |
| `new_vacancies` | Vacantes realmente nuevas, no nuevas URLs |
| `disappeared_vacancies` | Cierres observados confirmados |
| `reappeared_vacancies` | Nuevos episodios/reposts |
| `unique_employers` | Empleadores normalizados activos |
| `unique_agencies` | ETT activas |
| `public_direct_share` | Public direct / active vacancies |
| `agency_share` | Agency / active vacancies |
| `entry_accessible_share` | A0–A2 / vacancies clasificadas |
| `apprenticeship_share` | Aprendizajes / vacancies |
| `median_days_online` | Mediana de duración del episodio activo |
| `repost_rate` | Vacancies con episodio >1 / vacancies observables |

## Métricas de calidad obligatorias

- `source_coverage_ratio`
- `collector_success_ratio`
- fuentes degradadas/fallidas
- postings sin empleador normalizado
- vacancies en review queue
- localizaciones sin BFS code
- roles `TO_CLASSIFY`
- cobertura de `published_at`, salario y positions_count

Ningún dashboard debe mostrar una variación diaria sin mostrar la calidad de cobertura del mismo día.

## Observed Hiring Pressure

Índice de actividad observable que puede usar, tras calibración:

```text
z(new_vacancies)
+ z(active_unique_vacancies)
+ z(repost_rate)
+ z(agency_share)
+ z(immediate_start_share)
+ z(multi_position_signal)
```

No se denomina “escasez”.

## Labour Scarcity Evidence

Capa separada que exige combinar anuncios con datos oficiales sobre desempleados/demandantes, persistencia, salarios, requisitos y estacionalidad. Su estado inicial es `NOT_COMPUTED`.

## Comparabilidad

- Los contadores de portales no se usan como verdad de mercado.
- Las series se recalculan con una versión de dedup registrada.
- Cambios de cobertura o taxonomía generan una nueva `metric_version`.
- Aprendizajes y prácticas se separan del empleo ordinario.


## Extensión salarial v0.3

Las métricas salariales sólo usan observaciones con procedencia y normalización válida:

| Métrica | Definición |
|---|---|
| `salary_disclosure_coverage_ratio` | Vacantes con cualquier mención salarial / vacantes observables |
| `numeric_salary_coverage_ratio` | Vacantes con importe numérico publicado / vacantes observables |
| `annual_fte_normalization_coverage_ratio` | Importes convertibles con seguridad a bruto anual 100 % |
| `advertised_salary_sample_n` | N usado en percentiles/mediana publicados |
| `advertised_annual_gross_fte_p25/median/p75` | Distribución de salario publicado normalizado; nunca GAV/benchmark |
| `salary_above_verified_floor_share` | Sólo cuando la aplicabilidad del mínimo está verificada |
| `public_salary_range_coverage_ratio` | Empleo público con banda exacta o clase resoluble |
| `benefits_disclosure_ratio` | Vacantes con algún componente de compensación declarado |

Todos los gráficos muestran `n`, cobertura y tipo de evidencia. `NOT_DISCLOSED` no se sustituye por una estimación.
