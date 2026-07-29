#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Carga de datos de entrenamiento y prueba desde BigQuery.
"""

import logging
from typing import Dict, List, Tuple

import pandas as pd
from google.cloud import bigquery


logger = logging.getLogger("cargador_datos")


def _ejecutar_query(bq_client: bigquery.Client, sql: str, descripcion: str) -> pd.DataFrame:
    logger.info("Cargando %s ...", descripcion)
    try:
        df = bq_client.query(sql).to_dataframe()
        logger.info("%s: %s filas, %s columnas.", descripcion, len(df), len(df.columns))
        return df
    except Exception as exc:
        raise RuntimeError(f"Error cargando {descripcion}: {exc}") from exc


def cargar_train(
    bq_client: bigquery.Client,
    tabla: str,
    features_num: List[str],
    features_cat: List[str],
    target: str,
    precio_min: int = 0,
) -> Tuple[pd.DataFrame, pd.Series]:
    """Carga conjunto de entrenamiento desde BigQuery."""
    columnas = features_num + features_cat + [target]
    sql = f"SELECT {', '.join(columnas)} FROM `{tabla}`"
    if precio_min > 0:
        sql += f" WHERE {target} >= {precio_min}"
        logger.info("Filtro de calidad aplicado: %s >= %s", target, precio_min)
    df = _ejecutar_query(bq_client, sql, f"train ({tabla})")
    return df[features_num + features_cat], df[target]


def cargar_test(
    bq_client: bigquery.Client,
    tabla: str,
    features_num: List[str],
    features_cat: List[str],
    target: str,
    precio_min: int = 0,
) -> Tuple[pd.DataFrame, pd.Series]:
    """Carga conjunto de prueba desde BigQuery."""
    columnas = features_num + features_cat + [target]
    sql = f"SELECT {', '.join(columnas)} FROM `{tabla}`"
    if precio_min > 0:
        sql += f" WHERE {target} >= {precio_min}"
        logger.info("Filtro de calidad aplicado: %s >= %s", target, precio_min)
    df = _ejecutar_query(bq_client, sql, f"test ({tabla})")
    return df[features_num + features_cat], df[target]


def validar_estructura(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
) -> None:
    """Verifica que train y test tengan las mismas columnas y tipos."""
    cols_train = set(X_train.columns)
    cols_test = set(X_test.columns)

    faltantes_en_test = cols_train - cols_test
    extras_en_test = cols_test - cols_train

    if faltantes_en_test:
        raise RuntimeError(f"Columnas en train pero no en test: {faltantes_en_test}")
    if extras_en_test:
        raise RuntimeError(f"Columnas en test pero no en train: {extras_en_test}")

    for col in X_train.columns:
        if X_train[col].dtype != X_test[col].dtype:
            logger.warning(
                "Tipo distinto en '%s': train=%s, test=%s",
                col, X_train[col].dtype, X_test[col].dtype,
            )

    logger.info(
        "Estructura validada: %s features, train=%s filas, test=%s filas.",
        len(X_train.columns), len(X_train), len(X_test),
    )


def resumen_datos(X: pd.DataFrame, y: pd.Series, nombre: str) -> Dict:
    """Devuelve estadisticas basicas del dataset."""
    nulos = X.isnull().sum()
    return {
        f"{nombre}_filas": len(X),
        f"{nombre}_nulos_total": int(nulos.sum()),
        f"{nombre}_target_media": round(float(y.mean()), 2),
        f"{nombre}_target_mediana": round(float(y.median()), 2),
        f"{nombre}_target_min": int(y.min()),
        f"{nombre}_target_max": int(y.max()),
    }
