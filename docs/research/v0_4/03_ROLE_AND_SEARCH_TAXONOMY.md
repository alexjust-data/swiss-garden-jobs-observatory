# 03 — Role and Search Taxonomy v0.1

## Problema

Buscar únicamente `Gärtner` pierde puestos públicos cuyo título visible es `Mitarbeiter Werkhof`, `Fachmann Betriebsunterhalt` o `Mitarbeiter Gebäudebetrieb`, aunque las tareas incluyan Grünpflege o Arealpflege.

## Familias canónicas

```text
GARDENING
LANDSCAPE_GARDENING
GARDEN_MAINTENANCE
GREEN_SPACE_MAINTENANCE
CEMETERY_GREEN
TREE_CARE
SPORT_GREEN
PLANT_PRODUCTION
NATURE_MAINTENANCE
PUBLIC_WORKS
HELPER
LEADERSHIP
```

## Títulos públicos ocultos

```text
Mitarbeiter Werkhof / Werkdienst
Gemeindearbeiter / Gemeindemitarbeiter
Fachmann/Fachfrau Betriebsunterhalt
Strassenunterhalt
Anlagenwart / Gebäudebetrieb
Aussenanlagen / Sportanlagen / Schulanlagen
Winterdienst
```

No se incluyen ciegamente. El clasificador exige señales de tarea como `Grünpflege`, `Arealpflege`, parques, cementerios, árboles, césped, plantaciones o biodiversidad.

## Niveles de acceso

| Nivel | Definición |
|---|---|
| `A0` | Quereinsteiger / sin experiencia explícitamente admitido |
| `A1` | Ayudante / experiencia básica |
| `A2` | Experiencia práctica, título no obligatorio |
| `A3` | EBA |
| `A4` | EFZ |
| `A5` | EFZ + experiencia / requisitos adicionales |
| `A6` | Vorarbeiter, Obergärtner, Teamleiter |
| `A7` | Projektleiter / dirección |
| `APPRENTICESHIP` | Cohorte separada de aprendizaje |

## Consulta de recuperación inicial

```text
(
  Gärtner OR Landschaftsgärtner OR Gartenunterhalt OR Grünpflege
  OR Parkpflege OR Friedhof OR Baumpflege OR Greenkeeper
  OR Pflanzenproduktion
)
OR
(
  Werkhof OR Werkdienst OR Betriebsunterhalt OR Gebäudebetrieb
  OR Arealpflege OR Aussenanlagen OR Strassenunterhalt
)
AND
(
  Grün OR Park OR Garten OR Baum OR Rasen OR Hecke OR Pflanz
  OR Friedhof OR Sportplatz OR Biodiversität OR Neophyten
)
```

La primera parte prioriza recall. La clasificación posterior decide inclusión. `role_search_taxonomy.csv` contiene **53 términos y exclusiones**.

## Exclusiones

Floristería, agricultura pura, silvicultura pura, limpieza interior y puestos administrativos quedan fuera por defecto o en cohortes separadas. No se elimina un puesto por título: se evalúa la materialidad de sus tareas verdes.
