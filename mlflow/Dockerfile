FROM python:3.11-slim

WORKDIR /mlflow

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    mlflow==2.10.0 \
    scikit-learn==1.4.0 \
    xgboost==2.0.3 \
    pandas==2.1.4 \
    numpy==1.26.3 \
    joblib==1.3.2 \
    pyyaml==6.0.1 \
    google-cloud-bigquery==3.17.2 \
    google-cloud-storage==2.14.0 \
    db-dtypes==1.2.0 \
    boto3==1.34.0 \
    psycopg2-binary==2.9.9

EXPOSE 5000

RUN mkdir -p /mlflow/mlruns

CMD ["mlflow", "server", \
     "--host", "0.0.0.0", \
     "--port", "5000", \
     "--backend-store-uri", "sqlite:////mlflow/mlruns/mlflow.db", \
     "--default-artifact-root", "/mlflow/mlruns"]
