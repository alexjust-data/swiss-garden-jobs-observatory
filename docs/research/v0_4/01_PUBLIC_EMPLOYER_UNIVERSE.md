# 01 — Public Green Employer Universe v0.1

## 1. Definición geográfica

El universo no se define mediante una lista simplificada de cantones. Se parte del snapshot municipal oficial del BFS de **2026-01-01** y se seleccionan las comunas cuyo `SPRGEB2020 = 1`.

Resultado:

- Municipios germanófonos: **1,374**
- Cantones que contienen al menos uno: **22**
- Ciudades estadísticas (`STADTE2020 = 1`): **127**
- Clasificación DEGURB: urbano **76**, intermedio **685**, rural **613**.

| Cantón | Código | Municipios SPRGEB2020=1 |
| --- | --- | --- |
| Bern | BE | 299 |
| Aargau | AG | 196 |
| Zürich | ZH | 160 |
| Solothurn | SO | 104 |
| Basel-Landschaft | BL | 86 |
| Thurgau | TG | 80 |
| Luzern | LU | 79 |
| St. Gallen | SG | 75 |
| Graubünden | GR | 70 |
| Wallis/Valais | VS | 63 |
| Schwyz | SZ | 30 |
| Fribourg/Freiburg | FR | 26 |
| Schaffhausen | SH | 26 |
| Appenzell Ausserrhoden | AR | 20 |
| Uri | UR | 19 |
| Nidwalden | NW | 11 |
| Zug | ZG | 11 |
| Obwalden | OW | 7 |
| Appenzell Innerrhoden | AI | 5 |
| Basel-Stadt | BS | 3 |
| Glarus | GL | 3 |
| Jura | JU | 1 |

## 2. Universo auditable

```text
SCHWEIZERISCHE EIDGENOSSENSCHAFT                    1
CANTONES CON MUNICIPIOS GERMANÓFONOS               22
MUNICIPIOS GERMANÓFONOS                          1374
                                                   ─────
PUBLIC EMPLOYER AUDIT UNIVERSE                    1397
```

Esto no significa que existan 1,397 portales independientes. Un municipio puede:

- operar un portal propio;
- utilizar un ATS compartido;
- publicar en el portal cantonal;
- notificar en Job-Room;
- publicar únicamente mediante una plataforma pública o una ETT;
- no tener ninguna vacante en el período observado.

## 3. Prioridad de auditoría

| Tier | Criterio | Acción |
|---|---|---|
| `P0` | Confederación y cantones | Fuente oficial y collector contract |
| `P0_CITY` | Ciudad estadística BFS | Descubrir portal, ATS y unidad verde |
| `P1_URBAN_OR_INTERMEDIATE` | DEGURB 1–2, no ciudad estadística | Auditar tras ciudades |
| `P2_RURAL` | DEGURB 3 | Cubrir con portales compartidos, Job-Room y discovery |

## 4. Unidades públicas que deben investigarse

```text
Stadtgrün · Stadtgärtnerei · Grün Stadt
Werkhof · Werkdienst · Gemeindebetriebe
Friedhof · Parkanlagen · Sportanlagen · Schulanlagen
Strassenunterhalt · Liegenschaften · Arealpflege
Forst/Natur · Biodiversität · Neophyten · Winterdienst
Bundesimmobilien · Armee · Agroscope · ASTRA
```

## 5. Relación laboral

- `PUBLIC_DIRECT`: contrato directo con Bund, Kanton, Stadt o Gemeinde.
- `PUBLIC_INSTITUTION`: universidad, hospital, fundación o entidad pública.
- `PUBLIC_CONTRACTOR`: empresa privada que ejecuta un contrato público; no es empleo administrativo directo.
- `PRIVATE_DIRECT`: empresa privada ordinaria.
- `AGENCY`: ETT o intermediario contractual.

La aplicación debe permitir filtrar estas clases sin confundir el lugar donde se trabaja con quién firma el contrato.

## 6. Cierre real de W1

`public_employer_universe_1397.csv` contiene todos los registros administrativos del universo. `city_portal_audit_queue_127.csv` ordena la investigación de las ciudades. El cierre de W1 significa **universo completo y cola reproducible**, no que todos los endpoints municipales estén ya automatizados.
