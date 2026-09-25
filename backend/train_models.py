"""
Local TensorFlow training script.
Trains lightweight neural models for:
1. Flight/fare price trend prediction (book_now vs wait vs neutral)
2. Multimodal route score ranker (evaluating cost, duration, and convenience)

All models and cache are kept strictly inside D:/Contributions/Kompose/backend.
VRAM allocation is limited to 1.5GB for 6GB GPUs.
"""
import os
import sys

# Keep all cache and temporary data strictly in current directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)
os.environ["KERAS_HOME"] = os.path.join(CACHE_DIR, "keras")
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import numpy as np
import tensorflow as tf

# VRAM memory limit configuration for 6GB GPU
gpus = tf.config.list_physical_devices("GPU")
if gpus:
    for gpu in gpus:
        try:
            tf.config.experimental.set_memory_growth(gpu, True)
            tf.config.set_logical_device_configuration(
                gpu,
                [tf.config.LogicalDeviceConfiguration(memory_limit=1536)]
            )
            print(f"Configured GPU {gpu.name} with 1536MB memory limit.")
        except Exception as e:
            print(f"GPU config notice: {e}")

MODELS_DIR = os.path.join(BASE_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)


def train_price_trend_model():
    """Train price trend prediction model."""
    print("Training TensorFlow Price Trend model...")
    np.random.seed(42)
    tf.random.set_seed(42)

    n_samples = 4000
    # Features: [price, days_to_departure, day_of_week, month, is_peak_season]
    price = np.random.uniform(2500, 25000, n_samples)
    days_to_departure = np.random.randint(1, 90, n_samples)
    day_of_week = np.random.randint(0, 7, n_samples)
    month = np.random.randint(1, 13, n_samples)
    is_peak = np.isin(month, [11, 12, 1, 5]).astype(float)

    # Heuristic target: probability price will rise (1.0 = book now, 0.0 = wait)
    # Price rises close to departure (< 14 days) and in peak seasons
    urgency = np.clip(1.0 - (days_to_departure / 30.0), 0.0, 1.0)
    peak_factor = is_peak * 0.35
    weekend_factor = np.isin(day_of_week, [4, 5, 6]).astype(float) * 0.15
    y = np.clip(urgency * 0.6 + peak_factor + weekend_factor + np.random.normal(0, 0.08, n_samples), 0.0, 1.0)

    X = np.stack([price, days_to_departure, day_of_week, month, is_peak], axis=1).astype(np.float32)

    # Normalization layer
    norm_layer = tf.keras.layers.Normalization(axis=-1)
    norm_layer.adapt(X)

    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(5,)),
        norm_layer,
        tf.keras.layers.Dense(32, activation="relu"),
        tf.keras.layers.Dropout(0.1),
        tf.keras.layers.Dense(16, activation="relu"),
        tf.keras.layers.Dense(1, activation="sigmoid"),
    ])

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.005),
        loss="mse",
        metrics=["mae"],
    )

    model.fit(X, y, epochs=15, batch_size=64, verbose=0, validation_split=0.15)

    model_path = os.path.join(MODELS_DIR, "price_trend_model.keras")
    model.save(model_path)
    print(f"Price Trend model saved to {model_path}")
    return model_path


def train_travel_ranker_model():
    """Train multi-modal travel option ranker."""
    print("Training TensorFlow Travel Option Ranker...")
    np.random.seed(123)
    tf.random.set_seed(123)

    n_samples = 5000
    # Features: [mode_idx, cost_per_person, duration_hrs, distance_km, passengers, budget_ratio]
    # mode_idx: 0=flight, 1=train, 2=bus, 3=car
    mode_idx = np.random.randint(0, 4, n_samples)
    distance_km = np.random.uniform(100, 2500, n_samples)
    passengers = np.random.randint(1, 6, n_samples)
    cost = np.random.uniform(500, 15000, n_samples)
    duration_hrs = np.random.uniform(1.5, 36.0, n_samples)
    budget = np.random.uniform(2000, 30000, n_samples)
    budget_ratio = np.clip(cost / (budget + 1e-5), 0.1, 2.0)

    # Rank target: higher is better (value score between 0 and 1)
    cost_score = np.clip(1.0 - (budget_ratio / 1.5), 0.0, 1.0)
    speed_score = np.clip(1.0 - (duration_hrs / 30.0), 0.0, 1.0)
    target = np.clip(cost_score * 0.55 + speed_score * 0.45 + np.random.normal(0, 0.05, n_samples), 0.0, 1.0)

    X = np.stack([mode_idx, cost, duration_hrs, distance_km, passengers, budget_ratio], axis=1).astype(np.float32)

    norm_layer = tf.keras.layers.Normalization(axis=-1)
    norm_layer.adapt(X)

    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(6,)),
        norm_layer,
        tf.keras.layers.Dense(32, activation="relu"),
        tf.keras.layers.Dense(16, activation="relu"),
        tf.keras.layers.Dense(1, activation="sigmoid"),
    ])

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.005),
        loss="mse",
        metrics=["mae"],
    )

    model.fit(X, target, epochs=15, batch_size=64, verbose=0, validation_split=0.15)

    model_path = os.path.join(MODELS_DIR, "travel_ranker_model.keras")
    model.save(model_path)
    print(f"Travel Ranker model saved to {model_path}")
    return model_path


if __name__ == "__main__":
    train_price_trend_model()
    train_travel_ranker_model()
    print("All TensorFlow models successfully created and saved in backend/models.")
