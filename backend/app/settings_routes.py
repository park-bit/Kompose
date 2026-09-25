"""
Settings routes - let users save API keys locally via the UI.
Keys are stored in user_keys.json next to the backend process and loaded
into the running process environment so they take effect without restart.
"""

import json
import os
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Store beside wherever the backend is running
KEYS_FILE = Path(os.environ.get("KOMPOSE_KEYS_FILE", "user_keys.json"))

# Keys users can configure via the UI
CONFIGURABLE_KEYS = {
    "llm_api_key": "Gemini / LLM API Key",
    "google_maps_api_key": "Google Maps API Key",
    "amadeus_client_id": "Amadeus Client ID",
    "amadeus_client_secret": "Amadeus Client Secret",
    "openweather_api_key": "OpenWeatherMap API Key",
    "exchangerate_api_key": "Exchange Rate API Key",
    "apify_api_token": "Apify API Token",
}


def _load_saved_keys() -> dict:
    if KEYS_FILE.exists():
        try:
            return json.loads(KEYS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_keys(data: dict) -> None:
    KEYS_FILE.write_text(json.dumps(data, indent=2))


def _apply_to_env(data: dict) -> None:
    """Push saved keys into os.environ so config picks them up immediately."""
    for key, value in data.items():
        if value:
            os.environ[key.upper()] = value


# Apply saved keys on import (runs at startup)
_apply_to_env(_load_saved_keys())


class SettingsPayload(BaseModel):
    llm_api_key: str = ""
    google_maps_api_key: str = ""
    amadeus_client_id: str = ""
    amadeus_client_secret: str = ""
    openweather_api_key: str = ""
    exchangerate_api_key: str = ""
    apify_api_token: str = ""


@router.get("")
async def get_settings_ui():
    """Return current saved keys (values masked for security)."""
    saved = _load_saved_keys()
    result = {}
    for key in CONFIGURABLE_KEYS:
        raw = saved.get(key) or os.environ.get(key.upper(), "")
        # Mask all but last 4 chars
        result[key] = ("*" * (len(raw) - 4) + raw[-4:]) if len(raw) > 4 else ("*" * len(raw))
    return {"keys": result, "labels": CONFIGURABLE_KEYS}


@router.post("")
async def save_settings_ui(payload: SettingsPayload):
    """Save non-empty keys. Empty string = keep existing value."""
    saved = _load_saved_keys()
    updated = []

    for key in CONFIGURABLE_KEYS:
        value = getattr(payload, key, "")
        if value and not value.startswith("*"):  # ignore masked placeholders
            saved[key] = value
            os.environ[key.upper()] = value
            updated.append(key)

    _save_keys(saved)

    # Bust the settings cache so next request picks up new values
    try:
        from app.config import get_settings
        get_settings.cache_clear()
    except Exception:
        pass

    return {"saved": updated, "message": f"{len(updated)} key(s) saved."}
