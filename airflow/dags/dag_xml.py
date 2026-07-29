from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from paso_raw import ejecutar_raw


ARCHIVO_DEFAULT = "macro_housing_index.xml"

default_args = {
    "owner": "Ivan Camilo Rosales",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


def obtener_archivo(**context) -> str:
    return context["dag_run"].conf.get("nombre_archivo", ARCHIVO_DEFAULT)


def tarea_raw(**context):
    nombre_archivo = obtener_archivo(**context)
    resultado = ejecutar_raw(nombre_archivo)
    if resultado != 0:
        raise RuntimeError(f"Fallo la carga a RAW de '{nombre_archivo}'.")


with DAG(
    dag_id="dag_xml_raw",
    description="Pipeline XML",
    default_args=default_args,
    schedule_interval=None,
    start_date=datetime(2024, 1, 1),
    catchup=False
) as dag:

    raw = PythonOperator(task_id="carga_raw", python_callable=tarea_raw)
