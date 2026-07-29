#!/usr/bin/env python3
"""
funcion reutilizable para cargar aplicar las transformaciones en RAW y cargar a STAGING.
"""

from config import (
    PROJECT_ID, DATASET_CONFIG, DATASET_RAW, DATASET_STAGING, FUENTE_STAGING,
)
from utilidades import UtilidadesGCP
from transformaciones import ejecutar_transformacion


def ejecutar_staging(nombre_archivo: str) -> int:
    
    util = UtilidadesGCP(project_id=PROJECT_ID)
    inicio = util.ahora_utc()

    filas_leidas = 0
    filas_insertadas = 0
    filas_rechazadas = 0

    try:
        # 1. Parametros
        params = util.obtener_parametros(nombre_archivo, dataset_config=DATASET_CONFIG)
        if params is None:
            raise RuntimeError(
                f"No hay configuracion para '{nombre_archivo}' en "
                f"{DATASET_CONFIG}.parametros_ingesta"
            )

        tabla_raw_rel = params.get("tabla_raw")
        tabla_staging_rel = params.get("tabla_staging")
        
        if not tabla_raw_rel:
            raise RuntimeError(f"'tabla_raw' vacio para '{nombre_archivo}'.")
        if not tabla_staging_rel:
            raise RuntimeError(f"'tabla_staging' vacio para '{nombre_archivo}'.")

        tabla_raw = util.normalizar_tabla(tabla_raw_rel, PROJECT_ID, DATASET_RAW)
        tabla_staging = util.normalizar_tabla(tabla_staging_rel, PROJECT_ID, DATASET_STAGING)

        tipo_extraccion = (params.get("tipo_extraccion") or "INCREMENTAL").strip().upper()
        columnas_llave_str = (params.get("columnas_llave") or "").strip()

        util.logger.info(
            "Config STAGING: %s -> %s [%s] llaves=%s",
            tabla_raw, tabla_staging, tipo_extraccion, columnas_llave_str or "N/A",
        )

        # 2.ejecutamos las transformaciones
        resultado = ejecutar_transformacion(
            bq_client=util.bq_client,
            tabla_raw=tabla_raw,
            tabla_staging=tabla_staging,
            tipo_extraccion=tipo_extraccion,
            columnas_llave_str=columnas_llave_str,
        )

        filas_leidas = resultado["filas_raw"]
        filas_insertadas = resultado["filas_staging"]
        filas_rechazadas = resultado["filas_descartadas"]

        # 3. Auditoria OK
        util.registrar_metadata(
            nombre_archivo=nombre_archivo, fuente=FUENTE_STAGING,
            fecha_hora_inicio=inicio, fecha_hora_fin=util.ahora_utc(),
            estado="OK", filas_leidas=filas_leidas,
            filas_insertadas=filas_insertadas, filas_rechazadas=filas_rechazadas,
        )
        util.logger.info(
            "STAGING completado: raw=%s, staging=%s, descartadas=%s",
            filas_leidas, filas_insertadas, filas_rechazadas,
        )
        return 0

    except Exception as exc:
        mensaje = f"{type(exc).__name__}: {exc}"
        util.logger.error("STAGING fallo '%s': %s", nombre_archivo, mensaje)
        util.registrar_metadata(
            nombre_archivo=nombre_archivo, fuente=FUENTE_STAGING,
            fecha_hora_inicio=inicio, fecha_hora_fin=util.ahora_utc(),
            estado="ERROR", filas_leidas=filas_leidas,
            filas_insertadas=filas_insertadas, filas_rechazadas=filas_rechazadas,
            mensaje_error=mensaje,
        )
        return 1
