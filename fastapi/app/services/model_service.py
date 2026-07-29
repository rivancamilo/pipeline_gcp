"""
Servicio de modelos: descarga desde GCS, cacheo en memoria e inferencia.

Flujo:
  1. get_available_models()  → consulta MLflow REST API, devuelve top-N por test_R2
  2. load_model(nombre)      → descarga .joblib de GCS la primera vez, cachea en RAM
  3. predict(nombre, datos)  → deriva features y ejecuta pipeline.predict()
"""
import io
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import joblib
import numpy as np
import pandas as pd
from google.cloud import storage

from app.config import (
    GCS_BUCKET,
    GCP_PROJECT,
    MLFLOW_TRACKING_URI,
    MODELO_REGISTRO,
    TOP_N_MODELOS,
)

logger = logging.getLogger("model_service")

# ── Cache en memoria (duración: vida del proceso) ──────────────────
_MODELS_INFO_CACHE: Optional[List[Dict]] = None
_PIPELINE_CACHE: Dict[str, Any] = {}

# Orden de columnas que espera el pipeline (debe coincidir con entrenamiento)
_NUM_FEATURES = [
    "area_m2", "alcobas", "banos", "lat", "lon",
    "banos_por_alcoba", "area_por_alcoba",
    "anio", "mes", "trimestre", "dia_semana",
]
_CAT_FEATURES = ["ciudad", "tipo", "estado"]


# ── MLflow (REST API) ──────────────────────────────────────────────
def _mlflow_get(path: str, params: dict | None = None) -> dict:
    url = f"{MLFLOW_TRACKING_URI}{path}"
    with httpx.Client(timeout=15) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def get_available_models() -> List[Dict]:
    """
    Devuelve los TOP_N_MODELOS mejores modelos registrados en MLflow,
    ordenados por test_R2 descendente. Resultado cacheado.
    """
    global _MODELS_INFO_CACHE
    if _MODELS_INFO_CACHE is not None:
        return _MODELS_INFO_CACHE

    try:
        data = _mlflow_get(
            "/api/2.0/mlflow/model-versions/search",
            {"filter": f"name='{MODELO_REGISTRO}'", "max_results": 100},
        )
        versiones = data.get("model_versions", [])
    except Exception as exc:
        logger.error("Error consultando MLflow registry: %s", exc)
        return []

    # Por nombre de modelo, quedarse con la version de mayor R2
    candidatos: Dict[str, Dict] = {}
    for v in versiones:
        run_id = v.get("run_id", "")
        if not run_id:
            continue
        try:
            run_data = _mlflow_get("/api/2.0/mlflow/runs/get", {"run_id": run_id})
            run = run_data.get("run", {})
            params_run = {
                p["key"]: p["value"]
                for p in run.get("data", {}).get("params", [])
            }
            metrics_run = {
                m["key"]: float(m["value"])
                for m in run.get("data", {}).get("metrics", [])
            }

            nombre  = params_run.get("modelo", "")
            gcs_uri = params_run.get("gcs_uri", "")
            r2      = metrics_run.get("test_R2", 0.0)

            if not nombre or not gcs_uri:
                continue

            if nombre not in candidatos or r2 > candidatos[nombre]["r2"]:
                candidatos[nombre] = {
                    "nombre":  nombre,
                    "version": v.get("version", ""),
                    "r2":      r2,
                    "gcs_uri": gcs_uri,
                    "etapa":   v.get("current_stage", ""),
                }
        except Exception as exc:
            logger.warning("Saltando version %s: %s", v.get("version"), exc)

    top = sorted(candidatos.values(), key=lambda x: x["r2"], reverse=True)[:TOP_N_MODELOS]
    if top:
        _MODELS_INFO_CACHE = top
    logger.info("Modelos disponibles: %s", [m["nombre"] for m in top])
    return top


# ── GCS: descarga y cacheo ─────────────────────────────────────────
def _blob_path(uri: str) -> str:
    return uri.replace(f"gs://{GCS_BUCKET}/", "")


def load_model(nombre: str) -> Any:
    """Carga el pipeline desde GCS (o lo retorna del cache si ya fue descargado)."""
    if nombre in _PIPELINE_CACHE:
        return _PIPELINE_CACHE[nombre]

    info = next((m for m in get_available_models() if m["nombre"] == nombre), None)
    if info is None:
        raise ValueError(f"Modelo '{nombre}' no encontrado en el registro.")

    logger.info("Descargando '%s' desde %s ...", nombre, info["gcs_uri"])
    gcs    = storage.Client(project=GCP_PROJECT)
    bucket = gcs.bucket(GCS_BUCKET)
    blob   = bucket.blob(_blob_path(info["gcs_uri"]))

    buffer = io.BytesIO()
    blob.download_to_file(buffer)
    buffer.seek(0)
    pipeline = joblib.load(buffer)

    _PIPELINE_CACHE[nombre] = pipeline
    logger.info("Modelo '%s' cacheado en memoria.", nombre)
    return pipeline


# ── Inferencia ─────────────────────────────────────────────────────
def _construir_df(data: dict) -> pd.DataFrame:
    """Construye el DataFrame de features a partir de los datos del formulario."""
    alcobas = float(data["alcobas"])
    banos   = float(data["banos"])
    area_m2 = float(data["area_m2"])
    ahora   = datetime.now()

    # BigQuery DAYOFWEEK: 1=Domingo, 2=Lunes, ..., 7=Sábado
    dia_semana = ahora.isoweekday() % 7 + 1

    fila = {
        "area_m2":        area_m2,
        "alcobas":        int(data["alcobas"]),
        "banos":          int(data["banos"]),
        "lat":            float(data["lat"]),
        "lon":            float(data["lon"]),
        "banos_por_alcoba": banos / alcobas if alcobas > 0 else np.nan,
        "area_por_alcoba":  area_m2 / alcobas if alcobas > 0 else np.nan,
        "anio":           ahora.year,
        "mes":            ahora.month,
        "trimestre":      (ahora.month - 1) // 3 + 1,
        "dia_semana":     dia_semana,
        "ciudad":         data["ciudad"],
        "tipo":           data["tipo"],
        "estado":         None,  # campo eliminado del formulario; el imputer lo neutraliza
    }
    return pd.DataFrame([fila], columns=_NUM_FEATURES + _CAT_FEATURES)


def predict(nombre_modelo: str, data: dict) -> float:
    pipeline = load_model(nombre_modelo)
    df       = _construir_df(data)
    precio   = float(pipeline.predict(df)[0])
    return max(0.0, precio)
