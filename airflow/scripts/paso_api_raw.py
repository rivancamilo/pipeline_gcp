#!/usr/bin/env python3
"""
funcion para cargar a la capa RAW consumiendo una API REST paginada
bajo el estandar SODA
"""

from config import PROJECT_ID, DATASET_CONFIG, DATASET_RAW, FUENTE_RAW, SODA_APP_TOKEN
from utilidades import UtilidadesGCP

LIMIT_PAGINA_DEFAULT = 1000


def ejecutar_api_raw(nombre_archivo: str) -> int:
    """
    Consume una API REST paginada y carga todos los registros 
    disponibles a la capa RAW. Devuelve 0 si toda esta bien o 1 si hay un error.
    """
    util = UtilidadesGCP(project_id=PROJECT_ID)
    inicio = util.ahora_utc()

    filas_leidas = 0
    filas_insertadas = 0

    try:
        # 1. Parametros
        params = util.obtener_parametros(nombre_archivo, dataset_config=DATASET_CONFIG)
        if params is None:
            raise RuntimeError(
                f"No hay configuracion para '{nombre_archivo}' en "
                f"{DATASET_CONFIG}.parametros_ingesta"
            )

        tipo_archivo = (params.get("tipo_archivo") or "").upper()
        if tipo_archivo != "API":
            raise RuntimeError(
                f"Tipo '{tipo_archivo}' no soportado por este paso. Se admite API."
            )

        url_api = params.get("url_api")
        if not url_api:
            raise RuntimeError(f"'url_api' vacio para '{nombre_archivo}'.")

        tabla_raw_rel = params.get("tabla_raw")
        if not tabla_raw_rel:
            raise RuntimeError(f"'tabla_raw' vacio para '{nombre_archivo}'.")
        tabla_raw = util.normalizar_tabla(tabla_raw_rel, PROJECT_ID, DATASET_RAW)

        limit_pagina = int(params.get("limit_pagina") or LIMIT_PAGINA_DEFAULT)

        util.logger.info(
            "Config API RAW: fuente=%s url=%s limit_pagina=%s -> %s",
            nombre_archivo, url_api, limit_pagina, tabla_raw,
        )

        # 2. Consumir la API
        filas_insertadas = util.cargar_api_soda_paginada_a_raw(
            url_base=url_api,
            tabla_destino=tabla_raw,
            limit_pagina=limit_pagina,
            app_token=SODA_APP_TOKEN,
            write_disposition="WRITE_APPEND",
        )
        filas_leidas = filas_insertadas

        # 3. Auditoria OK
        util.registrar_metadata(
            nombre_archivo=nombre_archivo, fuente=FUENTE_RAW,
            fecha_hora_inicio=inicio, fecha_hora_fin=util.ahora_utc(),
            estado="OK", filas_leidas=filas_leidas,
            filas_insertadas=filas_insertadas,
            filas_rechazadas=max(filas_leidas - filas_insertadas, 0),
        )
        util.logger.info("RAW (API) completado: %s", nombre_archivo)
        return 0

    except Exception as exc:
        mensaje = f"{type(exc).__name__}: {exc}"
        util.logger.error("RAW (API) fallo '%s': %s", nombre_archivo, mensaje)
        util.registrar_metadata(
            nombre_archivo=nombre_archivo, fuente=FUENTE_RAW,
            fecha_hora_inicio=inicio, fecha_hora_fin=util.ahora_utc(),
            estado="ERROR", filas_leidas=filas_leidas,
            filas_insertadas=filas_insertadas,
            filas_rechazadas=max(filas_leidas - filas_insertadas, 0),
            mensaje_error=mensaje,
        )
        return 1
