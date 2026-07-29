from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from paso_raw import ejecutar_raw
from paso_staging import ejecutar_staging
from paso_consumption import ejecutar_consumption_paso


ARCHIVO_DEFAULT = "co_transacciones_habi.csv"

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

def tarea_staging(**context):
    nombre_archivo = obtener_archivo(**context)
    resultado = ejecutar_staging(nombre_archivo)
    if resultado != 0:
        raise RuntimeError(f"Fallo la carga a STAGING de '{nombre_archivo}'.")

def tarea_consumption(**context):
    nombre_archivo = obtener_archivo(**context)
    resultado = ejecutar_consumption_paso(nombre_archivo)
    if resultado != 0:
        raise RuntimeError(f"Fallo la carga a CONSUMPTION de '{nombre_archivo}'.")


with DAG(
    dag_id="dag_load_csv",
    description="Pipeline CSV",
    default_args=default_args,
    schedule_interval=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
) as dag:

    raw = PythonOperator(task_id="carga_raw", python_callable=tarea_raw)
    staging = PythonOperator(task_id="transformacion_staging", python_callable=tarea_staging)
    consumption = PythonOperator(task_id="carga_consumption", python_callable=tarea_consumption)
    entrenamiento = BashOperator(
        task_id="entrenamiento_modelos_ml",
        bash_command=(
            "docker exec predicasa-mlflow "
            "python /mlflow/experiments/entrenar_modelos.py"
        ),
    )

    raw >> staging >> consumption >> entrenamiento
