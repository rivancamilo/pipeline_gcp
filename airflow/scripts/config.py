import os

# Proyecto GCP
PROJECT_ID = os.environ["GCP_PROJECT"]

# Google Cloud Storage
BUCKET_NAME         = os.environ["GCS_BUCKET_NAME"]
PREFIX_LANDING      = os.environ["GCS_PREFIX_LANDING"]
PREFIX_PROCESSING   = os.environ["GCS_PREFIX_PROCESSING"]
PREFIX_PROCESSED    = os.environ["GCS_PREFIX_PROCESSED"]

# Datasets de BigQuery
DATASET_CONFIG      = os.environ["BQ_DATASET_CONFIG"]
DATASET_RAW         = os.environ["BQ_DATASET_RAW"]
DATASET_STAGING     = os.environ["BQ_DATASET_STAGING"]
DATASET_CONSUMPTION = os.environ["BQ_DATASET_CONSUMPTION"]

# Fuentes para la tabla de auditoria
FUENTE_RAW          = os.environ["BQ_FUENTE_RAW"]
FUENTE_STAGING      = os.environ["BQ_FUENTE_STAGING"]
FUENTE_CONSUMPTION  = os.environ["BQ_FUENTE_CONSUMPTION"]

# Consumption ML
PCT_TRAIN               = int(os.getenv("ML_PCT_TRAIN", "80"))
PRECIO_MIN_ENTRENAMIENTO = int(os.getenv("ML_PRECIO_MIN", "10000000"))


SODA_APP_TOKEN = os.getenv("SODA_APP_TOKEN") or None
