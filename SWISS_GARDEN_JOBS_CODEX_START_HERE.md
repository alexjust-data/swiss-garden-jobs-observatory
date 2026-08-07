# Swiss Garden Jobs — inicio exacto con Codex

## Preparación manual

1. Crear un repositorio privado en GitHub llamado `swiss-garden-jobs-observatory`.
2. Descomprimir `swiss_garden_jobs_research_v0_4.zip`.
3. Copiar su contenido a `docs/research/v0_4/` dentro del repositorio.
4. Copiar `AGENTS_SWISS_GARDEN_JOBS.md` a la raíz y renombrarlo `AGENTS.md`.
5. Hacer el commit inicial: `docs: add frozen research package v0.4`.
6. Conectar el repositorio a Codex y crear su entorno.

## Primera tarea para Codex — copiar literalmente

```text
Trabaja exclusivamente en GATE-001 — Repository baseline.

Antes de programar, lee AGENTS.md y todos los documentos que éste declara como source of truth. No implementes collectors reales, deduplicación, dashboard productivo ni estadísticas todavía.

Objetivo:
Crear el baseline ejecutable del repositorio Swiss Garden Jobs Observatory como monolito modular, siguiendo la decisión técnica de AGENTS.md.

Requisitos:

1. Estructura inicial clara para:
   - configuración Django;
   - dominio de sources, postings, observations, vacancies y reference data;
   - collectors futuros;
   - API futura;
   - templates/static futuros;
   - tests;
   - infraestructura local.

2. PostgreSQL local mediante Docker Compose.

3. Gestión de configuración y secretos:
   - `.env.example` sin credenciales reales;
   - variables validadas;
   - valores de desarrollo seguros;
   - ninguna clave comprometida.

4. Calidad:
   - formatter/linter;
   - type checking razonable;
   - pytest;
   - pre-commit opcional pero reproducible;
   - GitHub Actions para lint, typing y tests.

5. Base de datos:
   - sólo modelos/migraciones mínimos necesarios para demostrar que la infraestructura funciona;
   - no anticipar todavía todo `schema.sql`;
   - incluir una tabla o modelo de health/version si ayuda a validar migraciones.

6. Interfaces:
   - abstracción mínima de raw object storage con implementación filesystem local;
   - cálculo SHA-256 probado;
   - no acceso a fuentes externas en esta gate.

7. Developer experience:
   - README de arranque local;
   - comandos equivalentes a `make setup`, `make dev`, `make lint`, `make typecheck`, `make test` y `make migrate`;
   - health endpoint mínimo;
   - una página mínima que confirme que la aplicación funciona, sin copiar todavía el prototipo.

8. Tests de aceptación:
   - configuración carga correctamente;
   - migraciones se aplican a una base limpia;
   - health endpoint responde;
   - raw filesystem store escribe, lee y verifica SHA-256;
   - CI ejecuta todo lo anterior.

Restricciones:
- Una sola PR para GATE-001.
- No modificar `docs/research/v0_4/`.
- No añadir microservicios, Celery, Kafka, Elasticsearch, PostGIS ni una SPA.
- No inventar datos de ofertas.
- No hacer scraping.

Entrega:
- crea una rama `gate-001-repository-baseline`;
- implementa y ejecuta todos los tests;
- abre una PR draft;
- en la descripción incluye comandos ejecutados, resultados, decisiones arquitectónicas, riesgos y lo que queda expresamente fuera de alcance.
```

## No avanzar todavía a GATE-002

Antes de importar los 1.374 municipios y el registro de fuentes, revisar la PR de GATE-001 y confirmar:

- arranque reproducible;
- base limpia migrable;
- tests verdes;
- estructura comprensible;
- ningún sobre-diseño;
- documentos v0.4 intactos.

## Secuencia posterior

```text
GATE-001  baseline del repositorio
    ↓
GATE-002  importar BFS, source registry y taxonomías
    ↓
GATE-003  Winterthur end-to-end con fixture y fuente real controlada
    ↓
GATE-004  semántica de fechas
    ↓
GATE-005  geocodificación y privacidad
    ↓
GATE-SAL  salarios y compensación
    ↓
GATE-010  mapa + tabla + ficha + enlace original
    ↓
30 días de historial PIT
    ↓
MVP defendible
```
