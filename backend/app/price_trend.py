"""
TensorFlow price trend inference module.

The model is trained externally on Kaggle (see train/kaggle_train.py).
This module loads the exported SavedModel or .keras file at startup
and serves predictions at request time. No training happens here.
"""
import logging
import os
from datetime import datetime, date

import numpy as np

logger = logging.getLogger(__name__)


class PriceTrendPredictor:
    """
    Loads a trained TF model and predicts 'book_now' / 'wait' / 'neutral'
    based on current fare, days to departure, day of week, and seasonality.
    """

    def __init__(self, model_path: str):
        self.model = None
        self.model_path = model_path
        self._load_model()

    def _load_model(self):
        if not os.path.exists(self.model_path):
            logger.warning("Price trend model not found at %s. Using rule-based fallback.", self.model_path)
            return

        try:
            import tensorflow as tf  # lazy import — TF is large
            self.model = tf.saved_model.load(self.model_path)
            logger.info("Price trend model loaded from %s", self.model_path)
        except Exception as exc:
            logger.error("Failed to load price trend model: %s", exc)

    def predict(self, price: float, travel_date: str) -> dict:
        try:
            travel_dt = datetime.strptime(travel_date, "%Y-%m-%d").date()
        except ValueError:
            travel_dt = date.today()

        days_to_departure = (travel_dt - date.today()).days
        day_of_week = travel_dt.weekday()
        month = travel_dt.month

        if self.model is not None:
            return self._tf_predict(price, days_to_departure, day_of_week, month)
        else:
            return self._rule_based(price, days_to_departure, day_of_week)

    def _tf_predict(self, price: float, days_to_departure: int, day_of_week: int, month: int) -> dict:
        import tensorflow as tf

        features = np.array([[
            price,
            days_to_departure,
            day_of_week,
            month,
            1 if month in (11, 12, 1) else 0,   # peak season flag
        ]], dtype=np.float32)

        try:
            result = self.model(tf.constant(features))
            score = float(result.numpy()[0][0])
            # score > 0.6 = book now, < 0.4 = wait, else neutral
            if score > 0.6:
                signal = "book_now"
            elif score < 0.4:
                signal = "wait"
            else:
                signal = "neutral"
            return {"signal": signal, "confidence": round(score, 3), "note": f"Model score: {score:.3f}"}
        except Exception as exc:
            logger.warning("TF inference error: %s", exc)
            return self._rule_based(price, days_to_departure, day_of_week)

    def _rule_based(self, price: float, days_to_departure: int, day_of_week: int) -> dict:
        """Simple heuristic when model unavailable."""
        if days_to_departure < 7:
            signal = "book_now"
            note = "Departure within 7 days — prices typically spike near departure."
        elif days_to_departure > 45 and day_of_week in (1, 2, 3):
            signal = "wait"
            note = "More than 45 days out on a weekday — prices may dip with early sales."
        else:
            signal = "neutral"
            note = "No strong signal. Monitor prices over the next few days."

        return {"signal": signal, "confidence": 0.0, "note": note + " (Rule-based fallback — model not loaded.)"}
