#!/bin/bash
set -e

echo "================================================"
echo "  AIRFLOW STARTUP SCRIPT"
echo "================================================"

# Esperar a que MySQL esté disponible
echo ""
echo "Esperando a que MySQL esté disponible..."
max_retries=30
counter=0

while ! nc -z mysql 3306; do
    counter=$((counter+1))
    if [ $counter -gt $max_retries ]; then
        echo "ERROR: No se pudo conectar a MySQL después de $max_retries intentos"
        exit 1
    fi
    echo "Intento $counter/$max_retries: MySQL no está listo aún, esperando..."
    sleep 2
done

echo "MySQL está disponible!"

# Espera adicional para asegurar que MySQL está completamente listo
sleep 5

# Inicializar base de datos de Airflow
echo ""
echo "Inicializando base de datos de Airflow..."
airflow db init

# Crear usuario admin (ignorar si ya existe)
echo ""
echo "Creando usuario admin..."
airflow users create \
    --username admin \
    --password admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com 2>/dev/null || echo "Usuario admin ya existe, continuando..."

echo "✓ Usuario admin listo"

# Iniciar Airflow Webserver en background
echo ""
echo "Iniciando Airflow Webserver..."
airflow webserver --port 8080 &

# Esperar un poco para que el webserver inicie
sleep 5

# Iniciar Airflow Scheduler (en foreground para mantener el contenedor corriendo)
echo ""
echo "Iniciando Airflow Scheduler..."
echo "================================================"
echo "  Airflow está listo!"
echo "  Accede en: http://localhost:8081"
echo "  Usuario: admin | Password: admin"
echo "================================================"
echo ""

exec airflow scheduler