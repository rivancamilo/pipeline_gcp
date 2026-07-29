"""
funcion para cargar CONSUMPTION (ML features y train/test).
"""

import os

from config import (
    PROJECT_ID, DATASET_CONFIG, DATASET_STAGING,
    DATASET_CONSUMPTION, FUENTE_CONSUMPTION, PCT_TRAIN,
    PRECIO_MIN_ENTRENAMIENTO,
)
from utilidades import UtilidadesGCP
from consumo import ejecutar_consumption
from validador_contratos import validar_contratos, ViolacionContratoError


_CONTRATOS_PATH = os.environ.get("CONTRATOS_PATH", "/opt/airflow/contratos")
_CONTRATOS_CONSUMPTION = [
    os.path.join(_CONTRATOS_PATH, "consumo", "ml_features_transacciones.yml"),
    os.path.join(_CONTRATOS_PATH, "consumo", "ml_train_transacciones.yml"),
    os.path.join(_CONTRATOS_PATH, "consumo", "ml_test_transacciones.yml"),
]


def ejecutar_consumption_paso(nombre_archivo: str) -> int:
    """
    Genera features y materializa train/test. Devuelve 0 si todo 
    esta bien o 1 si hay un error.
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

        tabla_staging_rel = params.get("tabla_staging")
        if not tabla_staging_rel:
            raise RuntimeError(f"'tabla_staging' vacio para '{nombre_archivo}'.")
        tabla_staging = util.normalizar_tabla(
            tabla_staging_rel, PROJECT_ID, DATASET_STAGING
        )

        # Tablas de consumption por rol
        tablas_consumption = params.get("tablas_consumption", [])
        if not tablas_consumption:
            raise RuntimeError(
                f"No hay tablas de consumption para '{nombre_archivo}'."
            )

        mapa_roles = {}
        for t in tablas_consumption:
            rol = (t.get("rol_tabla") or "").upper()
            nombre_tabla = t.get("tabla_consumption")
            if rol and nombre_tabla:
                mapa_roles[rol] = util.normalizar_tabla(
                    nombre_tabla, PROJECT_ID, DATASET_CONSUMPTION
                )

        tabla_features = mapa_roles.get("FEATURES")
        tabla_train = mapa_roles.get("TRAIN")
        tabla_test = mapa_roles.get("TEST")

        if not all([tabla_features, tabla_train, tabla_test]):
            faltantes = [r for r in ["FEATURES", "TRAIN", "TEST"] if r not in mapa_roles]
            raise RuntimeError(f"Faltan roles de consumption: {faltantes}.")

        util.logger.info(
            "Config CONSUMPTION: staging=%s -> features=%s, train=%s, test=%s (%s%%/%s%%)",
            tabla_staging, tabla_features, tabla_train, tabla_test,
            PCT_TRAIN, 100 - PCT_TRAIN,
        )

        # 2. Ejecutar consumption
        resultado = ejecutar_consumption(
            bq_client=util.bq_client,
            tabla_staging=tabla_staging,
            tabla_features=tabla_features,
            tabla_train=tabla_train,
            tabla_test=tabla_test,
            pct_train=PCT_TRAIN,
            precio_min=PRECIO_MIN_ENTRENAMIENTO,
        )

        filas_leidas = resultado["filas_staging"]
        filas_insertadas = resultado["filas_features"]

        # 3. Validar contratos de datos
        util.logger.info("Validando contratos de datos de consumption ...")
        validar_contratos(util.bq_client, _CONTRATOS_CONSUMPTION)
        util.logger.info("Todos los contratos de consumption pasaron.")

        # 4. Auditoria OK
        util.registrar_metadata(
            nombre_archivo=nombre_archivo, fuente=FUENTE_CONSUMPTION,
            fecha_hora_inicio=inicio, fecha_hora_fin=util.ahora_utc(),
            estado="OK", filas_leidas=filas_leidas,
            filas_insertadas=filas_insertadas, filas_rechazadas=0,
        )
        util.logger.info(
            "CONSUMPTION completado: features=%s, train=%s, test=%s",
            resultado["filas_features"], resultado["filas_train"], resultado["filas_test"],
        )
        return 0

    except Exception as exc:
        mensaje = f"{type(exc).__name__}: {exc}"
        util.logger.error("CONSUMPTION fallo '%s': %s", nombre_archivo, mensaje)
        util.registrar_metadata(
            nombre_archivo=nombre_archivo, fuente=FUENTE_CONSUMPTION,
            fecha_hora_inicio=inicio, fecha_hora_fin=util.ahora_utc(),
            estado="ERROR", filas_leidas=filas_leidas,
            filas_insertadas=filas_insertadas, filas_rechazadas=0,
            mensaje_error=mensaje,
        )
        return 1
