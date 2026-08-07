# 11 — Salary and Total Compensation Contract v0.3

**Estado:** `CLOSED_FOR_IMPLEMENTATION v0.3`  
**Fecha de corte:** 2026-08-07

## 1. Corrección de diseño

El salario pasa a ser una dimensión de primer nivel. La aplicación no mostrará una única cifra opaca llamada `salary`, porque mezclaría hechos jurídicos y estadísticos distintos.

```text
A. ADVERTISED PAY
   cifra publicada para una oferta concreta

B. APPLICABLE FLOOR / PUBLIC SCALE
   mínimo GAV o banda/clase salarial pública potencialmente aplicable

C. MARKET BENCHMARK
   referencia estadística para comparar, nunca salario prometido
```

La interfaz debe mostrar las tres capas por separado. Un benchmark jamás rellena el campo de salario de una oferta.

## 2. Estados de divulgación

```text
NOT_DISCLOSED
QUALITATIVE_ONLY              "competitive", "attraktive Entlöhnung"
EXPLICIT_FIXED
EXPLICIT_MINIMUM
EXPLICIT_MAXIMUM
EXPLICIT_RANGE
PUBLIC_GRADE_ONLY
COLLECTIVE_AGREEMENT_ONLY
```

`NOT_DISCLOSED` es un resultado informativo, no un dato ausente que deba ocultarse.

## 3. Origen y confianza

```text
EMPLOYER_DECLARED
EMPLOYER_DECLARED_VIA_JOB_BOARD
RECRUITER_DECLARED
JOB_BOARD_DISPLAYED
JOB_BOARD_SEARCH_RESULT
PUBLIC_PAY_SCALE_DERIVED
GAV_MINIMUM
MARKET_BENCHMARK
```

Todo valor conserva texto original, URL, momento de observación, método, confianza y vínculo con el posting. La extracción desde un agregador no se promoverá automáticamente a fuente canónica.

## 4. Normalización permitida

Campos obligatorios o recomendados:

```text
salary_disclosure_status
salary_origin
currency
salary_gross_net
salary_amount_min
salary_amount_max
salary_period                HOUR / MONTH / YEAR
salary_payments_per_year     12 / 13 / UNKNOWN
salary_workload_basis        ACTUAL_PENSUM / FTE_100 / UNKNOWN
salary_annual_gross_fte_min
salary_annual_gross_fte_max
salary_raw_text
salary_source_url
salary_observed_at
salary_confidence
salary_linkage_confidence
```

Sólo se calcula `annual_gross_fte_*` cuando se conocen de forma defendible:

- bruto/neto;
- período;
- número de pagas;
- si la cifra corresponde al pensum real o a un 100 %;
- divisa.

Ejemplo prohibido:

```text
CHF 5.000–6.500 / mes
        ↓
"CHF 78.000 / año"
```

No se puede multiplicar por 12 o 13 sin conocer las pagas ni asegurar que la cifra sea de 100 %.

## 5. Mínimos GAV 2026 de referencia

Los documentos oficiales de JardinSuisse/GBS fijan para relaciones laborales sometidas al GAV correspondiente:

### Garten-, Landschafts- und Sportplatzbau

| Nivel | Mensual × 13 | Anual equivalente | Base horaria |
|---|---:|---:|---:|
| Dirección con Fachausweis y función directiva | CHF 5.275 | CHF 68.575 | — |
| Gärtner/in EFZ | CHF 4.875 | CHF 63.375 | CHF 26,80 |
| Gärtner/in EBA | CHF 4.200 | CHF 54.600 | CHF 23,10 |
| Gartenarbeitende | CHF 4.000 | CHF 52.000 | CHF 22,00 |

### Baumschulen y producción/detail retail

| Nivel | Mensual × 13 | Anual equivalente | Base horaria |
|---|---:|---:|---:|
| Dirección con Fachausweis y función directiva | CHF 5.200 | CHF 67.600 | — |
| Gärtner/in EFZ | CHF 4.500 | CHF 58.500 | CHF 24,50 |
| Gärtner/in EBA | CHF 3.700 | CHF 48.100 | CHF 20,10 |
| Gärtnereimitarbeitende | CHF 3.550 | CHF 46.150 | CHF 19,30 |
| Aushilfen | — | — | CHF 17,70 |

Los importes horarios base requieren añadir por separado vacaciones, festivos y 13.º salario. Existen además reducciones limitadas para recién titulados y GAV cantonales/regionales que pueden prevalecer. Por ello el motor debe resolver `gav_applicability_status`, nunca aplicar el mínimo nacional por título solamente.

Fuentes oficiales:

- https://jardinsuisse.ch/de/themen/unsere-themen/sozialpartnerschaftgav/
- https://jardinsuisse.ch/documents/17326/2d1_I_PE_Lohnregulativ_Galabau_2026_d.pdf
- https://jardinsuisse.ch/documents/17359/2d1_I_PE_Lohnregulativ_BS_2026_d_Q3D0o0O.pdf
- https://jardinsuisse.ch/documents/17360/2d1_I_PE_Lohnregulativ_Prod_2026_d_ehBc7ma.pdf

## 6. Escalas públicas

Una administración puede publicar:

- una cifra/rango exacto;
- una clase o nivel salarial;
- únicamente el sistema retributivo general.

La app conservará:

```text
public_pay_system
public_pay_grade
public_pay_function_level
public_pay_scale_valid_at
public_pay_scale_source_url
public_pay_amount_min/max
public_pay_derivation_status
```

No se inferirá una clase salarial sólo por el título. Por ejemplo, Stadt Zürich usa 18 niveles funcionales y paga 13 mensualidades; la función, experiencia útil y desempeño condicionan la cifra. La banda exacta de un anuncio tiene prioridad frente a cualquier derivación general.

## 7. Total compensation

En empleo público o private estate, el valor real puede incluir:

```text
13TH_SALARY
PERFORMANCE_BONUS
LOYALTY_BONUS
PENSION_SUPPLEMENT
FAMILY_ALLOWANCE
OVERTIME_COMPENSATION
NIGHT_WEEKEND_ALLOWANCE
WINTER_SERVICE_ALLOWANCE
MEALS
HOUSING
VEHICLE
PHONE
TOOLS_CLOTHING
TRAINING
EXTRA_HOLIDAY
```

Cada componente se almacena con estado `INCLUDED`, `OFFERED`, `POSSIBLE`, `NOT_MENTIONED` o `UNKNOWN`. No se convierte automáticamente a CHF salvo que exista valor explícito.

## 8. Salario neto

El posting conserva salario bruto. No se mostrará un “neto” único porque depende, entre otros factores, de residencia, cantón/municipio, permiso, estado civil, hijos, iglesia, caja de pensiones y retención fiscal.

El futuro simulador neto será una herramienta separada, personalizada y versionada; nunca sobrescribirá el salario observado.

## 9. Métricas diarias

Se añaden:

```text
salary_disclosure_coverage_ratio
numeric_salary_coverage_ratio
annual_fte_normalization_coverage_ratio
median_advertised_annual_gross_fte
p25/p75_advertised_annual_gross_fte
median_by_role_access_canton_segment
salary_above_verified_floor_share
public_salary_range_coverage_ratio
benefits_disclosure_ratio
```

Reglas:

1. No mezclar mensual con anual sin normalización válida.
2. No mezclar salarios publicados con benchmarks/GAV.
3. Mostrar `n` y cobertura en cada estadístico.
4. Suprimir o marcar muestras pequeñas (`n < 5`).
5. Aprendices, prácticas y empleo por horas forman cohortes separadas.
6. Los rangos se analizan con mínimo, máximo y midpoint, conservando el intervalo original.

## 10. Resultado visible por oferta

```text
SALARIO PUBLICADO
CHF 70.000–82.000 brutos/año
Base: 100 % · origen: empleador vía portal

REFERENCIA GAV
EFZ GaLaBau 2026: CHF 63.375/año
Aplicabilidad: pendiente de verificar

BENCHMARK
Gärtner CH: CHF 60.000/año de media
Muestra: 945 · no es salario prometido
```

Cuando no exista cifra:

```text
SALARIO PUBLICADO
No publicado

REFERENCIAS
Sólo se muestran como comparación, nunca sustituyen al salario de la oferta.
```

## 11. Artefactos

- `salary_reference_2026.csv`
- `salary_evidence_seed_2026-08-07.csv`
- `posting_observation_v1_2.schema.json`
- `schema_v0_3_salary_patch.sql`
- `dashboard_prototype.html`
