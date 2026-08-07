# 10 — Dates and Geospatial Contract v0.2

## 1. Las fechas no son intercambiables

La aplicación debe mostrar por separado:

```text
source_published_at
    fecha declarada por la fuente

first_seen_at
    primera vez que nuestro observatorio encontró el anuncio

last_seen_at
    última vez que lo observó activo

source_updated_at
    fecha de actualización declarada, cuando exista

closed_observed_at
    momento en que se confirmó la desaparición o expiración
```

Nunca se sustituye silenciosamente una fecha de publicación ausente por `first_seen_at`.

En la interfaz:

```text
PUBLICADO: 28/07/2026
PRIMERA OBSERVACIÓN: 07/08/2026
```

o bien:

```text
PUBLICADO: no informado por la fuente
PRIMERA OBSERVACIÓN: 07/08/2026 11:00
```

## 2. Calidad de la fecha

### `published_at_precision`

```text
EXACT_DATETIME
EXACT_DATE
RELATIVE_RESOLVED
MONTH_ONLY
UNKNOWN
```

### `published_at_parse_method`

```text
STRUCTURED_DATA
SOURCE_FIELD
VISIBLE_TEXT
RELATIVE_TEXT_RESOLVED
AGGREGATOR_METADATA
MISSING
```

`RELATIVE_TEXT_RESOLVED` debe guardar el `observed_at` utilizado para resolver expresiones como `hace 3 días`.

## 3. Ordenación por novedad

El orden `más recientes` puede usar:

```text
COALESCE(source_published_at, first_seen_at)
```

pero debe indicar qué fecha sostiene el orden. Las estadísticas `nuevas hoy` se basan por defecto en **primera observación de la vacante**, no en una fecha declarada susceptible de edición o sindicación tardía.

## 4. Geolocalización canónica

La entidad `location` ya contempla latitud y longitud. La v0.2 añade:

```text
location_precision
coordinate_source
geocoding_confidence
privacy_display_level
public_display_latitude
public_display_longitude
geocoded_at
```

### `location_precision`

```text
EXACT_WORK_ADDRESS
POSTCODE
MUNICIPALITY
DISTRICT_OR_REGION
CANTON
REMOTE_OR_MULTIPLE
UNKNOWN
```

### `coordinate_source`

```text
SOURCE_STRUCTURED
SOURCE_TEXT_GEOCODED
SWISSTOPO_SEARCHSERVER
BFS_MUNICIPALITY_CENTROID
MANUAL_REVIEW
UNKNOWN
```

### `privacy_display_level`

```text
EXACT_ALLOWED
POSTCODE_CENTROID
MUNICIPALITY_CENTROID
REGION_CENTROID
HIDDEN
```

## 5. Privacidad de villas y hogares particulares

Para `PRIVATE_ESTATE_DIRECT`, `PRIVATE_HOUSEHOLD_DIRECT` y anuncios confidenciales:

- no se publica una dirección residencial exacta;
- el marcador se sitúa en el centroide municipal o regional;
- se evita cualquier texto que permita reconstruir la propiedad;
- la dirección raw, si legalmente se conserva, queda restringida y separada del dato público;
- el popup informa `ubicación aproximada por privacidad`.

## 6. Servicio geográfico recomendado

Para Suiza, la primera opción de geocodificación es el `SearchServer` de geo.admin.ch, que admite búsqueda de cantones, ciudades, comunas, códigos postales y direcciones y puede devolver coordenadas WGS84.

```text
https://api3.geo.admin.ch/rest/services/ech/SearchServer
```

Prioridad de resolución:

```text
BFS code exacto
   ↓
municipio + cantón
   ↓
código postal + municipio
   ↓
texto regional
   ↓
revisión manual
```

## 7. Mapa de producto

El dashboard debe ofrecer:

- pan y zoom;
- marcadores y clustering;
- filtros sincronizados con la tabla;
- popup con título, empleador, segmento, fecha publicada y primera observación;
- mapa de puntos, agregación por municipio y heatmap;
- clic en una fila para centrar el mapa;
- radio de distancia desde una ubicación del usuario en una fase posterior;
- indicador de precisión geográfica.

## 8. Tecnología recomendada

Para el MVP de producción:

```text
MapLibre GL JS
+ tiles explícitamente licenciados
+ geo.admin SearchServer para geocodificación
```

Google Maps puede añadirse más adelante si se necesitan Places, Street View o navegación avanzada. No es necesario para el observatorio inicial y exige clave y configuración de facturación para la Maps JavaScript API.

El prototipo v0.2 usa un mapa interactivo con tiles oficiales de swisstopo y centroides municipales aproximados; no constituye todavía el servicio geográfico de producción.

## 9. Métricas de calidad

```text
published_date_coverage_ratio
geocoded_vacancy_ratio
municipality_precision_ratio
exact_or_postcode_precision_ratio
privacy_generalization_count
geocoding_review_queue_size
```
