"""
Centraliza la lógica de carga mediante estrategias, lo que facilita agregar nuevos 
tipos de procesamiento sin modificar el código existente.
Estrategias disponibles:
- FULL: Reemplaza todos los datos de la tabla destino.
- INCREMENTAL: Inserta únicamente los registros nuevos.
"""

import logging
from typing import Callable, Dict, List
from google.cloud import bigquery
from google.api_core import exceptions as gcp_exceptions


logger = logging.getLogger("carga")

# ------------------------------------------------------------------ #
# Registro de estrategias
# ------------------------------------------------------------------ #
_ESTRATEGIAS: Dict[str, Callable] = {}


def estrategia(nombre: str):
    """
    Creamos un decorador que registra una funcion como estrategia de carga.
    """
    def decorador(fn: Callable) -> Callable:
        _ESTRATEGIAS[nombre.upper()] = fn
        return fn
    return decorador


# ------------------------------------------------------------------ #
# Utilidades internas
# ------------------------------------------------------------------ #
def _columnas_datos(bq_client: bigquery.Client, tabla: str) -> List[str]:
    """
    Obtiene las columnas de la tabla que no tienen un valor por defecto 
    y que, se obtienen por el SELECT
    """
    t = bq_client.get_table(tabla)
    return [
        f.name for f in t.schema
        if not getattr(f, "default_value_expression", None)
    ]


def _validar_llaves(columnas_llave: List[str], columnas_datos: List[str]) -> None:
    """
    validamos que todas las columnas llave existan en la tabla destino
    """
    faltantes = [c for c in columnas_llave if c not in columnas_datos]
    if faltantes:
        raise ValueError(
            f"Las siguientes columnas_llave no existen en la tabla destino: {faltantes}"
        )


def _ejecutar_job(bq_client: bigquery.Client, sql: str, descripcion: str) -> bigquery.QueryJob:
    """
    ejecutamos un job de BigQuery y propaga errores con contexto
    """
    try:
        job = bq_client.query(sql)
        job.result()
        return job
    except gcp_exceptions.BadRequest as exc:
        raise RuntimeError(f"{descripcion} - Query invalida: {exc}") from exc
    except gcp_exceptions.GoogleAPICallError as exc:
        raise RuntimeError(f"{descripcion} - Error de API: {exc}") from exc


# ================================================================== #
#  ESTRATEGIAS DE CARGA
# ================================================================== #

@estrategia("FULL")
def _carga_full(
    bq_client: bigquery.Client,
    sql_fuente: str,
    tabla_staging: str,
    columnas_datos: List[str],
    **_,
) -> dict:
    """
    lo usamos para trunca la tabla destino y cargar todos los registros.
    """
    cols = ", ".join(columnas_datos)
    vals = ", ".join(f"src.{c}" for c in columnas_datos)

    logger.info("FULL | TRUNCATE TABLE `%s`", tabla_staging)
    _ejecutar_job(
        bq_client,
        f"TRUNCATE TABLE `{tabla_staging}`",
        "FULL - TRUNCATE",
    )

    sql_insert = f"""
        INSERT INTO `{tabla_staging}` ({cols})
        SELECT {cols} FROM ({sql_fuente}) AS src
    """
    logger.info("FULL | INSERT INTO `%s`", tabla_staging)
    job = _ejecutar_job(bq_client, sql_insert, "FULL - INSERT")

    filas = job.num_dml_affected_rows or 0
    logger.info("\tFilas insertadas: %s", filas)
    return {"filas_insertadas": filas, "filas_rechazadas": 0}


@estrategia("INCREMENTAL")
def _carga_incremental(
    bq_client: bigquery.Client,
    sql_fuente: str,
    tabla_staging: str,
    columnas_datos: List[str],
    columnas_llave: List[str],
    **_,
) -> dict:
    """
    lo usamos para insertar solo registros que no existen en la tabla destino.
    Construye dinamicamente la condicion ON del MERGE a partir de columnas_llave
    """
    if not columnas_llave:
        raise ValueError("INCREMENTAL requiere al menos una columna en columnas_llave.")

    _validar_llaves(columnas_llave, columnas_datos)

    on_cond = " AND ".join(f"tgt.{c} = src.{c}" for c in columnas_llave)
    cols     = ", ".join(columnas_datos)
    vals     = ", ".join(f"src.{c}" for c in columnas_datos)

    sql_merge = f"""
        MERGE `{tabla_staging}` AS tgt
        USING (
            {sql_fuente}
        ) AS src
        ON {on_cond}
        WHEN NOT MATCHED THEN
            INSERT ({cols})
            VALUES ({vals})
    """
    logger.info(
        "INCREMENTAL | MERGE `%s` ON (%s)",
        tabla_staging, ", ".join(columnas_llave),
    )
    job = _ejecutar_job(bq_client, sql_merge, "INCREMENTAL - MERGE")

    filas = job.num_dml_affected_rows or 0
    logger.info("\tFilas insertadas: %s", filas)
    return {"filas_insertadas": filas, "filas_rechazadas": 0}


@estrategia("UPSERT")
def _carga_upsert(
    bq_client: bigquery.Client,
    sql_fuente: str,
    tabla_staging: str,
    columnas_datos: List[str],
    columnas_llave: List[str],
    **_,
) -> dict:
    """
    lo usamos para actualizar registros existentes e inserta los nuevos.
    se construye dinamicamente:
      - ON condition  : columnas_llave
      - UPDATE SET    : todas las columnas que NO son llave
      - INSERT        : todas las columnas
    """
    if not columnas_llave:
        raise ValueError("UPSERT requiere al menos una columna en columnas_llave.")

    _validar_llaves(columnas_llave, columnas_datos)

    columnas_no_llave = [c for c in columnas_datos if c not in columnas_llave]
    if not columnas_no_llave:
        raise ValueError("UPSERT requiere al menos una columna fuera de columnas_llave para actualizar.")

    on_cond    = " AND ".join(f"tgt.{c} = src.{c}" for c in columnas_llave)
    update_set = ",\n            ".join(f"tgt.{c} = src.{c}" for c in columnas_no_llave)
    cols       = ", ".join(columnas_datos)
    vals       = ", ".join(f"src.{c}" for c in columnas_datos)

    sql_merge = f"""
        MERGE `{tabla_staging}` AS tgt
        USING (
            {sql_fuente}
        ) AS src
        ON {on_cond}
        WHEN MATCHED THEN UPDATE SET
            {update_set}
        WHEN NOT MATCHED THEN
            INSERT ({cols})
            VALUES ({vals})
    """
    logger.info(
        "UPSERT | MERGE `%s` ON (%s)",
        tabla_staging, ", ".join(columnas_llave),
    )
    job = _ejecutar_job(bq_client, sql_merge, "UPSERT - MERGE")

    filas = job.num_dml_affected_rows or 0
    logger.info("\tFilas afectadas (insertadas + actualizadas): %s", filas)
    return {"filas_insertadas": filas, "filas_rechazadas": 0}


# ================================================================== #
#  PUNTO DE ENTRADA PUBLICO
# ================================================================== #
def ejecutar_carga(
    bq_client: bigquery.Client,
    sql_fuente: str,
    tabla_staging: str,
    tipo_extraccion: str,
    columnas_llave_str: str = "",
) -> dict:
    tipo = (tipo_extraccion or "INCREMENTAL").strip().upper()

    if tipo not in _ESTRATEGIAS:
        disponibles = list(_ESTRATEGIAS.keys())
        raise ValueError(
            f"tipo_extraccion '{tipo}' no reconocido. "
            f"Estrategias disponibles: {disponibles}"
        )

    #Consultamos las columnas de la fuente
    cols_datos = _columnas_datos(bq_client, tabla_staging)

    #consultamos las llaves
    llaves = [c.strip() for c in (columnas_llave_str or "").split(",") if c.strip()]

    logger.info(
        "Ejecutando carga: tipo=%s | tabla=%s | llaves=%s",
        tipo, tabla_staging, llaves or "N/A",
    )

    return _ESTRATEGIAS[tipo](
        bq_client=bq_client,
        sql_fuente=sql_fuente,
        tabla_staging=tabla_staging,
        columnas_datos=cols_datos,
        columnas_llave=llaves,
    )
