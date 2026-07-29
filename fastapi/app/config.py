import os

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
GCP_PROJECT         = os.getenv("GCP_PROJECT", "pruebahabi")
GCS_BUCKET          = os.getenv("GCS_BUCKET_NAME", "habibucket")
BQ_FEATURES_TABLE   = "pruebahabi.consumption.ml_features_transacciones"
MODELO_REGISTRO     = "prediccion_precio_propiedades"
TOP_N_MODELOS       = 2
