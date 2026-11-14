# Running the full distributed stack without Docker

```bash
python -m scripts.run_distributed             # first run seeds 100 blood banks / 2000 donors
python -m scripts.run_distributed --no-seed   # reuse the data
python -m scripts.run_distributed --banks 1000 --donors 100000   # full-size dataset
```

Starts the blood bank and donor data APIs (8205, 8206), the MCP server (8001), nine A2A agents (8100-8108)
and the backend (8000, `A2A_EXECUTION_MODE=distributed`, `DATA_APIS_ENABLED=true`). Ctrl+C stops everything.

Request flow: `POST /api/v1/nl-request` -> Coordinator discovers agents from their Agent Cards -> Requirement ->
Emergency priority -> Matching (MCP tools over the synthetic data) -> Location -> Notification
(blood banks and donors, response `pending`).

Hospital staff need a hospital membership before using `/nl-request` (see `/api/v1/auth/users/{id}/hospital-memberships`).

## OpenStreetMap discovery and responses

* `OSM_DISCOVERY_ENABLED=true` (the launcher default) makes the Location agent ask the MCP tool
  `discover_osm_blood_banks` (Overpass API, `OVERPASS_URL` to override) for facilities near the hospital.
  They appear as `osm_nearby_blood_banks` in the request result. OSM has no stock data: phone them to confirm.
* In development the notification links are printed in the launcher output as `DEV response link ...`.
  Open one (or POST `{"response_status":"accepted","confirmed_available_units":2}` to it) to answer as that blood bank / donor.
* Staff see the answer at `GET /api/v1/hospital-alerts` and `GET /api/v1/blood-requests/{id}/responses`.

## Geoapify (places) and OpenRouteService (road distance / ETA)

Create a `.env` file in the project root (it is git-ignored; never commit keys):

```
GEOAPIFY_API_KEY=your_geoapify_key
ORS_API_KEY=your_openrouteservice_token
```

The launcher loads it automatically.

* `GEOAPIFY_API_KEY` -> nearby facilities come from Geoapify (`PLACES_PROVIDER=auto|geoapify|overpass`). Geoapify has no
  blood-bank category, so places named like a blood bank are listed first and hospitals (which often run a blood bank) after them.
* `ORS_API_KEY` -> `ROUTING_PROVIDER=ors`: one OpenRouteService Matrix request returns road distance and travel time for all
  candidates. If ORS fails (quota, key, network) the response falls back to straight-line estimates and says so.
