"""
Consultas a BigQuery: valores distintos para los selects del formulario.
Los resultados se cachean en memoria (con TTL) para no repetir queries.
"""
import logging
import os
import time
from typing import Dict, List, Tuple

from google.cloud import bigquery

from app.config import BQ_FEATURES_TABLE, GCP_PROJECT

logger = logging.getLogger("bigquery_service")

_BQ_CLIENT: bigquery.Client | None = None
# columna -> (valores, timestamp de carga). Nuevas ciudades/tipos pueden
# llegar en cualquier momento via el pipeline, asi que la cache vence.
_DISTINCT_CACHE: Dict[str, Tuple[List[str], float]] = {}
_CACHE_TTL_SEGUNDOS = 600  # 10 minutos


def _client() -> bigquery.Client:
    global _BQ_CLIENT
    if _BQ_CLIENT is None:
        _BQ_CLIENT = bigquery.Client(project=GCP_PROJECT)
    return _BQ_CLIENT


def get_distinct_values(column: str) -> List[str]:
    """SELECT DISTINCT {column} sobre ml_features_transacciones, ordenado A-Z."""
    cacheado = _DISTINCT_CACHE.get(column)
    if cacheado is not None:
        valores, cargado_en = cacheado
        if time.monotonic() - cargado_en < _CACHE_TTL_SEGUNDOS:
            return valores

    sql = (
        f"SELECT DISTINCT `{column}` "
        f"FROM `{BQ_FEATURES_TABLE}` "
        f"WHERE `{column}` IS NOT NULL "
        f"ORDER BY `{column}`"
    )
    logger.info("BQ DISTINCT %s ...", column)
    try:
        rows = _client().query(sql).result()
        values = [row[0] for row in rows]
        _DISTINCT_CACHE[column] = (values, time.monotonic())
        return values
    except Exception as exc:
        logger.error("Error en get_distinct_values(%s): %s", column, exc)
        raise
