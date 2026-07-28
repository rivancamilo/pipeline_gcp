# Catálogo de fuentes — Prueba Data Platform Engineer · Habi

Este catálogo describe un **abanico de fuentes heterogéneas** de mercado inmobiliario.
No todas sirven para lo mismo, no comparten país, moneda, año ni granularidad, y algunas
tienen problemas de calidad. **Parte de la prueba es que usted decida cuáles usar** para
construir su caso, y **justifique lo que incluye y lo que descarta**.

Unas fuentes vienen **incluidas** en esta carpeta. Otras son **remotas**: debe conectarse
usted mismo (API o descarga) para demostrar su capacidad de ingesta. No necesita usarlas
todas.

---

## A. Fuentes incluidas (en esta carpeta)

| Archivo | Formato | País / moneda | Granularidad | Notas |
|---|---|---|---|---|
| `co_transacciones_habi.csv` | CSV (~46k filas) | Colombia / COP | Transacción individual, con fecha 2024 | Fuente interna de Habi (compra/remodelación/venta). Tiene fecha → permite análisis temporal. |
| `india_metro_housing.csv` | CSV (~18k filas) | India / INR (lakh) | Propiedad individual, **sin fecha** | Precios en *lakh* (1 lakh = 100.000 INR). No trae año. |
| `usa_transactions_page_XX.json` | JSON paginado | USA / USD | Transacción individual | Respuesta de API: `meta` (paginación) + `data`. Recorra `meta.next`. |
| `macro_housing_index.xml` | XML | CO / IN / USA | Índice mensual (serie) | Índice de precio base 100, mensual, por país. Útil para tendencia. |

## B. Fuentes remotas (usted se conecta)

Demuestre que sabe ingerir desde origen. Elija las que le sirvan.

| Fuente | Acceso | Por qué podría servir |
|---|---|---|
| NY State Surplus Real Estate Sales | API pública (data.ny.gov, SODA) — JSON / CSV / XML | Subastas de inmuebles del Estado. Mismo dato en 3 formatos. |
| NY Real Property Transactions of State Authorities | API pública (data.ny.gov, SODA) | Compra/venta/arriendo, 8 años fiscales, 29 columnas. |
| USA Real Estate Dataset (realtor.com) | Kaggle (~2.2M filas) | **Alto volumen** real. Listings por estado/zip. Estresa performance. |
| HUD / FRED — Median Sales Price, Monthly Supply, Houses by Stage | Kaggle / FRED | Series macro históricas de EE. UU. (referencia de mercado). |
| Miami / London housing | Kaggle | Listings con features geográficas y de ciudad. |

> Endpoints y enlaces exactos en `ENLACES.md`. Si su entorno no tiene acceso a alguna,
> documente cómo lo resolvería y siga con las demás.

---

## Advertencia honesta sobre los datos

Estas fuentes reflejan condiciones reales: **distintas monedas, distintos años (o sin año),
distinta granularidad, formatos mezclados y problemas de calidad**. No las hemos "limpiado"
para usted. Detectar esas fricciones, decidir cómo resolverlas (o por qué descartar una
fuente) y **dejarlo documentado** es exactamente lo que evaluamos.
