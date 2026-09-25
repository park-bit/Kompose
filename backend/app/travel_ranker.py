"""
TensorFlow travel option ranker.
Scores and ranks travel options (flight, train, bus, car) using a trained neural network.
Keeps VRAM capped and operations local within workspace.
"""
import os
import logging
import numpy as np

logger = logging.getLogger(__name__)

# Mode mapping
MODE_MAP = {
    "flight": 0,
    "train": 1,
    "bus": 2,
    "car": 3,
}


class TravelRankerTF:
    """
    Ranks travel options using a trained TensorFlow Keras model.
    Evaluates mode, cost, duration, distance, passengers, and budget ratio.
    """

    def __init__(self, model_path: str | None = None):
        if not model_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            model_path = os.path.join(base_dir, "models", "travel_ranker_model.keras")

        self.model_path = model_path
        self.model = None
        self._load_model()

    def _load_model(self):
        if not os.path.exists(self.model_path):
            logger.warning("Travel ranker model not found at %s. Using heuristic fallback.", self.model_path)
            return

        try:
            import tensorflow as tf
            # Safe GPU memory growth
            gpus = tf.config.list_physical_devices("GPU")
            if gpus:
                for gpu in gpus:
                    try:
                        tf.config.experimental.set_memory_growth(gpu, True)
                    except Exception:
                        pass

            self.model = tf.keras.models.load_model(self.model_path)
            logger.info("TensorFlow travel ranker loaded from %s", self.model_path)
        except Exception as exc:
            logger.error("Failed to load travel ranker model: %s", exc)

    def score_option(
        self,
        mode: str,
        cost: float,
        duration_hrs: float,
        distance_km: float,
        passengers: int,
        budget: float | None = None,
    ) -> float:
        """Return neural suitability score between 0.0 and 100.0."""
        mode_idx = MODE_MAP.get(mode.lower(), 1)
        safe_budget = budget or (cost * 1.5)
        budget_ratio = min(cost / max(safe_budget, 1.0), 2.5)

        if self.model is not None:
            try:
                features = np.array([[
                    float(mode_idx),
                    float(cost),
                    float(duration_hrs),
                    float(distance_km),
                    float(passengers),
                    float(budget_ratio),
                ]], dtype=np.float32)

                res = self.model(features, training=False)
                raw_score = float(res[0][0]) if hasattr(res, "__getitem__") else float(res.numpy()[0][0])
                return round(np.clip(raw_score * 100.0, 5.0, 99.0), 1)
            except Exception as exc:
                logger.warning("TF ranker inference error: %s", exc)

        # Fallback heuristic
        cost_score = max(0.0, 1.0 - (budget_ratio / 1.5)) * 55.0
        speed_score = max(0.0, 1.0 - (duration_hrs / 30.0)) * 45.0
        return round(np.clip(cost_score + speed_score, 10.0, 95.0), 1)
