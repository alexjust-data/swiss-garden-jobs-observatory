# 07 — Dashboard Product Specification v0.1

## Página 1 — Estado del mercado

```text
ACTIVAS ÚNICAS       NUEVAS 24H       REAPARECIDAS       COBERTURA
      —                   —                 —                —

[serie diaria]                   [mapa por municipio/cantón]
```

Los guiones permanecen hasta que exista un Day-0 deduplicado y cobertura suficiente.

## Página 2 — Empleo público

Filtros:

- Bund / Kanton / Stadt / Gemeinde / institución pública;
- Stadtgrün, Werkhof, Friedhof, Sportanlagen, Botánico, Arealpflege;
- empleo directo frente a contratista público;
- rol, nivel de acceso, EFZ/EBA, alemán, carnet, pensum;
- distancia desde una ubicación del usuario.

## Página 3 — Accesibilidad

- A0–A7;
- Quereinsteiger;
- título no obligatorio;
- experiencia equivalente;
- alemán requerido;
- B/BE/C1;
- inmediata / fecha futura;
- aprendizaje separado.

## Página 4 — Persistencia y reposts

- mediana de días online;
- vacantes con episodios múltiples;
- empleadores con demanda recurrente;
- regiones con uso intensivo de ETT.

## Página 5 — Fuentes y calidad

- collectors sanos/degradados;
- cobertura esperada/observada;
- cambios de layout;
- cola de dedup;
- campos sin clasificar;
- fecha de última observación por fuente.

## Página 6 — Ofertas

Tabla trazable hasta postings y fuente canónica. Cada vacancy muestra:

```text
VACANCY
├── canonical public/direct posting
├── syndicated postings
├── first/last seen
├── episode/repost count
├── role/access classification
└── evidence and confidence
```

## Prototipo incluido

`dashboard_prototype.html` usa las 20 observaciones seed para validar navegación y filtros. Sus contadores describen únicamente el seed, no el mercado suizo.


## Página 7 — Salario y compensación

La vista salarial tendrá tres carriles que nunca se suman silenciosamente:

```text
SALARIO PUBLICADO     GAV / ESCALA PÚBLICA      BENCHMARK DE MERCADO
oferta concreta       referencia aplicable      comparación estadística
```

Filtros:

- con/sin salario numérico;
- CHF/hora, CHF/mes, CHF/año;
- mínimo/máximo anual 100 % cuando la normalización sea válida;
- público, privado, premium, private estate, ETT;
- EFZ/EBA/ayudante/dirección;
- GAV potencialmente aplicable/verificado;
- beneficios: vivienda, vehículo, bonus, 13.º, pensión, Winterdienst.

La tabla de ofertas incorpora una columna salarial con origen, base de pensum y confianza. El mapa puede colorear por rango salarial únicamente para observaciones comparables; los anuncios sin cifra conservan un marcador neutral.


## Job detail interaction — v0.4 patch

Every map marker and result row opens a complete side drawer. The marker popup must contain: title, employer, municipality, source publication date, pensum, salary, observed state, a `View full details` action and a correctly-labelled external source action. Link labels depend on canonical evidence and may be `original advert`, `source where published`, `observed source`, or `expired link`. See `13_JOB_DETAIL_AND_SOURCE_LINK_CONTRACT.md`.
