# AGENTS.md — Swiss Garden Jobs Observatory

## Mission

Implementar un observatorio point-in-time de ofertas de jardinería y mantenimiento verde en la Suiza alemana, con fuentes trazables, historial inmutable, deduplicación auditable, salarios, geografía, mapa, enlaces originales y protección de residencias privadas.

## Source of truth

Leer antes de modificar código, en este orden:

1. `docs/research/v0_4/00_README.md`
2. `docs/research/v0_4/04_OBSERVATION_CONTRACT.md`
3. `docs/research/v0_4/05_DEDUPLICATION_REPOST_CONTRACT.md`
4. `docs/research/v0_4/10_DATES_AND_GEOSPATIAL_CONTRACT.md`
5. `docs/research/v0_4/11_SALARY_AND_TOTAL_COMPENSATION_CONTRACT.md`
6. `docs/research/v0_4/13_JOB_DETAIL_AND_SOURCE_LINK_CONTRACT.md`
7. `docs/research/v0_4/08_IMPLEMENTATION_HANDOFF_CODEX.md`
8. JSON Schemas y SQL incluidos en la misma carpeta.

En caso de contradicción, detener la implementación afectada, documentar el conflicto y no inventar semántica.

## Architectural decision for the MVP

Construir un monolito modular:

- Python, versión estable fijada en el proyecto.
- Django + Django REST Framework.
- PostgreSQL.
- Django templates + HTMX/JavaScript ligero para el MVP.
- MapLibre GL JS para el mapa.
- `httpx` y parser HTML para collectors; navegador automatizado sólo cuando sea necesario.
- Almacenamiento raw mediante una interfaz: filesystem local en desarrollo y backend compatible con object storage más adelante.
- Comandos de gestión idempotentes para ingesta y ejecución diaria.
- Sin microservicios, Celery, Kafka, Elasticsearch ni PostGIS en GATE-001 salvo justificación y aprobación documentada.

## Non-negotiable domain rules

1. `JOB_POSTING != JOB_VACANCY != POSITIONS_COUNT`.
2. `source_published_at != first_seen_at`.
3. Una publicación desaparecida no demuestra que la vacante se haya cubierto.
4. Un fallo, 403, 429 o cambio de layout no puede cerrar publicaciones.
5. Conservar raw artefact + SHA-256 y observaciones append-only.
6. No sobrescribir evidencia histórica; registrar cambios como nuevas observaciones/eventos.
7. No introducir benchmarks, GAV o estimaciones en campos de salario anunciado.
8. No anualizar cuando faltan la base de jornada o el número de pagas.
9. Una localidad rica no demuestra que una oferta sea premium.
10. Direcciones de villas y hogares privados nunca llegan exactamente al frontend.
11. No llamar “anuncio original” a una página de búsqueda, agregador o portal genérico.
12. No automatizar una fuente hasta registrar su método permitido, términos/robots, feed/API o revisión de acceso.

## Engineering rules

- Una gate por rama y una PR pequeña.
- Toda nueva semántica exige tests.
- Type hints en código de dominio.
- Migraciones revisables y reversibles cuando sea razonable.
- Fixtures deterministas; ninguna prueba depende obligatoriamente de Internet.
- No datos sintéticos silenciosos en producción.
- Lint, typing y tests deben pasar antes de abrir PR.
- Añadir documentación de ejecución local y decisiones arquitectónicas.
- No modificar los artefactos de `docs/research/v0_4/`; son evidencia congelada.

## Expected developer interface

El repositorio debe converger hacia comandos equivalentes a:

```bash
make setup
make dev
make lint
make typecheck
make test
make migrate
make import-reference-data
```

Los nombres pueden ajustarse, pero la experiencia debe ser reproducible y documentada.

## Delivery format

Cada tarea debe terminar con:

- resumen de cambios;
- archivos principales modificados;
- migraciones creadas;
- tests ejecutados y resultado;
- riesgos o decisiones pendientes;
- enlace o contenido de la PR.
