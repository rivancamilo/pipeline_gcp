#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Registro de modelos ML (patron Registry).

Para agregar un nuevo modelo basta con decorar una funcion con
@modelo("nombre") que reciba (params, features_num, features_cat)
y retorne un sklearn Pipeline listo para fit/predict.

No se requiere modificar ningun otro modulo.
"""

import logging
from typing import Callable, Dict, List

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


logger = logging.getLogger("registro_modelos")

_FABRICA: Dict[str, Callable] = {}


def modelo(nombre: str):
    """Decorador que registra una funcion como constructor de modelo."""
    def decorador(fn: Callable) -> Callable:
        _FABRICA[nombre.lower()] = fn
        return fn
    return decorador


# ------------------------------------------------------------------ #
# Preprocesador compartido
# ------------------------------------------------------------------ #
def _construir_preprocesador(
    features_num: List[str],
    features_cat: List[str],
) -> ColumnTransformer:
    """
    Pipeline de preprocesamiento:
      - Numericas : imputacion por mediana + StandardScaler
      - Categoricas: imputacion por constante + OneHotEncoder
    """
    num_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler",  StandardScaler()),
    ])
    cat_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="constant", fill_value="desconocido")),
        ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    return ColumnTransformer(
        transformers=[
            ("num", num_pipeline, features_num),
            ("cat", cat_pipeline, features_cat),
        ],
        remainder="drop",
    )


def _pipeline(estimador, features_num, features_cat) -> Pipeline:
    preprocesador = _construir_preprocesador(features_num, features_cat)
    return Pipeline([
        ("preprocesador", preprocesador),
        ("modelo", estimador),
    ])


# ================================================================== #
#  MODELOS REGISTRADOS
# ================================================================== #

@modelo("regresion_lineal")
def _crear_regresion_lineal(
    params: dict,
    features_num: List[str],
    features_cat: List[str],
) -> Pipeline:
    from sklearn.linear_model import LinearRegression
    return _pipeline(LinearRegression(**params), features_num, features_cat)


@modelo("arbol_decision")
def _crear_arbol_decision(
    params: dict,
    features_num: List[str],
    features_cat: List[str],
) -> Pipeline:
    from sklearn.tree import DecisionTreeRegressor
    return _pipeline(DecisionTreeRegressor(**params), features_num, features_cat)


@modelo("random_forest")
def _crear_random_forest(
    params: dict,
    features_num: List[str],
    features_cat: List[str],
) -> Pipeline:
    from sklearn.ensemble import RandomForestRegressor
    return _pipeline(RandomForestRegressor(**params), features_num, features_cat)


@modelo("xgboost")
def _crear_xgboost(
    params: dict,
    features_num: List[str],
    features_cat: List[str],
) -> Pipeline:
    from xgboost import XGBRegressor
    return _pipeline(XGBRegressor(**params), features_num, features_cat)


# ================================================================== #
#  API publica
# ================================================================== #

def crear_pipeline(
    nombre: str,
    params: dict,
    features_num: List[str],
    features_cat: List[str],
) -> Pipeline:
    """
    Crea y devuelve un Pipeline sklearn para el modelo solicitado.

    Lanza ValueError si el nombre no esta registrado.
    """
    clave = nombre.lower()
    if clave not in _FABRICA:
        disponibles = list(_FABRICA.keys())
        raise ValueError(
            f"Modelo '{nombre}' no registrado. Disponibles: {disponibles}"
        )
    pipeline = _FABRICA[clave](params, features_num, features_cat)
    logger.debug("Pipeline creado para '%s'.", nombre)
    return pipeline


def modelos_disponibles() -> List[str]:
    """Lista los nombres de modelos registrados."""
    return list(_FABRICA.keys())
