#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orquestador de entrenamiento, evaluacion y registro de modelos.

Flujo por modelo:
    1. Crear pipeline (preprocesador + estimador)
    2. Validacion cruzada sobre train (MAE, RMSE, R2, MAPE)
    3. Entrenar sobre todo el conjunto train
    4. Evaluar sobre test
    5. Guardar modelo en disco (.joblib)  [nota: .keras es exclusivo de TF/Keras]
    6. Subir modelo a GCS
    7. Registrar run completo en MLflow (params, metricas CV + test, artefacto)
    8. Registrar modelo en MLflow Model Registry

Al final compara todos los modelos y promueve el mejor (mayor R2 en test)
al stage 'Production' en el Model Registry.
"""

import logging
import os
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
from google.cloud import bigquery, storage
from mlflow import MlflowClient

from cargador_datos import (
    cargar_test,
    cargar_train,
    resumen_datos,
    validar_estructura,
)
from evaluador import (
    calcular_metricas,
    imprimir_tabla_comparacion,
    validacion_cruzada,
)
from registro_modelos import crear_pipeline
from helpers import get_or_create_experiment


logger = logging.getLogger("entrenador")


# ------------------------------------------------------------------ #
# GCS
# ------------------------------------------------------------------ #
def _subir_a_gcs(
    ruta_local: str,
    bucket_name: str,
    blob_path: str,
) -> str:
    """Sube un archivo a GCS y devuelve la URI gs://..."""
    project = os.getenv("GCP_PROJECT")
    cliente = storage.Client(project=project)
    bucket = cliente.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.upload_from_filename(ruta_local)
    uri = f"gs://{bucket_name}/{blob_path}"
    logger.info("Modelo subido a %s", uri)
    return uri


# ------------------------------------------------------------------ #
# Entrenamiento de un modelo
# ------------------------------------------------------------------ #
def _entrenar_modelo(
    nombre: str,
    params: dict,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    features_num: List[str],
    features_cat: List[str],
    config: Dict[str, Any],
    experiment_id: str,
    precio_min: int = 0,
) -> Tuple[Optional[str], Dict[str, float]]:
    """
    Entrena un modelo, registra en MLflow y sube a GCS.

    Devuelve (run_id, metricas_test).
    """
    bucket      = config["gcs"]["bucket"]
    prefijo_gcs = config["gcs"]["prefijo_modelos"]
    cv_folds    = config.get("cv_folds", 5)
    random_state = config.get("random_state", 42)
    timestamp   = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    logger.info("=" * 60)
    logger.info("Entrenando: %s", nombre)
    logger.info("=" * 60)

    pipeline = crear_pipeline(nombre, params, features_num, features_cat)

    with mlflow.start_run(experiment_id=experiment_id, run_name=nombre) as run:
        run_id = run.info.run_id

        # ── 1. Parametros ────────────────────────────────────────
        mlflow.log_param("modelo", nombre)
        mlflow.log_param("cv_folds", cv_folds)
        mlflow.log_param("train_filas", len(X_train))
        mlflow.log_param("test_filas", len(X_test))
        mlflow.log_param("features_numericas", features_num)
        mlflow.log_param("features_categoricas", features_cat)
        for k, v in params.items():
            mlflow.log_param(k, v)

        # Estadisticas del dataset
        for k, v in resumen_datos(X_train, y_train, "train").items():
            mlflow.log_param(k, v)
        for k, v in resumen_datos(X_test, y_test, "test").items():
            mlflow.log_param(k, v)

        # ── 2. Validacion cruzada ─────────────────────────────────
        logger.info("Ejecutando %s-fold CV ...", cv_folds)
        metricas_cv = validacion_cruzada(
            pipeline, X_train, y_train, cv=cv_folds, random_state=random_state,
            precio_min=precio_min,
        )
        mlflow.log_metrics(metricas_cv)

        # ── 3. Entrenamiento final ────────────────────────────────
        logger.info("Entrenando modelo final sobre todo el train ...")
        pipeline.fit(X_train, y_train)

        # ── 4. Evaluacion en test ────────────────────────────────
        y_pred = pipeline.predict(X_test)
        metricas_test = calcular_metricas(y_test, y_pred, precio_min=precio_min)
        mlflow.log_metrics({f"test_{k}": v for k, v in metricas_test.items()})

        logger.info(
            "Test — MAE=%.0f  RMSE=%.0f  R2=%.4f  MAPE=%.2f%%",
            metricas_test["MAE"], metricas_test["RMSE"],
            metricas_test["R2"], metricas_test["MAPE"],
        )

        # ── 5. Guardar modelo en disco (.joblib) ─────────────────
        # Nota: .keras es exclusivo de TensorFlow/Keras.
        # Para sklearn y XGBoost el formato correcto es .joblib.
        nombre_archivo = f"{nombre}_{timestamp}.joblib"
        ruta_local = os.path.join(tempfile.gettempdir(), nombre_archivo)
        joblib.dump(pipeline, ruta_local)
        logger.info("Modelo guardado localmente: %s", ruta_local)

        # ── 6. Subir a GCS ────────────────────────────────────────
        blob_path = f"{prefijo_gcs}/{nombre_archivo}"
        try:
            uri_gcs = _subir_a_gcs(ruta_local, bucket, blob_path)
            mlflow.log_param("gcs_uri", uri_gcs)
        except Exception as exc:
            logger.warning("No se pudo subir a GCS: %s", exc)

        # ── 7. Registrar modelo en MLflow ─────────────────────────
        mlflow.sklearn.log_model(
            sk_model=pipeline,
            artifact_path="model",
            registered_model_name="prediccion_precio_propiedades",
        )
        mlflow.log_artifact(ruta_local, artifact_path="joblib")

        logger.info("Run registrado en MLflow: %s", run_id)

    return run_id, metricas_test


# ------------------------------------------------------------------ #
# Punto de entrada principal
# ------------------------------------------------------------------ #
def ejecutar_entrenamiento(
    bq_client: bigquery.Client,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Entrena todos los modelos del config, compara y promueve el mejor.

    Devuelve un dict con los resultados de todos los modelos.
    """
    tablas   = config["tablas_bigquery"]
    features_num = config["features"]["numericas"]
    features_cat = config["features"]["categoricas"]
    target   = config["target"]
    modelos_cfg = config["modelos"]
    precio_min = int(config.get("precio_minimo_entrenamiento", 0))

    # ── Cargar datos ─────────────────────────────────────────────
    logger.info("Cargando datos desde BigQuery ...")
    if precio_min > 0:
        logger.info(
            "Filtro de calidad: excluyendo registros con %s < %s COP",
            target, precio_min,
        )
    X_train, y_train = cargar_train(
        bq_client, tablas["train"], features_num, features_cat, target,
        precio_min=precio_min,
    )
    X_test, y_test = cargar_test(
        bq_client, tablas["test"], features_num, features_cat, target,
        precio_min=precio_min,
    )
    validar_estructura(X_train, X_test)

    # ── Experimento MLflow ────────────────────────────────────────
    experiment_id = get_or_create_experiment(config["experimento"])
    logger.info("Experimento MLflow: '%s' (id=%s)", config["experimento"], experiment_id)

    # ── Entrenar cada modelo ──────────────────────────────────────
    resultados: Dict[str, Dict] = {}
    run_ids: Dict[str, str] = {}

    for nombre, cfg in modelos_cfg.items():
        try:
            run_id, metricas_test = _entrenar_modelo(
                nombre=nombre,
                params=cfg.get("params", {}),
                X_train=X_train, y_train=y_train,
                X_test=X_test,   y_test=y_test,
                features_num=features_num,
                features_cat=features_cat,
                config=config,
                experiment_id=experiment_id,
                precio_min=precio_min,
            )
            resultados[nombre] = metricas_test
            run_ids[nombre] = run_id
        except Exception as exc:
            logger.error("Fallo entrenando '%s': %s", nombre, exc, exc_info=True)

    # ── Comparar y seleccionar mejor modelo ───────────────────────
    imprimir_tabla_comparacion(resultados)

    if resultados:
        mejor = max(resultados, key=lambda n: resultados[n].get("R2", -1))
        logger.info(
            "Mejor modelo: '%s' (R2_test=%.4f)", mejor, resultados[mejor]["R2"]
        )
        _promover_mejor_modelo(mejor, resultados[mejor])

    return {"modelos": resultados, "run_ids": run_ids}


def _promover_mejor_modelo(nombre: str, metricas: Dict[str, float]) -> None:
    """Promueve la version mas reciente del mejor modelo a 'Production'."""
    cliente = MlflowClient()
    registro = "prediccion_precio_propiedades"

    try:
        versiones = cliente.search_model_versions(f"name='{registro}'")
        if not versiones:
            logger.warning("No se encontraron versiones en el Model Registry.")
            return

        # Buscar la version que corresponde al mejor modelo por descripcion de run
        versiones_modelo = [
            v for v in versiones
            if cliente.get_run(v.run_id).data.params.get("modelo") == nombre
        ]
        if not versiones_modelo:
            versiones_modelo = versiones

        ultima_version = max(versiones_modelo, key=lambda v: int(v.version))

        cliente.transition_model_version_stage(
            name=registro,
            version=ultima_version.version,
            stage="Production",
            archive_existing_versions=True,
        )
        logger.info(
            "Modelo '%s' v%s promovido a Production (R2=%.4f).",
            nombre, ultima_version.version, metricas["R2"],
        )
    except Exception as exc:
        logger.warning("No se pudo promover el modelo: %s", exc)
