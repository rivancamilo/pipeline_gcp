#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calculo de metricas de evaluacion y validacion cruzada.
"""

import logging
from typing import Dict

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    mean_absolute_percentage_error,
    r2_score,
)
from sklearn.model_selection import KFold
from sklearn.pipeline import Pipeline


logger = logging.getLogger("evaluador")


def calcular_metricas(
    y_true: pd.Series,
    y_pred: np.ndarray,
    precio_min: float = 0,
) -> Dict[str, float]:
    """
    Calcula MAE, RMSE, R² y MAPE.

    MAPE se devuelve como porcentaje (0-100).
    Si precio_min > 0, el MAPE se calcula solo sobre filas donde
    y_true >= precio_min, evitando division por valores cercanos a cero.
    """
    mae  = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    r2   = float(r2_score(y_true, y_pred))

    if precio_min > 0:
        mask = np.asarray(y_true) >= precio_min
        n_excluidas = int((~mask).sum())
        if n_excluidas > 0:
            logger.debug(
                "MAPE: excluyendo %s filas con %s < %s",
                n_excluidas, "precio_cop", precio_min,
            )
        yt_mape = np.asarray(y_true)[mask]
        yp_mape = np.asarray(y_pred)[mask]
    else:
        yt_mape = np.asarray(y_true)
        yp_mape = np.asarray(y_pred)

    mape = (
        float(mean_absolute_percentage_error(yt_mape, yp_mape) * 100)
        if len(yt_mape) > 0
        else float("nan")
    )

    return {"MAE": mae, "RMSE": rmse, "R2": r2, "MAPE": mape}


def validacion_cruzada(
    pipeline: Pipeline,
    X: pd.DataFrame,
    y: pd.Series,
    cv: int = 5,
    random_state: int = 42,
    precio_min: float = 0,
) -> Dict[str, float]:
    """
    K-Fold cross-validation sobre el conjunto de entrenamiento.

    Clona el pipeline en cada fold para no contaminar el modelo final.
    Devuelve media y desviacion estandar de cada metrica.
    """
    kf = KFold(n_splits=cv, shuffle=True, random_state=random_state)
    resultados = {"MAE": [], "RMSE": [], "R2": [], "MAPE": []}

    for fold, (train_idx, val_idx) in enumerate(kf.split(X), start=1):
        X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]

        fold_pipeline = clone(pipeline)
        fold_pipeline.fit(X_tr, y_tr)
        y_pred = fold_pipeline.predict(X_val)

        metricas = calcular_metricas(y_val, y_pred, precio_min=precio_min)
        for k, v in metricas.items():
            resultados[k].append(v)

        logger.debug(
            "Fold %s/%s — MAE=%.0f  RMSE=%.0f  R2=%.4f  MAPE=%.2f%%",
            fold, cv,
            metricas["MAE"], metricas["RMSE"], metricas["R2"], metricas["MAPE"],
        )

    resumen: Dict[str, float] = {}
    for metrica, valores in resultados.items():
        resumen[f"cv_{metrica}_mean"] = float(np.mean(valores))
        resumen[f"cv_{metrica}_std"]  = float(np.std(valores))

    logger.info(
        "CV (%s-fold) — MAE=%.0f±%.0f  RMSE=%.0f±%.0f  R2=%.4f±%.4f  MAPE=%.2f±%.2f%%",
        cv,
        resumen["cv_MAE_mean"],  resumen["cv_MAE_std"],
        resumen["cv_RMSE_mean"], resumen["cv_RMSE_std"],
        resumen["cv_R2_mean"],   resumen["cv_R2_std"],
        resumen["cv_MAPE_mean"], resumen["cv_MAPE_std"],
    )
    return resumen


def imprimir_tabla_comparacion(resultados: Dict[str, Dict]) -> None:
    """Imprime tabla comparativa de metricas de test para todos los modelos."""
    encabezado = f"{'Modelo':<20} {'MAE':>15} {'RMSE':>15} {'R2':>8} {'MAPE':>10}"
    print("\n" + "=" * 72)
    print("  COMPARACION DE MODELOS (test set)")
    print("=" * 72)
    print(encabezado)
    print("-" * 72)
    for nombre, metricas in sorted(resultados.items(), key=lambda x: -x[1].get("R2", 0)):
        print(
            f"{nombre:<20} "
            f"{metricas['MAE']:>15,.0f} "
            f"{metricas['RMSE']:>15,.0f} "
            f"{metricas['R2']:>8.4f} "
            f"{metricas['MAPE']:>9.2f}%"
        )
    print("=" * 72 + "\n")
