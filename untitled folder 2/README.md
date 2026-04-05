# Atlas Lane

Atlas Lane is now a full browser app plus Python backend for a multi-city travel planning agent. The frontend still provides the travel dashboard UI, but the backend now owns the planning APIs, persistent learning, platform trust memory, George chat, and compliance refresh logic.

## What is implemented

- trip intake, route-aware city suggestions, and itinerary generation through backend endpoints
- baggage-aware flight ranking, ground transport options, and Monte Carlo-style price forecast payloads
- persistent per-user learning in SQLite for cities, attraction types, hotels, saved attractions, packing signals, and transport preferences
- global learning signals aggregated across sessions and used to weight future rankings
- platform trust storage with seeded blocked vendors plus user-flagged platform persistence
- George chat endpoint with OpenAI Responses API support and a structured fallback mode when no API key is configured
- on-demand prohibited-items refresh endpoint with OpenAI web search support when enabled

## Run

1. Copy [.env.example](/Users/jackgui/Desktop/untitled%20folder%202/.env.example) values into your shell or environment.
2. Start the backend:

```bash
python3 server.py
```

3. Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Configuration

- `OPENAI_API_KEY`: enables George and compliance refresh through the OpenAI Responses API
- `OPENAI_MODEL`: defaults to `gpt-5.4`
- `ATLAS_LANE_ENABLE_WEB_SEARCH=1`: allows George/compliance calls to use OpenAI web search when live lookup is needed
- `ATLAS_LANE_HOST` and `ATLAS_LANE_PORT`: backend bind settings

## Storage

- SQLite database: [data/atlas_lane.db](/Users/jackgui/Desktop/untitled%20folder%202/data/atlas_lane.db)
- Frontend session id and last synced memory remain cached in browser `localStorage`

## Notes

- Flights, hotels, attractions, and safety layers are still provider-ready deterministic generators until you add live supplier integrations.
- Compliance refresh and George become materially better when `OPENAI_API_KEY` is set.
- The backend was verified locally for `/api/health`, `/api/bootstrap`, `/api/suggestions`, and `/api/plan`.
