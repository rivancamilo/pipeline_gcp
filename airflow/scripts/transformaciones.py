#!/usr/bin/env python3
"""
funciones para aplicar las transformaciones de la capa RAW a STAGING
    Transformaciones aplicadas:
    1. Normalizacion de ciudades
    2. Casteo de tipos:
        - area_m2             STRING -> FLOAT64
        - alcobas, banos      STRING -> INT64
        - precio_cop           STRING -> INT64
        - lat, lon             STRING -> FLOAT64
        - fecha                STRING -> DATE
    3. Estandarizacion de texto:
        - tipo
        - estado
"""

import logging
from typing import Optional
from google.cloud import bigquery
from google.api_core import exceptions as gcp_exceptions
from carga import ejecutar_carga


logger = logging.getLogger("transformaciones")


# --------------------------------------------------------------------------- #
# Mapeo de ciudades
# --------------------------------------------------------------------------- #
MAPA_CIUDADES = {
    "BOGOTA":          "Bogota",
    "Bogota":          "Bogota",
    "Bogota D.C.":     "Bogota",
    "Bogotá":          "Bogota",
    "MEDELLIN":        "Medellin",
    "Medellin":        "Medellin",
    "Medellín":        "Medellin",
    "Cali":            "Cali",
    "Santiago de Cali": "Cali",
    "Barranquilla":    "Barranquilla",
    "B/quilla":        "Barranquilla",
}


def construir_case_ciudad() -> str:
    """
    generamos una expresion CASE WHEN para normalizar ciudades
    """
    lineas = []
    for variante, estandar in MAPA_CIUDADES.items():
        lineas.append(f"        WHEN ciudad = '{variante}' THEN '{estandar}'")
    return "\n".join(lineas)


# --------------------------------------------------------------------------- #
# construimos el select sin MERGE para hacer las transformaciones
# --------------------------------------------------------------------------- #
def generar_query_fuente(tabla_raw: str) -> str:
    """
    Construimos el SELECT que transforma raw a staging
    """
    case_ciudad = construir_case_ciudad()
    return f"""
        SELECT
            id,
            CASE
            {case_ciudad}
                ELSE INITCAP(TRIM(ciudad))
            END AS ciudad,
            INITCAP(TRIM(tipo))                                  AS tipo,
            SAFE_CAST(TRIM(area_m2) AS FLOAT64)                 AS area_m2,
            SAFE_CAST(TRIM(alcobas) AS INT64)                    AS alcobas,
            SAFE_CAST(TRIM(banos)   AS INT64)                    AS banos,
            SAFE_CAST(
                CAST(SAFE_CAST(TRIM(precio_cop) AS FLOAT64) AS INT64)
                AS INT64
            )                                                    AS precio_cop,
            SAFE_CAST(TRIM(lat) AS FLOAT64)                      AS lat,
            SAFE_CAST(TRIM(lon) AS FLOAT64)                      AS lon,
            SAFE_CAST(TRIM(fecha) AS DATE)                       AS fecha,
            LOWER(TRIM(estado))                                  AS estado
        FROM `{tabla_raw}`
        WHERE TRIM(COALESCE(precio_cop, '')) != ''
        QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY (SELECT NULL)) = 1
    """


# --------------------------------------------------------------------------- #
# Construimos el select de transformacion UPSERT completo
# --------------------------------------------------------------------------- #
def generar_query_transformacion(
    tabla_raw: str,
    tabla_staging: str,
) -> str:
    """
    construimos el SQL que transforma los datos de raw a staging usando MERGE
    para que no se duplique la informacion se se vuleve a ejecutar
    """
    case_ciudad = construir_case_ciudad()

    sql = f"""
    MERGE `{tabla_staging}` AS stg
    USING (
        -- QUALIFY deduplica por id manteniendo la fila mas reciente en raw
        SELECT
            id,
            CASE
            {case_ciudad}
                ELSE INITCAP(TRIM(ciudad))
            END AS ciudad,
            INITCAP(TRIM(tipo))                                  AS tipo,
            SAFE_CAST(TRIM(area_m2) AS FLOAT64)                 AS area_m2,
            SAFE_CAST(TRIM(alcobas) AS INT64)                    AS alcobas,
            SAFE_CAST(TRIM(banos)   AS INT64)                    AS banos,
            SAFE_CAST(
                CAST(SAFE_CAST(TRIM(precio_cop) AS FLOAT64) AS INT64)
                AS INT64
            )                                                    AS precio_cop,
            SAFE_CAST(TRIM(lat) AS FLOAT64)                      AS lat,
            SAFE_CAST(TRIM(lon) AS FLOAT64)                      AS lon,
            SAFE_CAST(TRIM(fecha) AS DATE)                       AS fecha,
            LOWER(TRIM(estado))                                  AS estado
        FROM `{tabla_raw}`
        WHERE TRIM(COALESCE(precio_cop, '')) != ''
        QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY (SELECT NULL)) = 1
    ) AS src
    ON stg.id = src.id
    -- Si el registro ya existe, se actualiza
    WHEN MATCHED THEN UPDATE SET
        stg.ciudad     = src.ciudad,
        stg.tipo       = src.tipo,
        stg.area_m2    = src.area_m2,
        stg.alcobas    = src.alcobas,
        stg.banos      = src.banos,
        stg.precio_cop = src.precio_cop,
        stg.lat        = src.lat,
        stg.lon        = src.lon,
        stg.fecha      = src.fecha,
        stg.estado     = src.estado
    -- Si no existe, se inserta
    WHEN NOT MATCHED THEN INSERT (
        id, ciudad, tipo, area_m2, alcobas, banos,
        precio_cop, lat, lon, fecha, estado
    )
    VALUES (
        src.id, src.ciudad, src.tipo, src.area_m2, src.alcobas, src.banos,
        src.precio_cop, src.lat, src.lon, src.fecha, src.estado
    );
    """
    return sql


# --------------------------------------------------------------------------- #
# Funcion principal para hacer la transformacion
# --------------------------------------------------------------------------- #
def ejecutar_transformacion(
    bq_client: bigquery.Client,
    tabla_raw: str,
    tabla_staging: str,
    tipo_extraccion: str = "INCREMENTAL",
    columnas_llave_str: str = "",
) -> dict:
    """
    Ejecutamos las transformacion de raw a staging y devolvemos un dic con las metricas
    """
    resultado = {
        "filas_raw": 0,
        "filas_staging": 0,
        "filas_descartadas": 0,
    }

    #Validamos que ambas tablas existan
    for tabla in [tabla_raw, tabla_staging]:
        try:
            bq_client.get_table(tabla)
        except gcp_exceptions.NotFound:
            raise RuntimeError(f"La tabla '{tabla}' no existe. Debe crearse antes.")

    #hacemos un conteo de filas
    counts = list(bq_client.query(f"""
        SELECT
            COUNT(*)                                         AS total,
            COUNTIF(TRIM(COALESCE(precio_cop, '')) = '')     AS sin_precio
        FROM `{tabla_raw}`
    """).result())
    resultado["filas_raw"] = counts[0].total
    resultado["filas_descartadas"] = counts[0].sin_precio
    
    logger.info(
        "Filas en raw: %s (con precio: %s, sin precio: %s -> se descartan)",
        resultado["filas_raw"],
        resultado["filas_raw"] - resultado["filas_descartadas"],
        resultado["filas_descartadas"],
    )

    if resultado["filas_raw"] == 0:
        logger.warning("La tabla raw esta vacia. No hay nada que transformar.")
        return resultado

    #Construimos el select 
    sql_fuente = generar_query_fuente(tabla_raw)
    logger.info(
        "Ejecutando transformacion raw - staging [%s] ...", tipo_extraccion
    )
    resultado_carga = ejecutar_carga(
        bq_client=bq_client,
        sql_fuente=sql_fuente,
        tabla_staging=tabla_staging,
        tipo_extraccion=tipo_extraccion,
        columnas_llave_str=columnas_llave_str,
    )

    resultado["filas_staging"] = resultado_carga["filas_insertadas"]
    logger.info(
        "Transformacion completada. Filas DML afectadas: %s",
        resultado["filas_staging"],
    )
    return resultado
