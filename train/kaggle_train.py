"""
Kaggle training script for price trend LSTM model.

Run this notebook on Kaggle (free GPU/TPU):
1. Upload your Postgres export CSV (fare_records.csv) to Kaggle as a dataset.
2. Set the DATA_PATH constant below to the Kaggle dataset path.
3. Run all cells.
4. Download the exported model artifact (price_trend_model.zip or SavedModel directory).
5. Place it in backend/models/price_trend_model in your repo.
6. The backend will auto-load it at startup.

Exported CSV schema: route_key, mode, price, currency, travel_date, query_date,
                     days_to_departure, day_of_week, source
"""

import os
import pandas as pd
import numpy as np
import tensorflow as tf
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import joblib

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATA_PATH = "/kaggle/input/travel-fare-records/fare_records.csv"  # adjust to your Kaggle dataset path
MODEL_OUTPUT_DIR = "/kaggle/working/price_trend_model"
SCALER_OUTPUT = "/kaggle/working/scaler.pkl"

EPOCHS = 30
BATCH_SIZE = 64
SEQUENCE_LEN = 10  # for LSTM variant; ignored for dense model


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.dropna(subset=["price", "days_to_departure", "day_of_week"])
    df["travel_date"] = pd.to_datetime(df["travel_date"], errors="coerce")
    df["month"] = df["travel_date"].dt.month.fillna(6).astype(int)
    df["is_peak_season"] = df["month"].isin([11, 12, 1]).astype(int)

    # Label: if price is in the bottom 33rd percentile for that route, label = "wait" (0),
    # if in top 33rd, label = "book_now" (1), else "neutral" (0.5 -> rounded)
    df["price_rank"] = df.groupby("route_key")["price"].rank(pct=True)
    df["label"] = np.where(df["price_rank"] >= 0.67, 1.0, np.where(df["price_rank"] <= 0.33, 0.0, 0.5))

    return df


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

FEATURES = ["price", "days_to_departure", "day_of_week", "month", "is_peak_season"]


def build_features(df: pd.DataFrame):
    X = df[FEATURES].values.astype(np.float32)
    y = df["label"].values.astype(np.float32)
    return X, y


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def build_model(input_dim: int) -> tf.keras.Model:
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(input_dim,)),
        tf.keras.layers.Dense(64, activation="relu"),
        tf.keras.layers.BatchNormalization(),
        tf.keras.layers.Dropout(0.2),
        tf.keras.layers.Dense(32, activation="relu"),
        tf.keras.layers.Dropout(0.1),
        tf.keras.layers.Dense(1, activation="sigmoid"),
    ])
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
        loss="binary_crossentropy",
        metrics=["accuracy", tf.keras.metrics.AUC(name="auc")],
    )
    return model


# ---------------------------------------------------------------------------
# Train
# ---------------------------------------------------------------------------

def train():
    print("Loading data...")
    df = load_data(DATA_PATH)
    print(f"Loaded {len(df)} records.")

    X, y = build_features(df)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    X_train, X_val, y_train, y_val = train_test_split(X_scaled, y, test_size=0.2, random_state=42)

    model = build_model(X_train.shape[1])
    model.summary()

    callbacks = [
        tf.keras.callbacks.EarlyStopping(patience=5, restore_best_weights=True),
        tf.keras.callbacks.ReduceLROnPlateau(patience=3, factor=0.5),
    ]

    history = model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        callbacks=callbacks,
        verbose=1,
    )

    val_auc = max(history.history.get("val_auc", [0]))
    print(f"Best validation AUC: {val_auc:.4f}")

    # Save model as SavedModel (TF serving compatible)
    os.makedirs(MODEL_OUTPUT_DIR, exist_ok=True)
    model.export(MODEL_OUTPUT_DIR)
    print(f"Model saved to {MODEL_OUTPUT_DIR}")

    # Save scaler for inference normalization
    joblib.dump(scaler, SCALER_OUTPUT)
    print(f"Scaler saved to {SCALER_OUTPUT}")

    print("\nDownload these files from Kaggle output:")
    print(f"  {MODEL_OUTPUT_DIR}/  -> place in backend/models/price_trend_model/")
    print(f"  {SCALER_OUTPUT}      -> place in backend/models/scaler.pkl")
    print("\nThe backend PriceTrendPredictor will auto-load them at startup.")


if __name__ == "__main__":
    train()
