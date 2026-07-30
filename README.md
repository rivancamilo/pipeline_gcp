# Plataforma de Predicción de Precios Inmobiliarios

Sistema completo para predicción de precios de inmuebles en Colombia. Orquesta un pipeline de datos con **Apache Airflow**, sobre un data lake/warehouse en **Google Cloud (BigQuery + Cloud Storage)** organizado en capas raw → staging → consumption, con **validación de contratos de datos (Data Contracts)**, entrenamiento y registro de modelos con **MLflow**, y una interfaz web de estimación de precios construida con **FastAPI**.

---

- **MySQL** solo actúa como backend de metadatos interno de Airflow; los datos de negocio viven en **BigQuery**.
- **Airflow** ingesta archivos desde Google Cloud Storage (GCS), los transforma en BigQuery (raw → staging → consumption) y, al terminar el pipeline de transacciones, dispara el entrenamiento de modelos ejecutando un docker exec sobre el contenedor de MLflow.
- **MLflow** entrena varios modelos, los registra en su Model Registry y sube los artefactos .joblib a GCS.
- **FastAPI** consulta el Model Registry de MLflow, descarga el mejor modelo desde GCS y expone un formulario web + API REST para estimar precios.

| Servicio | Puerto host | Descripción |
|----------|-------------|-------------|
| **FastAPI** | 8000 | Interfaz web y API de predicción |
| **Airflow** | 8080 | Orquestación de pipelines ETL |
| **MLflow** | 5000 | Tracking UI y Model Registry |
| **MySQL** | 3307 → 3306 | Backend de metadatos de Airflow|

---

## Estructura de carpetas

```
ProyectoDocker/
├── airflow/
│   ├── dags/
│   │   ├── dag_csv.py          # Pipeline completo: raw → staging → consumption → entrenamiento
│   │   ├── dag_json.py         # Ingesta a raw de transacciones paginadas (JSON)
│   │   ├── dag_xml.py          # Ingesta a raw del índice macro de vivienda (XML)
│   │   └── dag_api.py          # Ingesta a raw de una API REST paginada
│   ├── scripts/
│   │   ├── config.py           # Configuración centralizada
│   │   ├── utilidades.py       # Cliente GCS/BigQuery/API: carga a raw, auditoría, metadatos
│   │   ├── validador_contratos.py  # Motor de validación de Data Contracts
│   │   ├── paso_raw.py         # Orquesta la carga landing → raw (CSV/XML/JSON)
│   │   ├── paso_api_raw.py     # Orquesta la carga de una API REST paginada → raw
│   │   ├── paso_staging.py     # Orquesta la transformación raw → staging
│   │   ├── paso_consumption.py # Orquesta staging → consumption + validación de contratos
│   │   ├── transformaciones.py # Reglas de limpieza/tipado
│   │   ├── carga.py            # Estrategias de carga: FULL / INCREMENTAL / UPSERT
│   │   └── consumo.py          # Genera features ML y split train/test
│   │   └── tests/
│   │       └── test_transformaciones.py  # 6 pruebas unitarias (normalización, casteo, dedup, etc.)
│   ├── plugins/                # Plugins de Airflow
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── requirements-dev.txt    # Dependencias solo de desarrollo (pytest)
│   └── start-airflow.sh        # Espera MySQL, inicializa Airflow y levanta webserver+scheduler
│
├── mlflow/
│   ├── experiments/
│   │   ├── entrenar_modelos.py     # Punto de entrada real del entrenamiento (usa BigQuery)
│   │   ├── config_modelos.yaml     # Modelos, hiperparámetros, features y tablas de origen
│   ├── scripts/
│   │   ├── cargador_datos.py   # Carga train/test desde BigQuery y valida su estructura
│   │   ├── entrenador.py       # Orquesta CV, entrenamiento, logging y promoción a Production
│   │   ├── evaluador.py        # Métricas (MAE, RMSE, R², MAPE) y validación cruzada
│   │   ├── registro_modelos.py # Registro de modelos y pipelines de preprocesamiento sklearn
│   │   └── helpers.py          # Utilidades de MLflow (experimentos, logging de datasets)
│   └── Dockerfile
│
├── fastapi/
│   ├── app/
│   │   ├── main.py             # App FastAPI, CORS, montaje de estáticos y routers
│   │   ├── config.py           # Configuración (MLflow URI, proyecto GCP, dataset, etc.)
│   │   ├── routers/
│   │   │   ├── pages.py        # GET / → formulario de estimación
│   │   │   └── predict.py      # /api/health, /api/modelos, /api/opciones, /api/predict
│   │   ├── services/
│   │   │   ├── bigquery_service.py  # Valores únicos (ciudad, tipo) desde BigQuery
│   │   │   └── model_service.py     # Consulta MLflow Registry, descarga modelo desde GCS y predice
│   │   └── models/
│   │       └── schemas.py      # Esquemas Pydantic (PropiedadInput, PrediccionResultado, ...)
│   ├── templates/
│   │   └── index.html          # Formulario con mapa Leaflet para seleccionar ubicación
│   ├── static/
│   │   ├── css/style.css
│   │   └── js/main.js
│   ├── Dockerfile
│   └── requirements.txt
│
├── contratos/
│   └── consumo/
│       ├── ml_features_transacciones.yml
│       ├── ml_train_transacciones.yml
│       └── ml_test_transacciones.yml
│
├── docker-compose.yml
├── .env                        # Variables de entorno (no versionado)
└── README.md
```
---

## Construir y levantar los contenedores

```bash
# Construir imágenes
docker compose build

# Levantar todos los servicios en segundo plano
docker compose up -d

# Ver el estado de los contenedores
docker compose ps

# Ver logs en tiempo real
docker compose logs -f
```

---

## Acceder a los servicios

Una vez que todos los contenedores estén `healthy`:

| Servicio | URL | Credenciales |
|----------|-----|--------------|
| **FastAPI** | http://localhost:8000 | - |
| **Airflow UI** | http://localhost:8080 | admin / admin |
| **MLflow UI** | http://localhost:5000 | - |
| **API Docs (Swagger)** | http://localhost:8000/docs | - |

---
## Ejecutar pruebas (tests)

El archivo `airflow/scripts/tests/test_transformaciones.py` contiene **6 pruebas unitarias** desarrolladas con **pytest** para validar la lógica de `transformaciones.py`, encargada de la transformación **raw → staging** del archivo `co_transacciones_habi.csv`.

Las pruebas verifican los siguientes escenarios:
- Normalización de ciudades.
- Eliminación de registros con `precio_cop` nulo.
- Deduplicación de registros por `id`.
- Conversión de columnas a sus tipos de datos correctos (numéricas y fechas).
- Normalización de los valores de `tipo` y `estado`.

Cada prueba está asociada a un hallazgo cuantitativo documentado en el archivo `/EDA/EDA.ipynb`.

`pytest` no hace parte de la imagen de producción, por lo que no está incluido en `requirements.txt`. En su lugar, se encuentra listado en `airflow/requirements-dev.txt`, archivo que sirve únicamente como referencia y **no se copia a la imagen ni se monta como volumen**. De esta manera se evita incrementar el tamaño de la imagen de Airflow.

### Opción A — Dentro del contenedor de Airflow (Docker)

Requiere Docker Desktop corriendo. Instala `pytest` una única vez dentro del contenedor y luego ejecuta:

```bash
# Instalar pytest dentro del contenedor
docker compose exec airflow python -m pip install pytest==7.4.4

# Ejecutar las pruebas
docker compose exec airflow env PYTHONPATH=/opt/airflow/scripts python -m pytest /opt/airflow/scripts/tests -v
```

### Opción B — Localmente con `uv` (sin Docker)

```bash
uv run pytest airflow/scripts/tests -v
```
---

## Detener los servicios

```bash
# Detener sin eliminar volúmenes (mantiene datos)
docker compose down

# Detener y eliminar todos los volúmenes (reset completo)
docker compose down -v

# Detener un servicio específico
docker compose stop fastapi
```
