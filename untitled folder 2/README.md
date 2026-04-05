# Atlas Lane

Atlas Lane is now a full browser app plus Python backend for a multi-city travel planning agent. The frontend still provides the travel dashboard UI, but the backend now owns the planning APIs, persistent learning, platform trust memory, George chat, and compliance refresh logic.

## What is implemented

- separate page flow:
  - [index.html](/Users/jackgui/Desktop/untitled%20folder%202/index.html) for travel-window search
  - [trip-details.html](/Users/jackgui/Desktop/untitled%20folder%202/trip-details.html) for detailed traveler inputs
  - [results.html](/Users/jackgui/Desktop/untitled%20folder%202/results.html) for foldable search results
  - [item-detail.html](/Users/jackgui/Desktop/untitled%20folder%202/item-detail.html) for full item detail and price forecast views
- trip intake, route-aware city suggestions, and itinerary generation through backend endpoints
- baggage-aware flight ranking, ground transport options, and Monte Carlo-style price forecast payloads
- persistent per-user learning in SQLite for cities, attraction types, hotels, saved attractions, packing signals, and transport preferences
- global learning signals aggregated across sessions and used to weight future rankings
- platform trust storage with seeded blocked vendors plus user-flagged platform persistence
- George chat endpoint with OpenAI Responses API support, typo-tolerant NLP-style fallback logic, simple retrieval, and structured packing-list responses
- on-demand prohibited-items refresh endpoint with OpenAI web search support when enabled

## Run

1. Put secrets in `.env.local` or export them in your shell. `server.py` loads `.env` and `.env.local` automatically.
2. Start the backend:

```bash
python3 server.py
```

3. Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

You can also open the HTML files directly from disk now. In `file://` mode the frontend automatically targets `http://127.0.0.1:8000`, and the backend now answers CORS preflight requests so the browser does not fail with generic load errors.

## Configuration

- `OPENAI_API_KEY`: enables George and compliance refresh through the OpenAI Responses API
- `OPENAI_MODEL`: defaults to `gpt-5.4`
- `ATLAS_LANE_ENABLE_WEB_SEARCH=1`: allows George/compliance calls to use OpenAI web search when live lookup is needed
- `ATLAS_LANE_HOST` and `ATLAS_LANE_PORT`: backend bind settings
- `OPENWEATHER_API_KEY`: enables live weather summaries for cities in results and packing guidance
- `MAPBOX_TOKEN`: enables live geocoding for unknown cities and static city map previews
- `GOOGLE_PLACES_API_KEY`: used for Google Places text search, or treated as an Apify token if it starts with `apify_api_`
- `RAPID_API_KEY`: enables the RapidAPI travel-provider path for live hotel pricing and flight shopping
- `RAPID_API_HOST`: defaults to `booking-com15.p.rapidapi.com`

## Storage

- SQLite database: [data/atlas_lane.db](/Users/jackgui/Desktop/untitled%20folder%202/data/atlas_lane.db)
- Frontend session id and last synced memory remain cached in browser `localStorage`

## Notes

- Flights and ground transport are still provider-ready deterministic generators until you add a flight/rail supplier API.
- Weather and static city maps are now live when the keys are configured.
- The provided places token in this workspace is not a valid Google Places key. It identifies as an Apify token, but the referenced Google Maps scraper actor currently returns a provider-side rental error, so hotels and attractions fall back to seeded results until that provider access is fixed.
- The current RapidAPI key is wired into the app, but the tested hotel endpoint on `booking-com15` returned `403 You are not subscribed to this API`, and the tested flight search returned `429 Too many requests`, so real purchase deeplinks will only appear once the key is subscribed to the chosen travel API host and has available quota.
- Compliance refresh and George become materially better when `OPENAI_API_KEY` is set.
- Verified locally:
  - `/api/health`
  - `/api/bootstrap`
  - `/api/suggestions`
  - `/api/plan`
  - static routes for `/`, `/trip-details.html`, `/results.html`, and `/item-detail.html`
