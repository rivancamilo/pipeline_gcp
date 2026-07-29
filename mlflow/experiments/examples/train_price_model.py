"""Experiment: Property price prediction model training."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import mlflow
import mlflow.sklearn
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler
from helpers import get_or_create_experiment, setup_mlflow


def generate_sample_data(n=1000, seed=42):
    """Generate synthetic property data for training."""
    rng = np.random.default_rng(seed)
    area = rng.uniform(30, 300, n)
    rooms = rng.integers(1, 6, n)
    bathrooms = rng.integers(1, 4, n)
    parking = rng.integers(0, 3, n)
    floor = rng.integers(1, 20, n)
    stratum = rng.integers(1, 7, n)
    age = rng.integers(0, 40, n)

    price = (
        area * 3_500_000
        + rooms * 15_000_000
        + bathrooms * 8_000_000
        + parking * 20_000_000
        + stratum * 25_000_000
        - age * 500_000
        + rng.normal(0, 10_000_000, n)
    )

    return pd.DataFrame({
        "area": area,
        "rooms": rooms,
        "bathrooms": bathrooms,
        "parking": parking,
        "floor": floor,
        "stratum": stratum,
        "age_years": age,
        "price": price.clip(50_000_000, 2_000_000_000),
    })


def evaluate(model, X_test, y_test):
    preds = model.predict(X_test)
    return {
        "mae": mean_absolute_error(y_test, preds),
        "rmse": mean_squared_error(y_test, preds, squared=False),
        "r2": r2_score(y_test, preds),
    }


def run_experiment():
    setup_mlflow()
    experiment_id = get_or_create_experiment("property-price-prediction")

    df = generate_sample_data()
    features = ["area", "rooms", "bathrooms", "parking", "floor", "stratum", "age_years"]
    X = df[features]
    y = df["price"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    models = {
        "RandomForest": RandomForestRegressor(n_estimators=100, random_state=42),
        "GradientBoosting": GradientBoostingRegressor(n_estimators=100, random_state=42),
        "Ridge": Ridge(alpha=1.0),
    }

    best_r2 = -np.inf
    best_run_id = None

    for model_name, model in models.items():
        with mlflow.start_run(experiment_id=experiment_id, run_name=model_name):
            mlflow.log_param("model_type", model_name)
            mlflow.log_param("features", features)
            mlflow.log_param("train_samples", len(X_train))
            mlflow.log_param("test_samples", len(X_test))

            model.fit(X_train, y_train)
            metrics = evaluate(model, X_test, y_test)

            mlflow.log_metrics(metrics)
            mlflow.sklearn.log_model(model, artifact_path="model")

            print(f"{model_name}: R2={metrics['r2']:.4f}, MAE={metrics['mae']:,.0f}")

            if metrics["r2"] > best_r2:
                best_r2 = metrics["r2"]
                best_run_id = mlflow.active_run().info.run_id

    print(f"\nBest model run_id: {best_run_id} (R2={best_r2:.4f})")


if __name__ == "__main__":
    run_experiment()
