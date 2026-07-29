#!/usr/bin/env python3
"""
Pruebas unitarias de transformaciones.py (raw -> staging de
co_transacciones_habi.csv).

Los 6 casos cubren las reglas de negocio detectadas con evidencia de datos
en pipeline_gcp/EDA/EDA.ipynb (Seccion 2): normalizacion de ciudad, descarte
de precio nulo, deduplicacion por id, casteo de tipos y normalizacion de
texto. Solo se prueban construir_case_ciudad() y generar_query_fuente(),
que son generacion pura de SQL (sin BigQuery real), por lo que no requieren
credenciales de GCP ni mocks.

Ejecutar (con las dependencias de requirements.txt + requirements-dev.txt
instaladas, p. ej. dentro del contenedor de airflow):
    PYTHONPATH=/opt/airflow/scripts pytest /opt/airflow/scripts/tests
"""

from transformaciones import construir_case_ciudad, generar_query_fuente

TABLA_RAW = "pruebahabi.raw.raw_transaccioneshabi"


def test_normaliza_variantes_de_ciudad_mapeadas():
    """
    EDA 2.1: de las 13 variantes de ciudad en raw, 11 (Bogota, Medellin,
    Cali, Barranquilla) tienen mas de una forma de escritura y deben
    normalizarse a un unico nombre.
    """
    case_ciudad = construir_case_ciudad()
    casos = {
        "BOGOTA": "Bogota", "Bogota D.C.": "Bogota", "Bogotá": "Bogota",
        "MEDELLIN": "Medellin", "Medellín": "Medellin",
        "Santiago de Cali": "Cali",
        "B/quilla": "Barranquilla",
    }
    for variante, estandar in casos.items():
        assert f"WHEN ciudad = '{variante}' THEN '{estandar}'" in case_ciudad


def test_normaliza_ciudades_sin_mapeo_explicito_con_initcap():
    """
    EDA 2.1: Santa Marta y Valledupar solo tienen una forma de escritura
    en raw, por lo que caen al fallback INITCAP(TRIM(ciudad)) en vez de
    a una regla explicita del CASE.
    """
    query = generar_query_fuente(TABLA_RAW)
    assert "ELSE INITCAP(TRIM(ciudad))" in query
    assert "WHEN ciudad = 'SANTA MARTA'" not in query
    assert "WHEN ciudad = 'VALLEDUPAR'" not in query


def test_descarta_registros_con_precio_nulo():
    """
    EDA 2.5: 367 filas (~0.80%) llegan con precio_cop vacio; al ser la
    variable objetivo del modelo ML, se descartan en el SELECT fuente.
    """
    query = generar_query_fuente(TABLA_RAW)
    assert "WHERE TRIM(COALESCE(precio_cop, '')) != ''" in query


def test_deduplica_por_id():
    """
    EDA 2.6: 900 ids se repiten en raw (1.800 filas afectadas); solo debe
    conservarse una fila por id.
    """
    query = generar_query_fuente(TABLA_RAW)
    assert (
        "QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY (SELECT NULL)) = 1"
        in query
    )


def test_castea_columnas_numericas_y_fecha():
    """
    EDA 2.3/2.4: area_m2, alcobas, banos, lat, lon y fecha llegan como
    STRING en raw y se convirtieron sin fallos (0 errores de casteo).
    """
    query = generar_query_fuente(TABLA_RAW)
    assert "SAFE_CAST(TRIM(area_m2) AS FLOAT64)" in query
    assert "SAFE_CAST(TRIM(alcobas) AS INT64)" in query
    assert "SAFE_CAST(TRIM(banos)   AS INT64)" in query
    assert "SAFE_CAST(TRIM(lat) AS FLOAT64)" in query
    assert "SAFE_CAST(TRIM(lon) AS FLOAT64)" in query
    assert "SAFE_CAST(TRIM(fecha) AS DATE)" in query


def test_normaliza_texto_tipo_y_estado():
    """
    EDA 2.2: tipo y estado ya llegan con casing consistente en la fuente,
    pero se normalizan de todas formas por robustez.
    """
    query = generar_query_fuente(TABLA_RAW)
    assert "INITCAP(TRIM(tipo))" in query
    assert "LOWER(TRIM(estado))" in query
