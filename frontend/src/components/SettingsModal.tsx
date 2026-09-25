"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface KeyField {
  key: string;
  label: string;
  placeholder?: string;
}

const FIELDS: KeyField[] = [
  { key: "llm_api_key", label: "Gemini / LLM API Key", placeholder: "AIza..." },
  { key: "google_maps_api_key", label: "Google Maps API Key", placeholder: "AIza..." },
  { key: "amadeus_client_id", label: "Amadeus Client ID", placeholder: "Optional - flight data" },
  { key: "amadeus_client_secret", label: "Amadeus Client Secret", placeholder: "Optional" },
  { key: "openweather_api_key", label: "OpenWeatherMap API Key", placeholder: "Optional" },
  { key: "exchangerate_api_key", label: "Exchange Rate API Key", placeholder: "Optional" },
  { key: "apify_api_token", label: "Apify Token", placeholder: "Optional" },
];

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function SettingsModal({ open, onClose }: Props) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    fetch(`${API}/api/settings`)
      .then((r) => r.json())
      .then((data) => {
        const filled: Record<string, string> = {};
        for (const f of FIELDS) {
          filled[f.key] = data.keys?.[f.key] ?? "";
        }
        setValues(filled);
      })
      .catch(() => {});
  }, [open]);

  async function handleSave() {
    setLoading(true);
    setStatus(null);
    try {
      const res = await fetch(`${API}/api/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      const data = await res.json();
      setStatus(data.message ?? "Saved.");
    } catch {
      setStatus("Failed to save. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }

  if (!open) return null;

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="settings-header">
          <h2>API Keys</h2>
          <p>Keys are saved locally on your machine and never sent anywhere else.</p>
          <button className="settings-close" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <div className="settings-fields">
          {FIELDS.map((f) => (
            <div key={f.key} className="settings-field">
              <label htmlFor={`key-${f.key}`}>{f.label}</label>
              <input
                id={`key-${f.key}`}
                type="password"
                autoComplete="off"
                placeholder={f.placeholder ?? ""}
                value={values[f.key] ?? ""}
                onChange={(e) =>
                  setValues((v) => ({ ...v, [f.key]: e.target.value }))
                }
              />
            </div>
          ))}
        </div>

        {status && <p className="settings-status">{status}</p>}

        <div className="settings-actions">
          <button className="settings-cancel" onClick={onClose}>Cancel</button>
          <button className="settings-save" onClick={handleSave} disabled={loading}>
            {loading ? "Saving..." : "Save Keys"}
          </button>
        </div>
      </div>
    </div>
  );
}
