#!/usr/bin/env python3
"""
Motor de validaciones de Data Contracts
Lee un contrato YAML, construye una unica query de validacion por tabla
todos los COUNTIF en un solo SELECT y lanza ViolacionContratoError si
alguna regla no se cumple.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple
import yaml
from google.cloud import bigquery


logger = logging.getLogger("validador_contratos")


class ViolacionContratoError(RuntimeError):
    """
    Lanzada cuando una o mas reglas del contrato no se cumplen.
    """


class ValidadorContrato:
    """
    Valida una tabla de BigQuery contra su contrato YAML.
    Ejecuta una sola query por tabla para minimizar llamadas a la API
    """

    _UNIDADES_A_HORAS: Dict[str, int] = {"h": 1, "d": 24, "w": 168}

    def __init__(self, bq_client: bigquery.Client, ruta_contrato: str) -> None:
        self.bq_client = bq_client
        self.ruta_contrato = ruta_contrato
        with open(ruta_contrato, "r", encoding="utf-8") as fh:
            self.contrato: Dict[str, Any] = yaml.safe_load(fh)
        self._tabla_fq: str = self.contrato["dataset"]

    # ------------------------------------------------------------------ #
    # API publica
    # ------------------------------------------------------------------ #
    def validar(self) -> Dict[str, Any]:
        """
        Ejecutamo todas las validaciones del contrato  y devuelve dict 
        con metricas si todo pasa en caso contrario Lanza ViolacionContratoError 
        con detalle de fallos si alguna regla falla
        """
        logger.info(
            "\tValidando contrato v%s | tabla='%s'",
            self.contrato.get("version", "?"), self._tabla_fq,
        )

        sql, alias_map = self._construir_query_validacion()
        try:
            row = list(self.bq_client.query(sql).result())[0]
        except Exception as exc:
            raise RuntimeError(
                f"Error ejecutando validacion para '{self._tabla_fq}': {exc}"
            ) from exc

        resultado = dict(row.items())
        errores: List[str] = []
        checks_ok = 0

        # --- row count ---
        total_rows = resultado.get("__total_rows", 0)
        min_rows = self.contrato.get("row_count", {}).get("min", 0)
        if total_rows < min_rows:
            errores.append(
                f"row_count: {total_rows} filas encontradas, minimo esperado {min_rows}"
            )
        else:
            checks_ok += 1
        logger.info("Total filas en '%s': %s", self._tabla_fq, total_rows)

        # --- freshness ---
        freshness = self.contrato.get("freshness", {})
        if freshness.get("timestamp_column") and freshness.get("max_age"):
            horas_datos = resultado.get("__freshness_hours")
            max_horas = self._max_age_a_horas(str(freshness["max_age"]))
            if horas_datos is None or horas_datos > max_horas:
                errores.append(
                    f"freshness: datos con {horas_datos}h de antiguedad, "
                    f"maximo permitido {max_horas}h ({freshness['max_age']})"
                )
            else:
                checks_ok += 1
                logger.info(
                    "Freshness OK: %sh de antiguedad (limite %sh)", horas_datos, max_horas
                )

        # --- restricciones de columnas ---
        for alias, descripcion in alias_map.items():
            valor = resultado.get(alias) or 0
            if valor > 0:
                errores.append(f"{descripcion}: {valor} fila(s) violan la regla")
            else:
                checks_ok += 1

        if errores:
            resumen = "\n  - ".join(errores)
            logger.error(
                "Contrato FALLIDO para '%s' (%s regla(s)):\n  - %s",
                self._tabla_fq, len(errores), resumen,
            )
            raise ViolacionContratoError(
                f"Contrato '{os.path.basename(self.ruta_contrato)}' "
                f"v{self.contrato.get('version', '?')} — "
                f"{len(errores)} regla(s) incumplida(s):\n  - {resumen}"
            )

        logger.info(
            "Contrato OK | tabla='%s' | %s checks pasaron.", self._tabla_fq, checks_ok
        )
        return {
            "tabla": self._tabla_fq,
            "version": self.contrato.get("version"),
            "total_rows": total_rows,
            "checks_ok": checks_ok,
            "errores": 0,
        }

    # ------------------------------------------------------------------ #
    # Construccion de la query de validacion
    # ------------------------------------------------------------------ #
    def _construir_query_validacion(self) -> Tuple[str, Dict[str, str]]:
        """
        Construye el SELECT que verifica TODAS las restricciones una sola vez
        """
        selects = ["COUNT(*) AS __total_rows"]
        alias_map: Dict[str, str] = {}

        freshness = self.contrato.get("freshness", {})
        if freshness.get("timestamp_column"):
            col = freshness["timestamp_column"]
            selects.append(
                f"TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(`{col}`), HOUR)"
                f" AS __freshness_hours"
            )

        for col_def in self.contrato.get("schema", []):
            col = col_def["name"]
            for constraint in col_def.get("constraints", []):
                alias, expr, desc = self._constraint_a_sql(col, constraint)
                if alias:
                    selects.append(f"{expr} AS {alias}")
                    alias_map[alias] = desc

        sql = (
            "SELECT\n"
            + ",\n".join(f"    {s}" for s in selects)
            + f"\nFROM `{self._tabla_fq}`"
        )
        return sql, alias_map

    @staticmethod
    def _constraint_a_sql(col: str, constraint: Any) -> Tuple[str, str, str]:
        """
        Convierte una restriccion YAML a (alias_sql, expresion_sql, descripcion)
        """
        safe = re.sub(r"[^a-zA-Z0-9]", "_", col)

        if constraint == "not_null":
            return (
                f"{safe}__not_null",
                f"COUNTIF(`{col}` IS NULL)",
                f"{col}: not_null",
            )

        if constraint == "unique":
            return (
                f"{safe}__unique",
                f"(COUNT(*) - COUNT(DISTINCT `{col}`))",
                f"{col}: unique",
            )

        if isinstance(constraint, dict):
            if "allowed_values" in constraint:
                vals = ", ".join(f"'{v}'" for v in constraint["allowed_values"])
                return (
                    f"{safe}__allowed_values",
                    f"COUNTIF(`{col}` IS NOT NULL AND `{col}` NOT IN ({vals}))",
                    f"{col}: valor no permitido (esperados: {constraint['allowed_values']})",
                )
            if "min" in constraint:
                v = constraint["min"]
                return (
                    f"{safe}__min",
                    f"COUNTIF(`{col}` < {v})",
                    f"{col} >= {v}",
                )
            if "max" in constraint:
                v = constraint["max"]
                return (
                    f"{safe}__max",
                    f"COUNTIF(`{col}` > {v})",
                    f"{col} <= {v}",
                )
            if "between" in constraint:
                a, b = constraint["between"]
                return (
                    f"{safe}__between",
                    f"COUNTIF(`{col}` NOT BETWEEN {a} AND {b})",
                    f"{col} entre [{a}, {b}]",
                )

        logger.warning("Restriccion no reconocida en '%s': %s", col, constraint)
        return "", "", ""

    @staticmethod
    def _max_age_a_horas(max_age: str) -> int:
        """
        Convierte '24h', '7d', '2w' a numero entero de horas
        """
        m = re.fullmatch(r"(\d+)([hdw])", max_age.strip().lower())
        if not m:
            raise ValueError(
                f"Formato de max_age invalido: '{max_age}'. Usar ej. '24h', '7d', '1w'."
            )
        return int(m.group(1)) * ValidadorContrato._UNIDADES_A_HORAS[m.group(2)]


# ------------------------------------------------------------------ #
# Funcion de conveniencia para multiples contratos
# ------------------------------------------------------------------ #
def validar_contratos(
    bq_client: bigquery.Client,
    rutas: List[str],
) -> List[Dict[str, Any]]:
    """
    Valida una lista de contratos en secuencia.
    Acumula TODOS los errores antes de lanzar la excepcion final,
    de modo que el log muestre todos los fallos de una sola vez
    """
    resultados: List[Dict[str, Any]] = []
    errores_globales: List[str] = []

    for ruta in rutas:
        try:
            resultados.append(ValidadorContrato(bq_client, ruta).validar())
        except ViolacionContratoError as exc:
            errores_globales.append(str(exc))
        except Exception as exc:
            errores_globales.append(f"Error inesperado validando '{ruta}': {exc}")

    if errores_globales:
        raise ViolacionContratoError(
            f"{len(errores_globales)} contrato(s) fallaron:\n\n"
            + "\n\n".join(errores_globales)
        )

    return resultados
