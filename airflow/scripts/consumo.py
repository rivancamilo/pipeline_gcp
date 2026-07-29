"""
Consumption de transacciones: staging -> ml_features / ml_train / ml_test.

Lee la tabla staging (stg_transaccioneshabi), genera features derivadas,
asigna la particion train/test con corte temporal, y carga las tres tablas
de consumption:

    1. ml_features_transacciones  : todas las filas con features + split.
    2. ml_train_transacciones     : solo filas con split = 'train'.
    3. ml_test_transacciones      : solo filas con split = 'test'.

El split es aleatorio reproducible (FARM_FINGERPRINT sobre propiedad_id):
    - train: ~pct_train% de las filas (por defecto 80%)
    - test:  ~(100 - pct_train)% de las filas (por defecto 20%)

Todas las cargas usan MERGE sobre propiedad_id para ser idempotentes.

Dependencias:
    pip install google-cloud-bigquery
"""

import logging
from typing import Optional

from google.cloud import bigquery
from google.api_core import exceptions as gcp_exceptions


logger = logging.getLogger("consumption_transacciones")


# --------------------------------------------------------------------------- #
# Queries de transformacion
# --------------------------------------------------------------------------- #
def generar_query_features(
    tabla_staging: str,
    tabla_features: str,
    pct_train: int = 80,
    precio_min: int = 0,
) -> str:
    """
    contruimos el MERGE ml_features_transacciones desde staging.
    """
    sql = f"""
    MERGE `{tabla_features}` AS tgt
    USING (
        SELECT
            id                                          AS propiedad_id,

            -- Features categoricas
            ciudad,
            tipo,
            estado,

            -- Features numericas base
            area_m2,
            alcobas,
            banos,
            lat,
            lon,

            -- Features derivadas
            SAFE_DIVIDE(CAST(precio_cop AS FLOAT64), area_m2)
                                                        AS precio_por_m2,
            LN(CAST(precio_cop AS FLOAT64))             AS log_precio_cop,
            SAFE_DIVIDE(CAST(banos AS FLOAT64), CAST(alcobas AS FLOAT64))
                                                        AS banos_por_alcoba,
            SAFE_DIVIDE(area_m2, CAST(alcobas AS FLOAT64))
                                                        AS area_por_alcoba,
            EXTRACT(YEAR  FROM fecha)                   AS anio,
            EXTRACT(MONTH FROM fecha)                   AS mes,
            EXTRACT(QUARTER FROM fecha)                 AS trimestre,
            EXTRACT(DAYOFWEEK FROM fecha)               AS dia_semana,
            fecha,

            -- Target
            precio_cop,

            -- Split aleatorio reproducible (FARM_FINGERPRINT es deterministico)
            CASE
                WHEN MOD(ABS(FARM_FINGERPRINT(id)), 100) < {pct_train} THEN 'train'
                ELSE 'test'
            END                                         AS split

        FROM `{tabla_staging}`
        WHERE precio_cop >= {precio_min}
    ) AS src
    ON tgt.propiedad_id = src.propiedad_id

    WHEN MATCHED THEN UPDATE SET
        tgt.ciudad          = src.ciudad,
        tgt.tipo            = src.tipo,
        tgt.estado          = src.estado,
        tgt.area_m2         = src.area_m2,
        tgt.alcobas         = src.alcobas,
        tgt.banos           = src.banos,
        tgt.lat             = src.lat,
        tgt.lon             = src.lon,
        tgt.precio_por_m2   = src.precio_por_m2,
        tgt.log_precio_cop  = src.log_precio_cop,
        tgt.banos_por_alcoba= src.banos_por_alcoba,
        tgt.area_por_alcoba = src.area_por_alcoba,
        tgt.anio            = src.anio,
        tgt.mes             = src.mes,
        tgt.trimestre       = src.trimestre,
        tgt.dia_semana      = src.dia_semana,
        tgt.fecha           = src.fecha,
        tgt.precio_cop      = src.precio_cop,
        tgt.split           = src.split

    WHEN NOT MATCHED THEN INSERT (
        propiedad_id, ciudad, tipo, estado,
        area_m2, alcobas, banos, lat, lon,
        precio_por_m2, log_precio_cop, banos_por_alcoba, area_por_alcoba,
        anio, mes, trimestre, dia_semana, fecha,
        precio_cop, split
    )
    VALUES (
        src.propiedad_id, src.ciudad, src.tipo, src.estado,
        src.area_m2, src.alcobas, src.banos, src.lat, src.lon,
        src.precio_por_m2, src.log_precio_cop, src.banos_por_alcoba, src.area_por_alcoba,
        src.anio, src.mes, src.trimestre, src.dia_semana, src.fecha,
        src.precio_cop, src.split
    )

    WHEN NOT MATCHED BY SOURCE THEN DELETE;
    """
    return sql


def generar_query_split(
    tabla_features: str,
    tabla_destino: str,
    split_value: str,
) -> str:
    """
    contruimos el MERGE que materializa una tabla de split (train o test)
    a partir de ml_features_transacciones.
    """
    sql = f"""
    MERGE `{tabla_destino}` AS tgt
    USING (
        SELECT
            propiedad_id, ciudad, tipo, estado,
            area_m2, alcobas, banos, lat, lon,
            precio_por_m2, log_precio_cop, banos_por_alcoba, area_por_alcoba,
            anio, mes, trimestre, dia_semana, fecha,
            precio_cop
        FROM `{tabla_features}`
        WHERE split = '{split_value}'
    ) AS src
    ON tgt.propiedad_id = src.propiedad_id

    WHEN MATCHED THEN UPDATE SET
        tgt.ciudad          = src.ciudad,
        tgt.tipo            = src.tipo,
        tgt.estado          = src.estado,
        tgt.area_m2         = src.area_m2,
        tgt.alcobas         = src.alcobas,
        tgt.banos           = src.banos,
        tgt.lat             = src.lat,
        tgt.lon             = src.lon,
        tgt.precio_por_m2   = src.precio_por_m2,
        tgt.log_precio_cop  = src.log_precio_cop,
        tgt.banos_por_alcoba= src.banos_por_alcoba,
        tgt.area_por_alcoba = src.area_por_alcoba,
        tgt.anio            = src.anio,
        tgt.mes             = src.mes,
        tgt.trimestre       = src.trimestre,
        tgt.dia_semana      = src.dia_semana,
        tgt.fecha           = src.fecha,
        tgt.precio_cop      = src.precio_cop

    WHEN NOT MATCHED THEN INSERT (
        propiedad_id, ciudad, tipo, estado,
        area_m2, alcobas, banos, lat, lon,
        precio_por_m2, log_precio_cop, banos_por_alcoba, area_por_alcoba,
        anio, mes, trimestre, dia_semana, fecha,
        precio_cop
    )
    VALUES (
        src.propiedad_id, src.ciudad, src.tipo, src.estado,
        src.area_m2, src.alcobas, src.banos, src.lat, src.lon,
        src.precio_por_m2, src.log_precio_cop, src.banos_por_alcoba, src.area_por_alcoba,
        src.anio, src.mes, src.trimestre, src.dia_semana, src.fecha,
        src.precio_cop
    )

    WHEN NOT MATCHED BY SOURCE THEN DELETE;
    """
    return sql


# --------------------------------------------------------------------------- #
# Funcion principal
# --------------------------------------------------------------------------- #
def ejecutar_consumption(
    bq_client: bigquery.Client,
    tabla_staging: str,
    tabla_features: str,
    tabla_train: str,
    tabla_test: str,
    pct_train: int = 80,
    precio_min: int = 0,
) -> dict:
    """
    cargamos toda la informacion en las tres tablas de consumption.
    """
    resultado = {
        "filas_staging": 0,
        "filas_features": 0,
        "filas_train": 0,
        "filas_test": 0,
    }

    for tabla in [tabla_staging, tabla_features, tabla_train, tabla_test]:
        try:
            bq_client.get_table(tabla)
        except gcp_exceptions.NotFound:
            raise RuntimeError(f"La tabla '{tabla}' no existe. Debe crearse antes.")

    count = list(bq_client.query(
        f"SELECT COUNT(*) AS n FROM `{tabla_staging}`"
    ).result())
    resultado["filas_staging"] = count[0].n
    logger.info("Filas en staging: %s", resultado["filas_staging"])

    if resultado["filas_staging"] == 0:
        logger.warning("La tabla staging esta vacia. No hay nada que procesar.")
        return resultado

    # Paso 1: staging -> ml_features
    logger.info(
        "Generando features (split aleatorio: %s%% train / %s%% test) ...",
        pct_train, 100 - pct_train,
    )
    sql_features = generar_query_features(tabla_staging, tabla_features, pct_train, precio_min)
    try:
        job = bq_client.query(sql_features)
        job.result()
        logger.info("MERGE features completado. Filas afectadas: %s", job.num_dml_affected_rows)
    except gcp_exceptions.BadRequest as exc:
        raise RuntimeError(f"Error generando features: {exc}")
    except gcp_exceptions.GoogleAPICallError as exc:
        raise RuntimeError(f"Error de API generando features: {exc}")

    stats = list(bq_client.query(f"""
        SELECT COUNT(*) AS total, COUNTIF(split = 'train') AS n_train, COUNTIF(split = 'test') AS n_test
        FROM `{tabla_features}`
    """).result())
    resultado["filas_features"] = stats[0].total
    logger.info("Features: %s total (train=%s, test=%s)", stats[0].total, stats[0].n_train, stats[0].n_test)

    # Paso 2: ml_features -> ml_train
    logger.info("Materializando tabla train ...")
    try:
        job = bq_client.query(generar_query_split(tabla_features, tabla_train, "train"))
        job.result()
    except (gcp_exceptions.BadRequest, gcp_exceptions.GoogleAPICallError) as exc:
        raise RuntimeError(f"Error materializando train: {exc}")
    resultado["filas_train"] = list(bq_client.query(f"SELECT COUNT(*) AS n FROM `{tabla_train}`").result())[0].n

    # Paso 3: ml_features -> ml_test
    logger.info("Materializando tabla test ...")
    try:
        job = bq_client.query(generar_query_split(tabla_features, tabla_test, "test"))
        job.result()
    except (gcp_exceptions.BadRequest, gcp_exceptions.GoogleAPICallError) as exc:
        raise RuntimeError(f"Error materializando test: {exc}")
    resultado["filas_test"] = list(bq_client.query(f"SELECT COUNT(*) AS n FROM `{tabla_test}`").result())[0].n

    logger.info(
        "Consumption completado: features=%s, train=%s, test=%s",
        resultado["filas_features"], resultado["filas_train"], resultado["filas_test"],
    )
    return resultado
