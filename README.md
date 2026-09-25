# Travel Planner

AI-powered travel planning agent. Chat with it, it extracts your trip details, fetches real-time flight/hotel/route data from multiple sources, and returns a structured itinerary with a price-trend advisory.

## Stack

- **Backend**: Python, FastAPI, LangGraph, Gemini (function calling)
- **Frontend**: Next.js 15, TypeScript, Tailwind CSS
- **Database**: PostgreSQL (conversation + fare history)
- **Cache**: Redis (API responses: 1hr TTL, scrape results: 30min TTL)
- **Price model**: TensorFlow dense regression, trained on Kaggle, loaded at runtime

## Features

- Conversational slot extraction: asks for missing destination/date only when needed
- Parallel tool execution: Maps, Amadeus flights/hotels/prices, Apify scrape, OpenWeatherMap, FX all called concurrently
- Budget optimizer: ranks options against budget, flags over-budget
- Price trend signal: TF model (or rule-based fallback) outputs book now / wait / neutral
- Scraped listings (MMT/OYO via Apify): display only, outbound link to source, no auto-booking
- Google Maps route visualization in the UI

## Requirements

- Python 3.11+
- Node.js 20+
- Docker + Docker Compose (for Postgres and Redis)

## Setup

### 1. Clone and configure

```bash
git clone <repo-url>
cd travel-planner
cp .env.example .env
# Fill in all keys in .env
```

### 2. Start infrastructure

```bash
docker compose up postgres redis -d
```

### 3. Backend

```bash
cd backend
pip install uv
uv pip install --system .
uvicorn app.main:app --reload
```

The backend auto-creates tables on first startup. For production migrations:

```bash
alembic upgrade head
```

### 4. Frontend

```bash
cd frontend
cp .env.local.example .env.local
# Set NEXT_PUBLIC_GOOGLE_MAPS_KEY
npm install
npm run dev
```

Open `http://localhost:3000`.

## Price Trend Model

The TF price model is trained externally on Kaggle (not in the production backend).

1. Export historical fare data from Postgres:
   ```sql
   COPY fare_records TO '/tmp/fare_records.csv' CSV HEADER;
   ```
2. Upload `fare_records.csv` to a Kaggle dataset.
3. Run `train/kaggle_train.py` on Kaggle (free GPU).
4. Download the output `price_trend_model/` directory.
5. Place it at `backend/models/price_trend_model/`.
6. Restart the backend — it loads the model at startup.

See `train/kaggle_train.py` for full instructions.

## API Keys Required

| Key | Source |
|-----|--------|
| `LLM_API_KEY` | [Google AI Studio](https://aistudio.google.com) |
| `GOOGLE_MAPS_API_KEY` | [Google Cloud Console](https://console.cloud.google.com) |
| `AMADEUS_CLIENT_ID` / `AMADEUS_CLIENT_SECRET` | [Amadeus for Developers](https://developers.amadeus.com) — use test environment first |
| `APIFY_API_TOKEN` | [Apify](https://apify.com) |
| `OPENWEATHER_API_KEY` | [OpenWeatherMap](https://openweathermap.org/api) |
| `EXCHANGERATE_API_KEY` | [exchangerate-api.com](https://www.exchangerate-api.com) |

## Legal Notes

- Scraped data from MakeMyTrip/OYO via Apify is for display only. No booking is performed on their behalf. Users are directed to the source site for booking.
- Amadeus data is real bookable data via their official API.

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app
│   │   ├── agent.py         # LangGraph graph
│   │   ├── tools.py         # All external API tools
│   │   ├── price_trend.py   # TF model inference
│   │   ├── routes.py        # HTTP endpoints
│   │   ├── models.py        # SQLAlchemy ORM
│   │   ├── database.py      # DB engine/session
│   │   ├── cache.py         # Redis helpers
│   │   └── config.py        # Settings from env
│   ├── alembic/             # DB migrations
│   └── models/              # TF model artifacts (gitignored)
├── frontend/
│   └── src/
│       ├── app/             # Next.js App Router
│       ├── components/      # UI components
│       ├── lib/             # API client
│       └── types/           # TypeScript types
└── train/
    └── kaggle_train.py      # Kaggle training script
```
