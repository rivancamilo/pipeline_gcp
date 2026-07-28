# Enlaces y endpoints de fuentes remotas

## APIs públicas (NY Open Data — SODA)
Cada dataset expone el mismo dato en JSON, CSV y XML.

- **NY State Surplus Real Estate Sales (Beginning 2015)**
  - Portal: https://data.ny.gov/d/yv49-emnc
  - JSON:  https://data.ny.gov/resource/yv49-emnc.json
  - CSV:   https://data.ny.gov/api/v3/views/yv49-emnc/export.csv?accessType=DOWNLOAD
  - Doc columnas: https://data.ny.gov/api/views/yv49-emnc/columns.json
  - Nota: revise el campo de fecha con cuidado.

- **NY Real Property Transactions of State Authorities**
  - Portal: https://data.ny.gov/d/t7uh-5ac8
  - JSON:  https://data.ny.gov/resource/t7uh-5ac8.json
  - CSV:   https://data.ny.gov/api/v3/views/t7uh-5ac8/export.csv?accessType=DOWNLOAD
  - 29 columnas; muchos campos opcionales quedan vacíos.

Paginación SODA: parámetros `$limit` y `$offset` (p. ej. `?$limit=1000&$offset=2000`).

## Kaggle (requiere cuenta / API key de Kaggle)
- USA Real Estate Dataset (~2.2M): https://www.kaggle.com/datasets/ahmedshahriarsakib/usa-real-estate-dataset
- Housing Prices Metropolitan Areas India: https://www.kaggle.com/datasets/ruchi798/housing-prices-in-metropolitan-areas-of-india
- Miami Housing Dataset: https://www.kaggle.com/datasets/deepcontractor/miami-housing-dataset
- Houses in London: https://www.kaggle.com/datasets/oktayrdeki/houses-in-london

## HUD / FRED (series macro)
- Median Sales Price for New Houses Sold (FRED: MSPNHSUS): https://fred.stlouisfed.org/series/MSPNHSUS
- Monthly Supply of New Houses (FRED: MSACSR): https://fred.stlouisfed.org/series/MSACSR

> Si no tiene acceso a Kaggle/FRED en su entorno, use las fuentes incluidas y **describa**
> cómo automatizaría la conexión (autenticación, descarga, reintentos).
