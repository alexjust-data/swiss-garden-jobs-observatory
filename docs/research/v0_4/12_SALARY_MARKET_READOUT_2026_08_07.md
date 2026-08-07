# 12 — Salary Market Readout — 7 August 2026

**Alcance:** jardinería y mantenimiento verde en Suiza, con foco en la Suiza alemana.  
**Estado:** lectura inicial; no es todavía una distribución salarial deduplicada del mercado completo.

## 1. Referencia general de mercado

jobs.ch muestra para `Gärtner` en Suiza una media de **CHF 60.000 brutos al año** para empleo a tiempo completo. La cifra incluye bonus y 13.º salario y se apoya en **945 declaraciones salariales**. Es un benchmark amplio: mezcla especialidades, experiencia, regiones y tipos de empleador.

Experiencia según la misma fuente:

| Experiencia | Media bruta anual |
|---|---:|
| 0–2 años | CHF 54.600 |
| 3–5 años | CHF 56.920 |
| 6–8 años | CHF 61.000 |
| 9–11 años | CHF 62.200 |
| 12–21 años | CHF 63.269 |
| Más de 21 años | CHF 68.250 |

Fuente: https://www.jobs.ch/de/lohn/?canton=ch&term=g%C3%A4rtner

## 2. Mínimos GAV 2026 — Garten-, Landschafts- und Sportplatzbau

Estos son mínimos para relaciones laborales realmente sometidas al GAV aplicable; no son el salario automático de cualquier anuncio.

| Perfil | Bruto mensual × 13 | Equivalente anual | Base horaria |
|---|---:|---:|---:|
| Gartenarbeitende | CHF 4.000 | CHF 52.000 | CHF 22,00 |
| Gärtner/in EBA | CHF 4.200 | CHF 54.600 | CHF 23,10 |
| Gärtner/in EFZ | CHF 4.875 | CHF 63.375 | CHF 26,80 |
| Dirección con Fachausweis y función directiva | CHF 5.275 | CHF 68.575 | — |

El documento fija 42 horas semanales de media. En salario por hora deben añadirse por separado vacaciones, festivos y 13.º salario. Hay posibles reducciones limitadas durante los primeros años posteriores a la titulación y pueden existir GAV regionales que prevalezcan.

Fuente oficial: https://jardinsuisse.ch/documents/17326/2d1_I_PE_Lohnregulativ_Galabau_2026_d.pdf

## 3. Mínimos GAV 2026 — Baumschulen / producción / detail retail

| Perfil | Bruto mensual × 13 | Equivalente anual | Base horaria |
|---|---:|---:|---:|
| Gärtnereimitarbeitende | CHF 3.550 | CHF 46.150 | CHF 19,30 |
| Gärtner/in EBA | CHF 3.700 | CHF 48.100 | CHF 20,10 |
| Gärtner/in EFZ | CHF 4.500 | CHF 58.500 | CHF 24,50 |
| Dirección con Fachausweis y función directiva | CHF 5.200 | CHF 67.600 | — |
| Aushilfen | — | — | CHF 17,70 |

Fuentes oficiales:

- https://jardinsuisse.ch/documents/17359/2d1_I_PE_Lohnregulativ_BS_2026_d_Q3D0o0O.pdf
- https://jardinsuisse.ch/documents/17360/2d1_I_PE_Lohnregulativ_Prod_2026_d_ehBc7ma.pdf

## 4. Salarios publicados encontrados en anuncios

| Segmento | Puesto | Salario publicado | Observación |
|---|---|---:|---|
| Administración municipal | Grün Stadt Zürich — Gärtner*in, Ref. 50017 | **CHF 70.000–82.000 brutos/año**, base 100 % | Rango explícito del anuncio; salario efectivo puede variar por experiencia y competencias |
| Administración municipal especializada | Grün Stadt Zürich — Fachbearbeiter*in Baumschutz, Ref. 51057 | **CHF 84.600–98.800/año**, base mostrada 100 % | Perfil técnico/especializado |
| Jardines privados premium | Bill & Meyer Gartenbau AG — EFZ/Vorarbeiter/Kundengärtner | **CHF 5.000–6.500/mes** | No anualizar hasta confirmar 12/13 pagas y base exacta de pensum |
| Private estate | Lead-Privatgärtner/-in, Zürichsee | **CHF 60.000–85.000/año** | Evidencia procedente del resultado de búsqueda; detalle contractual pendiente |
| Comercial | Stadt-Gärtner:in / flores, Zürich | **desde CHF 56.000/año** | Oferta histórica con mínimo publicado |

Fuentes de evidencia:

- https://ch.indeed.com/q-stadt-g%C3%A4rtner-jobs.html
- https://www.jobs.ch/de/stellenangebote/detail/7d193948-ce89-433f-b06a-83aa39a0c0a1/
- https://www.jobs.ch/de/stellenangebote/?page=2&term=jardinier
- https://www.jobs.ch/de/stellenangebote/detail/c81141fb-edbc-42ba-b6a2-35692a372691/

## 5. Qué lectura preliminar sí parece razonable

Los ejemplos observados sugieren una escalera aproximada, aún no una distribución completa:

```text
ayudante / garden worker GAV       ~ CHF 52k/año
EBA GaLaBau GAV                    ~ CHF 54,6k/año
EFZ GaLaBau GAV                    ~ CHF 63,4k/año
EFZ público municipal observado      CHF 70k–82k/año
especialista público observado       CHF 84,6k–98,8k/año
lead private estate observado         CHF 60k–85k/año
premium private gardens observado     CHF 5k–6,5k/mes
```

No debe concluirse todavía que todo empleo público o todo jardín de lujo pague más. Hace falta reunir suficientes anuncios comparables y medir cobertura, rol, experiencia, cantón, pensum y total compensation.

## 6. Qué mostrará la aplicación

Para cada oferta:

```text
Salario publicado:       cifra exacta o “No publicado”
Base:                     hora / mes / año; 100 % o pensum real
Bruto/neto:               según evidencia
13.º salario:             incluido / separado / desconocido
GAV o escala pública:     referencia separada y aplicabilidad
Benchmark:                comparación, nunca salario prometido
Beneficios:               vivienda, vehículo, bonus, pensión, etc.
```

El dashboard calculará cobertura salarial, percentiles y medianas sólo con observaciones comparables y mostrará siempre el tamaño de muestra.
