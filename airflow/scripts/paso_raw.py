#!/usr/bin/env python3
"""
funcion reutilizable para carga de archivos a la capa RAW
"""

from config import (
    PROJECT_ID, BUCKET_NAME,
    PREFIX_LANDING, PREFIX_PROCESSING, PREFIX_PROCESSED,
    DATASET_CONFIG, DATASET_RAW, FUENTE_RAW,
)
from utilidades import UtilidadesGCP


def ejecutar_raw(nombre_archivo: str) -> int:
    util = UtilidadesGCP(project_id=PROJECT_ID)
    inicio = util.ahora_utc()

    filas_leidas = 0
    filas_insertadas = 0
    filas_rechazadas = 0

    try:
        # 1. Obtenemos los Parametros
        params = util.obtener_parametros(nombre_archivo, dataset_config=DATASET_CONFIG)
        if params is None:
            raise RuntimeError(
                f"No hay configuracion para '{nombre_archivo}' en "
                f"{DATASET_CONFIG}.parametros_ingesta"
            )

        tipo_archivo = (params.get("tipo_archivo") or "").upper()
        tabla_raw_rel = params.get("tabla_raw")
        if not tabla_raw_rel:
            raise RuntimeError(f"'tabla_raw' vacio para '{nombre_archivo}'.")

        tabla_raw = util.normalizar_tabla(tabla_raw_rel, PROJECT_ID, DATASET_RAW)

        util.logger.info(
            "Config RAW: archivo=%s tipo=%s -> %s", nombre_archivo, tipo_archivo, tabla_raw
        )

        if tipo_archivo not in ("CSV", "XML", "JSON"):
            raise RuntimeError(
                f"Tipo '{tipo_archivo}' no soportado. Se admite CSV, XML o JSON."
            )

        # 2. Buscamos los archivos en en la carpeta landing
        util.buscar_archivo(BUCKET_NAME, PREFIX_LANDING, nombre_archivo)
        ruta_landing = f"{PREFIX_LANDING}/{nombre_archivo}"

        if tipo_archivo == "JSON":
            rutas_landing = util.seguir_paginacion(BUCKET_NAME, ruta_landing)
        else:
            rutas_landing = [ruta_landing]

        # 3. movemos los archivos de la carpeta landing a processing
        rutas_processing = []
        for r in rutas_landing:
            nombre = r.split("/")[-1]
            destino = f"{PREFIX_PROCESSING}/{nombre}"
            util.mover_archivo(BUCKET_NAME, r, destino)
            rutas_processing.append(destino)

        ruta_processing = rutas_processing[0]

        # 4. Cargamos a RAW segun el tipo de fuente
        if tipo_archivo == "CSV":
            filas_leidas = util.contar_filas_csv(BUCKET_NAME, ruta_processing)
            uri_gcs = f"gs://{BUCKET_NAME}/{ruta_processing}"
            filas_insertadas = util.cargar_csv_a_raw(
                uri_gcs=uri_gcs, tabla_destino=tabla_raw,
                skip_leading_rows=1, field_delimiter=",",
                write_disposition="WRITE_APPEND",
            )
        elif tipo_archivo == "XML":
            filas_insertadas = util.cargar_xml_a_raw(
                bucket_name=BUCKET_NAME, ruta=ruta_processing,
                tabla_destino=tabla_raw, write_disposition="WRITE_APPEND",
            )
            filas_leidas = filas_insertadas
        else:  # JSON
            filas_insertadas = util.cargar_json_paginado_a_raw(
                bucket_name=BUCKET_NAME, ruta_inicial=ruta_processing,
                tabla_destino=tabla_raw, write_disposition="WRITE_APPEND",
            )
            filas_leidas = filas_insertadas

        filas_rechazadas = max(filas_leidas - filas_insertadas, 0)

        # 5. Movemos el archivo de processing a processed
        for r in rutas_processing:
            nombre = r.split("/")[-1]
            util.mover_archivo(BUCKET_NAME, r, f"{PREFIX_PROCESSED}/{nombre}")

        # 6. registramos la info en auditoria
        util.registrar_metadata(
            nombre_archivo=nombre_archivo, fuente=FUENTE_RAW,
            fecha_hora_inicio=inicio, fecha_hora_fin=util.ahora_utc(),
            estado="OK", filas_leidas=filas_leidas,
            filas_insertadas=filas_insertadas, filas_rechazadas=filas_rechazadas,
        )
        util.logger.info("RAW completado: %s", nombre_archivo)
        return 0

    except Exception as exc:
        mensaje = f"{type(exc).__name__}: {exc}"
        util.logger.error("RAW fallo '%s': %s", nombre_archivo, mensaje)
        util.registrar_metadata(
            nombre_archivo=nombre_archivo, fuente=FUENTE_RAW,
            fecha_hora_inicio=inicio, fecha_hora_fin=util.ahora_utc(),
            estado="ERROR", filas_leidas=filas_leidas,
            filas_insertadas=filas_insertadas, filas_rechazadas=filas_rechazadas,
            mensaje_error=mensaje,
        )
        return 1
