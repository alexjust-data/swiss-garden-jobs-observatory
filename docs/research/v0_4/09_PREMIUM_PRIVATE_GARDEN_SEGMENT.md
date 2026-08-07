# 09 — Premium Private Garden Segment Contract v0.2

## 1. La distinción existe, pero no adopta una única forma

El mercado observable contiene al menos dos vías diferentes:

```text
A. PREMIUM GARDEN COMPANY
   trabajador contratado por una empresa de jardinería
   que construye o mantiene varios jardines privados de alto nivel

B. PRIVATE ESTATE DIRECT
   trabajador contratado directamente —o mediante una agencia doméstica—
   por una villa, finca, family office o residencia privada
```

No deben mezclarse. En la primera vía suele importar la cualificación técnica, la ejecución de proyectos y el trato con varios clientes. En la segunda suelen ganar peso la discreción, la confianza, los idiomas, la polivalencia, los antecedentes/referencias y la disponibilidad.

## 2. Evidencia observada

La distinción aparece algunas veces explícitamente:

- `hochwertige Privatgärten`;
- `exklusive Gartenanlagen`;
- `anspruchsvolle Kundengärten`;
- `exklusive Kundschaft`;
- `private villa` / `private estate`;
- `HNW` / `UHNW` / `family office`;
- `estate manager`, `head gardener`, `domestic couple` o `all-rounder` con responsabilidades de jardín.

Otras veces sólo se descubre enriqueciendo el anuncio con la web corporativa, su cartera de proyectos o el canal especializado que publica la vacante.

Ejemplos observados en agosto de 2026:

- Enea publica una vacante de `Vorarbeiter / Kundengärtner` para jardines exigentes y contacto directo con clientela exclusiva.
- Glowing Grass describe en su página de carrera proyectos en jardines privados de alta calidad, terrazas y espacios exteriores individualizados.
- Randstad distribuye una vacante de mantenimiento y jefatura que menciona jardines privados de alta calidad.
- Han aparecido puestos titulados `All-Rounder (Hauswart)` para una villa privada, que un buscador limitado a `Gärtner` perdería.
- Agencias de personal doméstico y family office declaran contratar gardeners, estate managers, domestic couples y gardening & maintenance para hogares privados de alto valor.

## 3. Taxonomía canónica

### `client_market_segment`

```text
PUBLIC_GREEN
PRIVATE_RESIDENTIAL_STANDARD
PRIVATE_RESIDENTIAL_PREMIUM
PRIVATE_ESTATE_DIRECT
LUXURY_HOSPITALITY_OR_RESORT
COMMERCIAL_OR_INSTITUTIONAL
MIXED
UNKNOWN
```

### `employment_channel`

```text
DIRECT_GARDEN_COMPANY
STAFFING_AGENCY
PRIVATE_HOUSEHOLD_DIRECT
PRIVATE_HOUSEHOLD_STAFFING
FAMILY_OFFICE
MARKETPLACE_GIG
PUBLIC_EMPLOYER
UNKNOWN
```

### `segment_classification_status`

```text
EXPLICIT_CONFIRMED
EMPLOYER_PROFILE_CONFIRMED
MULTI_SIGNAL_LIKELY
WEAK_SIGNAL_ONLY
UNCLASSIFIED
```

## 4. La clasificación debe separar oferta y empleador

Una empresa puede trabajar habitualmente en el segmento premium, pero no toda vacante concreta tiene por qué hacerlo. Por ello se guardan dos niveles:

```text
EMPLOYER MARKET PROFILE
    qué mercado declara atender la empresa

VACANCY WORK CONTEXT
    en qué entorno trabajará previsiblemente esa vacante
```

La vacante puede heredar el perfil del empleador, pero la herencia debe quedar marcada como tal y admitir override.

## 5. Evidencias y pesos iniciales

Los pesos de `premium_signal_taxonomy.csv` son una heurística de clasificación, no una verdad económica.

Ejemplo orientativo:

```text
private estate / private villa / HNW-UHNW       señal muy fuerte
exklusive Kundschaft / hochwertige Privatgärten señal fuerte
portfolio premium del empleador                 señal media
pools, Naturstein, Dachterrassen, Gartendesign  señales auxiliares
municipio o código postal                       no constituye evidencia
```

Umbrales provisionales:

```text
confidence >= 0.85  PREMIUM_CONFIRMED
0.65–0.85           PREMIUM_LIKELY
0.45–0.65           REVIEW_REQUIRED
< 0.45              NO_PREMIUM_CONCLUSION
```

Una mención explícita a villa/estate/HNW puede confirmar por sí sola `PRIVATE_ESTATE_DIRECT`. Para `PRIVATE_RESIDENTIAL_PREMIUM`, se prefieren dos señales independientes cuando no existe una declaración explícita.

## 6. Prohibiciones metodológicas

No se permite:

- inferir riqueza únicamente por municipio, barrio, precio inmobiliario o código postal;
- etiquetar a una persona o familia concreta como rica;
- mostrar en el mapa la dirección exacta de una residencia privada;
- convertir `Privatgarten` sin más en sinónimo de lujo;
- usar un portfolio corporativo actual como si demostrara que todas las vacantes históricas fueron premium;
- confundir una tarea puntual de jardinero particular con empleo estable de estate gardening.

## 7. Fuentes adicionales necesarias

```text
PRIVATE HOUSEHOLD STAFFING
├── Tiger Recruitment
├── Morgan & Mallet
├── Heritage Staffing
└── otras agencias verificadas

PRIVATE HOUSEHOLD MARKETPLACES
└── Homeservice24 y equivalentes

PREMIUM EMPLOYER ENRICHMENT
├── páginas de carrera
├── páginas de servicios
├── portfolio/proyectos
├── premios y prensa sectorial
└── publicaciones corporativas de contratación
```

Las redes sociales pueden aportar evidencia de segmento, pero no deben ser la única fuente canónica de una vacante cuando existe un anuncio directo.

## 8. Estadísticas específicas

- vacantes premium activas y nuevas;
- empleo en empresa premium frente a estate directo;
- proporción con EFZ/EBA;
- requisitos de idiomas, discreción, carnet, live-in y referencias;
- salarios observados, sin imputarlos cuando no se publican;
- mediana de días online y tasa de repost;
- regiones de trabajo, usando precisión municipal o regional y preservando privacidad;
- cobertura por canal especializado.

## 9. Utilidad para el candidato

El dashboard debe explicar por qué ha clasificado una oportunidad:

```text
SEGMENTO: PRIVATE_RESIDENTIAL_PREMIUM
CONFIANZA: 0.94
EVIDENCIA:
- anuncio: exklusive Kundschaft
- tareas: anspruchsvolle Kundengärten
- empleador: portfolio de diseño y mantenimiento premium
```

No debe mostrar simplemente una insignia `LUJO` sin evidencia.


## Extensión salarial premium v0.3

`premium` no implica automáticamente mejor sueldo. La app medirálo con evidencia publicada y conservará por separado:

- jardinero contratado por empresa premium;
- lead/head gardener de estate privado;
- household staffing;
- alojamiento, vehículo, comidas, confidencialidad/on-call y disponibilidad de fin de semana;
- importe publicado frente a expresión cualitativa `competitive`.

Una localización rica o la palabra `luxury` no permiten imputar una cifra. Los beneficios en especie no se convierten a CHF sin valoración explícita.
