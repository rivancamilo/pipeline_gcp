import io
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

import requests
from google.cloud import storage, bigquery
from google.api_core import exceptions as gcp_exceptions


class UtilidadesGCP:
    """
    metodos para interactuar con GCS y BigQuery
    """

    def __init__(
        self,
        project_id: str,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.project_id = project_id
        self.logger = logger or self._crear_logger()
        self._storage_client: Optional[storage.Client] = None
        self._bq_client: Optional[bigquery.Client] = None

    # ------------------------------------------------------------------ #
    # Utilidades generales
    # ------------------------------------------------------------------ #
    @staticmethod
    def _crear_logger() -> logging.Logger:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        return logging.getLogger("utilidades_gcp")

    @staticmethod
    def ahora_utc() -> datetime:
        """
        Timestamp actual en UTC
        """
        return datetime.now(timezone.utc)

    @staticmethod
    def normalizar_tabla(
        referencia: str, project_id: str, dataset_default: str = None
    ) -> str:
        """
        Normaliza una referencia de tabla a 'proyecto.dataset.tabla'
        """
        ref = (referencia or "").strip().strip("`")
        partes = ref.split(".")

        if len(partes) == 3:
            return ref
        if len(partes) == 2:
            return f"{project_id}.{ref}"
        if len(partes) == 1 and ref:
            if not dataset_default:
                raise RuntimeError(
                    f"La tabla '{referencia}' no incluye dataset y no se "
                    f"indico un dataset por defecto."
                )
            return f"{project_id}.{dataset_default}.{ref}"

        raise RuntimeError(
            f"Referencia de tabla invalida o vacia: '{referencia}'."
        )

    @staticmethod
    def _aplanar_dict(d: Dict[str, Any], prefijo: str = "", sep: str = "_") -> Dict[str, Any]:
        """
        convertimos un diccionario anidado a un solo nivel.
        Los valores escalares se convierten a texto.
        """
        out: Dict[str, Any] = {}
        for k, v in d.items():
            clave = f"{prefijo}{sep}{k}" if prefijo else k
            if isinstance(v, dict):
                out.update(UtilidadesGCP._aplanar_dict(v, clave, sep))
            elif isinstance(v, list):
                out[clave] = json.dumps(v, ensure_ascii=False)
            else:
                out[clave] = None if v is None else str(v)
        return out

    # ------------------------------------------------------------------ #
    # Clientes (lazy)
    # ------------------------------------------------------------------ #
    @property
    def storage_client(self) -> storage.Client:
        if self._storage_client is None:
            self._storage_client = storage.Client(project=self.project_id)
        return self._storage_client

    @property
    def bq_client(self) -> bigquery.Client:
        if self._bq_client is None:
            self._bq_client = bigquery.Client(project=self.project_id)
        return self._bq_client

    def obtener_bucket(self, bucket_name: str) -> storage.Bucket:
        """
        obtenemos el bucket validando que exista y sea accesible
        """
        try:
            bucket = self.storage_client.get_bucket(bucket_name)
            return bucket
        except gcp_exceptions.NotFound:
            raise RuntimeError(f"El bucket '{bucket_name}' no existe.")
        except gcp_exceptions.Forbidden:
            raise RuntimeError(f"Sin permisos para acceder al bucket '{bucket_name}'.")

    # ================================================================== #
    #  GOOGLE CLOUD STORAGE
    # ================================================================== #
    def buscar_archivo(
        self, bucket_name: str, prefix: str, nombre_archivo: str
    ) -> storage.Blob:
        """
        Busca un archivo dentro de un prefijo
        """
        ruta = f"{prefix}/{nombre_archivo}"
        self.logger.info("Buscando 'gs://%s/%s' ...", bucket_name, ruta)

        bucket = self.obtener_bucket(bucket_name)
        blob = bucket.blob(ruta)
        if not blob.exists():
            raise FileNotFoundError(
                f"No se encontro el archivo en gs://{bucket_name}/{ruta}"
            )
        self.logger.info("Archivo encontrado: gs://%s/%s", bucket_name, ruta)
        return blob

    def copiar_archivo(
        self, bucket_name: str, ruta_origen: str, ruta_destino: str
    ) -> storage.Blob:
        """
        Copia un objeto dentro del mismo bucket sin descargarlo
        """
        bucket = self.obtener_bucket(bucket_name)
        blob_origen = bucket.blob(ruta_origen)
        if not blob_origen.exists():
            raise FileNotFoundError(
                f"No existe el origen gs://{bucket_name}/{ruta_origen}"
            )
        try:
            blob_destino = bucket.copy_blob(blob_origen, bucket, ruta_destino)
            self.logger.info("Copiado: %s -> %s", ruta_origen, ruta_destino)
            return blob_destino
        except gcp_exceptions.GoogleAPICallError as exc:
            raise RuntimeError(
                f"Error copiando {ruta_origen} -> {ruta_destino}: {exc}"
            )

    def eliminar_archivo(self, bucket_name: str, ruta: str) -> None:
        """
        Elimina un objeto del bucket
        """
        bucket = self.obtener_bucket(bucket_name)
        blob = bucket.blob(ruta)
        try:
            blob.delete()
            self.logger.info("Eliminado: gs://%s/%s", bucket_name, ruta)
        except gcp_exceptions.NotFound:
            self.logger.warning(
                "No se pudo eliminar (no existe): gs://%s/%s", bucket_name, ruta
            )
        except gcp_exceptions.GoogleAPICallError as exc:
            raise RuntimeError(f"Error eliminando gs://{bucket_name}/{ruta}: {exc}")

    def mover_archivo(
        self, bucket_name: str, ruta_origen: str, ruta_destino: str
    ) -> storage.Blob:
        """
        Mueve un objeto dentro del mismo bucket
        """
        blob_destino = self.copiar_archivo(bucket_name, ruta_origen, ruta_destino)
        self.eliminar_archivo(bucket_name, ruta_origen)
        self.logger.info("Movido: %s -> %s", ruta_origen, ruta_destino)
        return blob_destino

    def descargar_texto(self, bucket_name: str, ruta: str) -> str:
        """
        descargamos el contenido de un objeto como texto
        """
        bucket = self.obtener_bucket(bucket_name)
        blob = bucket.blob(ruta)
        try:
            return blob.download_as_text()
        except gcp_exceptions.NotFound:
            raise FileNotFoundError(f"No existe gs://{bucket_name}/{ruta}")
        except gcp_exceptions.GoogleAPICallError as exc:
            raise RuntimeError(f"Error descargando gs://{bucket_name}/{ruta}: {exc}")

    def contar_filas_csv(
        self, bucket_name: str, ruta: str, skip_leading_rows: int = 1
    ) -> int:
        """
        Cuenta las filas de datos de un CSV descontando el encabezado.
        """
        contenido = self.descargar_texto(bucket_name, ruta)
        total = sum(1 for linea in contenido.splitlines() if linea.strip())
        filas = max(total - skip_leading_rows, 0)
        self.logger.info("Filas de datos en gs://%s/%s: %s", bucket_name, ruta, filas)
        return filas

    # ------------------------------------------------------------------ #
    # Carga de CSV a la capa RAW
    # ------------------------------------------------------------------ #
    def cargar_csv_a_raw(
        self,
        uri_gcs: str,
        tabla_destino: str,
        skip_leading_rows: int = 1,
        field_delimiter: str = ",",
        max_bad_records: int = 0,
        write_disposition: str = bigquery.WriteDisposition.WRITE_APPEND,
    ) -> int:
        """
        Carga un CSV desde GCS a una tabla de la capa RAW
        """
        if not (uri_gcs or "").startswith("gs://"):
            raise RuntimeError(
                f"URI de GCS invalida: '{uri_gcs}'. Debe empezar con 'gs://'."
            )

        try:
            tabla = self.bq_client.get_table(tabla_destino)
        except gcp_exceptions.NotFound:
            raise RuntimeError(
                f"La tabla destino '{tabla_destino}' no existe. Debe crearse antes."
            )

        schema_csv = [
            bigquery.SchemaField(f.name, f.field_type, mode=f.mode)
            for f in tabla.schema
            if getattr(f, "default_value_expression", None) is None
        ]
        columnas_default = [
            f.name for f in tabla.schema
            if getattr(f, "default_value_expression", None) is not None
        ]

        if not schema_csv:
            raise RuntimeError(
                f"La tabla '{tabla_destino}' no tiene columnas cargables."
            )

        self.logger.info(
            "Carga CSV - RAW: %s columna(s) del CSV, %s columna(s) por defecto (%s)",
            len(schema_csv), len(columnas_default),
            ", ".join(columnas_default) or "ninguna",
        )

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=skip_leading_rows,
            field_delimiter=field_delimiter,
            max_bad_records=max_bad_records,
            write_disposition=write_disposition,
            create_disposition=bigquery.CreateDisposition.CREATE_NEVER,
            schema=schema_csv,
            autodetect=False,
        )

        self.logger.info("Cargando (GCS) %s -> %s", uri_gcs, tabla_destino)
        try:
            job = self.bq_client.load_table_from_uri(
                uri_gcs, tabla_destino, job_config=job_config
            )
            job.result()
        except gcp_exceptions.BadRequest as exc:
            detalle = "; ".join(
                str(e.get("message", e)) for e in getattr(exc, "errors", []) or []
            )
            raise RuntimeError(f"Carga rechazada por BigQuery: {detalle or exc}")
        except gcp_exceptions.GoogleAPICallError as exc:
            raise RuntimeError(f"Error de API en la carga desde GCS: {exc}")

        if job.errors:
            raise RuntimeError(f"La carga finalizo con errores: {job.errors}")

        filas = job.output_rows or 0
        self.logger.info("Carga a RAW completada. Filas insertadas: %s", filas)
        return filas

    # ------------------------------------------------------------------ #
    # Carga de XML a la capa RAW
    # ------------------------------------------------------------------ #
    def cargar_xml_a_raw(
        self,
        bucket_name: str,
        ruta: str,
        tabla_destino: str,
        tag_registro: str = "observation",
        tag_grupo: Optional[str] = "country",
        attr_grupo: Optional[str] = "name",
        col_grupo: str = "country",
        attrs_raiz: Optional[Dict[str, str]] = None,
        write_disposition: str = bigquery.WriteDisposition.WRITE_APPEND,
    ) -> int:
        """
        Descargamos un XML de GCS lo aplana a filas y lo cargamos a una tabla RAW
        """
        attrs_raiz = attrs_raiz or {"unit": "unit"}

        try:
            tabla = self.bq_client.get_table(tabla_destino)
        except gcp_exceptions.NotFound:
            raise RuntimeError(
                f"La tabla destino '{tabla_destino}' no existe. Debe crearse antes."
            )

        xml_text = self.descargar_texto(bucket_name, ruta)
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise RuntimeError(f"XML mal formado en gs://{bucket_name}/{ruta}: {exc}")

        base = {col: root.get(attr) for attr, col in attrs_raiz.items()}
        filas: List[Dict[str, Any]] = []

        if tag_grupo:
            grupos = list(root.iter(tag_grupo))
            for grupo in grupos:
                valor_grupo = grupo.get(attr_grupo) if attr_grupo else None
                for reg in grupo.iter(tag_registro):
                    fila = dict(base)
                    if col_grupo:
                        fila[col_grupo] = valor_grupo
                    for hijo in reg:
                        fila[hijo.tag] = (hijo.text or "").strip()
                    filas.append(fila)
        else:
            for reg in root.iter(tag_registro):
                fila = dict(base)
                for hijo in reg:
                    fila[hijo.tag] = (hijo.text or "").strip()
                filas.append(fila)

        if not filas:
            raise RuntimeError(
                f"No se extrajo ninguna fila del XML "
                f"(tag_registro='{tag_registro}', tag_grupo='{tag_grupo}')."
            )

        self.logger.info(
            "XML aplanado: %s fila(s) extraidas de gs://%s/%s",
            len(filas), bucket_name, ruta,
        )

        schema_carga = [
            bigquery.SchemaField(f.name, f.field_type, mode=f.mode)
            for f in tabla.schema
            if getattr(f, "default_value_expression", None) is None
        ]

        buffer = io.BytesIO()
        for fila in filas:
            buffer.write((json.dumps(fila, ensure_ascii=False) + "\n").encode("utf-8"))
        buffer.seek(0)

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=write_disposition,
            create_disposition=bigquery.CreateDisposition.CREATE_NEVER,
            schema=schema_carga,
            ignore_unknown_values=True,
            autodetect=False,
        )

        self.logger.info("Cargando -> %s", tabla_destino)
        try:
            job = self.bq_client.load_table_from_file(
                buffer, tabla_destino, job_config=job_config
            )
            job.result()
        except gcp_exceptions.BadRequest as exc:
            detalle = "; ".join(
                str(e.get("message", e)) for e in getattr(exc, "errors", []) or []
            )
            raise RuntimeError(f"Carga XML rechazada por BigQuery: {detalle or exc}")
        except gcp_exceptions.GoogleAPICallError as exc:
            raise RuntimeError(f"Error de API en la carga del XML: {exc}")

        if job.errors:
            raise RuntimeError(f"La carga finalizo con errores: {job.errors}")

        n = job.output_rows or len(filas)
        self.logger.info("Carga XML a RAW completada. Filas insertadas: %s", n)
        return n

    # ------------------------------------------------------------------ #
    # Carga de JSON paginado a la capa RAW
    # ------------------------------------------------------------------ #
    def seguir_paginacion(
        self,
        bucket_name: str,
        ruta_inicial: str,
        meta_path: str = "meta",
        next_field: str = "next",
    ) -> List[str]:
        """
        Devuelve la lista ordenada de rutas de todas las paginas.
        """
        prefijo = ruta_inicial.rsplit("/", 1)[0] if "/" in ruta_inicial else ""
        rutas: List[str] = []
        actual: Optional[str] = ruta_inicial
        visitados = set()

        while actual and actual not in visitados:
            visitados.add(actual)
            rutas.append(actual)
            texto = self.descargar_texto(bucket_name, actual)
            try:
                obj = json.loads(texto)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"JSON invalido en gs://{bucket_name}/{actual}: {exc}"
                )
            meta = obj.get(meta_path) or {}
            siguiente = meta.get(next_field)
            actual = (f"{prefijo}/{siguiente}" if prefijo else siguiente) if siguiente else None

        self.logger.info("Paginacion: %s pagina(s) desde '%s'.", len(rutas), ruta_inicial)
        return rutas

    def cargar_json_paginado_a_raw(
        self,
        bucket_name: str,
        ruta_inicial: str,
        tabla_destino: str,
        data_path: str = "data",
        meta_path: str = "meta",
        next_field: str = "next",
        sep: str = "_",
        write_disposition: str = bigquery.WriteDisposition.WRITE_APPEND,
    ) -> int:
        """
        Cargamos a RAW un conjunto de JSON paginados al estilo de una API
        """
        try:
            tabla = self.bq_client.get_table(tabla_destino)
        except gcp_exceptions.NotFound:
            raise RuntimeError(
                f"La tabla destino '{tabla_destino}' no existe. Debe crearse antes."
            )

        prefijo = ruta_inicial.rsplit("/", 1)[0] if "/" in ruta_inicial else ""
        filas: List[Dict[str, Any]] = []
        ruta_actual: Optional[str] = ruta_inicial
        visitados = set()
        n_paginas = 0

        while ruta_actual and ruta_actual not in visitados:
            visitados.add(ruta_actual)
            texto = self.descargar_texto(bucket_name, ruta_actual)
            try:
                obj = json.loads(texto)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"JSON invalido en gs://{bucket_name}/{ruta_actual}: {exc}"
                )

            registros = obj.get(data_path)
            if registros is None:
                raise RuntimeError(
                    f"La pagina '{ruta_actual}' no tiene el campo de datos '{data_path}'."
                )
            for reg in registros:
                filas.append(self._aplanar_dict(reg, sep=sep))

            n_paginas += 1
            meta = obj.get(meta_path) or {}
            siguiente = meta.get(next_field)
            ruta_actual = (f"{prefijo}/{siguiente}" if prefijo else siguiente) if siguiente else None

        if not filas:
            raise RuntimeError(
                f"No se extrajo ningun registro de la paginacion iniciada en '{ruta_inicial}'."
            )

        self.logger.info(
            "JSON paginado: %s pagina(s), %s registro(s) en total.",
            n_paginas, len(filas),
        )

        schema_carga = [
            bigquery.SchemaField(f.name, f.field_type, mode=f.mode)
            for f in tabla.schema
            if getattr(f, "default_value_expression", None) is None
        ]

        buffer = io.BytesIO()
        for fila in filas:
            buffer.write((json.dumps(fila, ensure_ascii=False) + "\n").encode("utf-8"))
        buffer.seek(0)

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=write_disposition,
            create_disposition=bigquery.CreateDisposition.CREATE_NEVER,
            schema=schema_carga,
            ignore_unknown_values=True,
            autodetect=False,
        )

        self.logger.info("Cargando (JSON paginado -> NDJSON) -> %s", tabla_destino)
        try:
            job = self.bq_client.load_table_from_file(
                buffer, tabla_destino, job_config=job_config
            )
            job.result()
        except gcp_exceptions.BadRequest as exc:
            detalle = "; ".join(
                str(e.get("message", e)) for e in getattr(exc, "errors", []) or []
            )
            raise RuntimeError(f"Carga JSON rechazada por BigQuery: {detalle or exc}")
        except gcp_exceptions.GoogleAPICallError as exc:
            raise RuntimeError(f"Error de API en la carga del JSON: {exc}")

        if job.errors:
            raise RuntimeError(f"La carga finalizo con errores: {job.errors}")

        n = job.output_rows or len(filas)
        self.logger.info("Carga JSON paginado a RAW completada. Filas: %s", n)
        return n

    # ------------------------------------------------------------------ #
    # Carga de una API REST paginada
    # ------------------------------------------------------------------ #
    def obtener_pagina_api_soda(
        self,
        url_base: str,
        limit_pagina: int,
        offset: int,
        app_token: Optional[str] = None,
        parametros_extra: Optional[Dict[str, str]] = None,
        timeout: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene una sola pagina de una API REST paginada devuelve la lista de
        registros de esa pagina
        """
        query: Dict[str, Any] = {"$limit": limit_pagina, "$offset": offset}
        if parametros_extra:
            query.update(parametros_extra)
        headers = {"X-App-Token": app_token} if app_token else None

        try:
            resp = requests.get(url_base, params=query, headers=headers, timeout=timeout)
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                f"Error consultando '{url_base}' (limit={limit_pagina}, offset={offset}): {exc}"
            )

        try:
            datos = resp.json()
        except ValueError as exc:
            raise RuntimeError(f"Respuesta no es JSON valido de '{url_base}': {exc}")

        if not isinstance(datos, list):
            raise RuntimeError(
                f"Respuesta inesperada de '{url_base}': se esperaba una lista de registros."
            )
        return datos

    def cargar_api_soda_paginada_a_raw(
        self,
        url_base: str,
        tabla_destino: str,
        limit_pagina: int = 1000,
        app_token: Optional[str] = None,
        parametros_extra: Optional[Dict[str, str]] = None,
        sep: str = "_",
        write_disposition: str = bigquery.WriteDisposition.WRITE_APPEND,
    ) -> int:
        """
        Consume por completo una API REST paginada $limit/$offset 
        y carga todos los registros obtenidos a una tabla RAW 
        """
        try:
            tabla = self.bq_client.get_table(tabla_destino)
        except gcp_exceptions.NotFound:
            raise RuntimeError(
                f"La tabla destino '{tabla_destino}' no existe. Debe crearse antes."
            )

        filas: List[Dict[str, Any]] = []
        offset = 0
        n_paginas = 0

        while True:
            registros = self.obtener_pagina_api_soda(
                url_base, limit_pagina, offset,
                app_token=app_token, parametros_extra=parametros_extra,
            )
            n_paginas += 1
            self.logger.info(
                "Pagina %s: %s registro(s) (limit=%s, offset=%s) de '%s'",
                n_paginas, len(registros), limit_pagina, offset, url_base,
            )

            if not registros:
                break
            for reg in registros:
                filas.append(self._aplanar_dict(reg, sep=sep))

            if len(registros) < limit_pagina:
                break
            offset += limit_pagina

        if not filas:
            raise RuntimeError(f"La API '{url_base}' no devolvio ningun registro.")

        self.logger.info(
            "API paginada: %s pagina(s), %s registro(s) en total desde '%s'.",
            n_paginas, len(filas), url_base,
        )

        schema_carga = [
            bigquery.SchemaField(f.name, f.field_type, mode=f.mode)
            for f in tabla.schema
            if getattr(f, "default_value_expression", None) is None
        ]

        buffer = io.BytesIO()
        for fila in filas:
            buffer.write((json.dumps(fila, ensure_ascii=False) + "\n").encode("utf-8"))
        buffer.seek(0)

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=write_disposition,
            create_disposition=bigquery.CreateDisposition.CREATE_NEVER,
            schema=schema_carga,
            ignore_unknown_values=True,
            autodetect=False,
        )

        self.logger.info("Cargando (API SODA -> NDJSON) -> %s", tabla_destino)
        try:
            job = self.bq_client.load_table_from_file(
                buffer, tabla_destino, job_config=job_config
            )
            job.result()
        except gcp_exceptions.BadRequest as exc:
            detalle = "; ".join(
                str(e.get("message", e)) for e in getattr(exc, "errors", []) or []
            )
            raise RuntimeError(f"Carga API rechazada por BigQuery: {detalle or exc}")
        except gcp_exceptions.GoogleAPICallError as exc:
            raise RuntimeError(f"Error de API en la carga desde la API REST: {exc}")

        if job.errors:
            raise RuntimeError(f"La carga finalizo con errores: {job.errors}")

        n = job.output_rows or len(filas)
        self.logger.info("Carga API a RAW completada. Filas insertadas: %s", n)
        return n

    def ejecutar_query(
        self,
        sql: str,
        parametros: Optional[List[bigquery.ScalarQueryParameter]] = None,
    ) -> bigquery.table.RowIterator:
        """
        Ejecuta una query y devuelve el resultado
        """
        job_config = bigquery.QueryJobConfig()
        if parametros:
            job_config.query_parameters = parametros

        self.logger.info("Ejecutando query en BigQuery ...")
        try:
            query_job = self.bq_client.query(sql, job_config=job_config)
            return query_job.result()
        except gcp_exceptions.BadRequest as exc:
            raise RuntimeError(f"Query invalida: {exc}")
        except gcp_exceptions.GoogleAPICallError as exc:
            raise RuntimeError(f"Error de API ejecutando query: {exc}")

    def insertar_filas(
        self, tabla: str, filas: List[Dict[str, Any]]
    ) -> None:
        """
        Inserta filas
        """
        try:
            errores = self.bq_client.insert_rows_json(tabla, filas)
            if errores:
                self.logger.error("Errores insertando en %s: %s", tabla, errores)
                raise RuntimeError(f"insert_rows_json devolvio errores: {errores}")
            self.logger.info("%s fila(s) insertadas en %s", len(filas), tabla)
        except gcp_exceptions.GoogleAPICallError as exc:
            raise RuntimeError(f"Error de API insertando en {tabla}: {exc}")

    # ------------------------------------------------------------------ #
    # Tabla de parametros
    # ------------------------------------------------------------------ #
    def obtener_parametros(
        self,
        nombre_archivo: str,
        dataset_config: str = "config",
        solo_activos: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Lee la configuracion de las dos tablas de parametros
        """
        tabla_ingesta = f"{self.project_id}.{dataset_config}.parametros_ingesta"
        tabla_consumption = f"{self.project_id}.{dataset_config}.parametros_consumption"

        sql_ingesta = f"""
            SELECT
                nombre_archivo, tipo_archivo, tabla_raw, tabla_staging,
                tipo_analisis, tipo_extraccion, columnas_llave,
                url_api, limit_pagina
            FROM `{tabla_ingesta}`
            WHERE nombre_archivo = @nombre_archivo
            LIMIT 1
        """
        parametros = [
            bigquery.ScalarQueryParameter("nombre_archivo", "STRING", nombre_archivo)
        ]
        filas = list(self.ejecutar_query(sql_ingesta, parametros))
        if not filas:
            self.logger.warning(
                "No hay parametros para '%s' en %s", nombre_archivo, tabla_ingesta
            )
            return None

        config = dict(filas[0].items())

        filtro_activo = "AND activo = TRUE" if solo_activos else ""
        sql_consumption = f"""
            SELECT tabla_consumption, rol_tabla, estrategia, clave, orden_carga
            FROM `{tabla_consumption}`
            WHERE nombre_archivo = @nombre_archivo
            {filtro_activo}
            ORDER BY orden_carga
        """
        filas_c = list(self.ejecutar_query(sql_consumption, parametros))
        config["tablas_consumption"] = [dict(f.items()) for f in filas_c]

        self.logger.info(
            "Parametros cargados para '%s' (%s tabla(s) de consumption).",
            nombre_archivo, len(config["tablas_consumption"]),
        )
        return config

    # ------------------------------------------------------------------ #
    # Tabla de metadata / auditoria
    # ------------------------------------------------------------------ #
    def registrar_metadata(
        self,
        nombre_archivo: str,
        fuente: str,
        fecha_hora_inicio: datetime,
        fecha_hora_fin: datetime,
        estado: str,
        filas_leidas: int = 0,
        filas_insertadas: int = 0,
        filas_rechazadas: int = 0,
        mensaje_error: Optional[str] = None,
        tabla_metadata: str = None,
    ) -> None:
        """
        Inserta un registro de auditoria en la tabla de metadata
        """
        tabla = tabla_metadata or f"{self.project_id}.metadata.ingestion_files"
        fila = {
            "nombre_archivo": nombre_archivo,
            "fuente": fuente,
            "fecha_hora_inicio": fecha_hora_inicio.isoformat(),
            "fecha_hora_fin": fecha_hora_fin.isoformat(),
            "estado": estado,
            "filas_leidas": filas_leidas,
            "filas_insertadas": filas_insertadas,
            "filas_rechazadas": filas_rechazadas,
            "mensaje_error": mensaje_error[:1024] if mensaje_error else None,
        }
        try:
            self.insertar_filas(tabla, [fila])
            self.logger.info("Metadata registrada (estado=%s).", estado)
        except Exception as exc:
            self.logger.error("No se pudo registrar la metadata: %s", exc)
