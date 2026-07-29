"""Shared utilities for MLflow experiments."""
import mlflow
import os
import logging

logger = logging.getLogger(__name__)


def get_or_create_experiment(name: str) -> str:
    experiment = mlflow.get_experiment_by_name(name)
    if experiment is None:
        return mlflow.create_experiment(name)
    return experiment.experiment_id


def log_dataset_info(df, name: str = "dataset"):
    mlflow.log_param(f"{name}_rows", len(df))
    mlflow.log_param(f"{name}_cols", len(df.columns))
    mlflow.log_param(f"{name}_columns", list(df.columns))


def setup_mlflow(tracking_uri: str = None):
    uri = tracking_uri or os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    mlflow.set_tracking_uri(uri)
    logger.info(f"MLflow tracking URI set to: {uri}")
