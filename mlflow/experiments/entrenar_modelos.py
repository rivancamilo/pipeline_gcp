#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Punto de entrada para el entrenamiento de modelos de prediccion de precios.

Uso desde el contenedor MLflow:
    docker exec predicasa-mlflow python /mlflow/experiments/entrenar_modelos.py

O con configuracion alternativa:
    docker exec predicasa-mlflow \
        python /mlflow/experiments/entrenar_modelos.py \
        --config /mlflow/experiments/config_modelos.yaml
"""

import argparse
import logging
import os
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import mlflow
from google.cloud import bigquery

from entrenador import ejecutar_entrenamiento


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("entrenar_modelos")


def _cargar_config(ruta: str) -> dict:
    with open(ruta, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Entrena modelos de prediccion de precios.")
    parser.add_argument(
        "--config",
        default=os.path.join(os.path.dirname(__file__), "config_modelos.yaml"),
        help="Ruta al archivo de configuracion YAML.",
    )
    args = parser.parse_args()

    # ── Configuracion ──────────────────────────────────────────
    logger.info("Cargando configuracion desde: %s", args.config)
    config = _cargar_config(args.config)

    # ── MLflow ─────────────────────────────────────────────────
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    mlflow.set_tracking_uri(tracking_uri)
    logger.info("MLflow tracking URI: %s", tracking_uri)

    # ── BigQuery ────────────────────────────────────────────────
    project = config["tablas_bigquery"]["project"]
    logger.info("Conectando a BigQuery (proyecto: %s) ...", project)
    bq_client = bigquery.Client(project=project)

    # ── Entrenamiento ───────────────────────────────────────────
    logger.info("Iniciando entrenamiento de %s modelos ...", len(config["modelos"]))
    resultados = ejecutar_entrenamiento(bq_client, config)

    # ── Resumen final ────────────────────────────────────────────
    logger.info("Entrenamiento completado.")
    logger.info("Modelos entrenados: %s", list(resultados["modelos"].keys()))
    logger.info(
        "Run IDs: %s",
        {k: v[:8] + "..." for k, v in resultados["run_ids"].items() if v}
    )


if __name__ == "__main__":
    main()
