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


## Monitoring: Grafana, Jaeger, Prometheus and logs

The launcher records metrics, traces and logs for every service. Three things watch them:

| Tool | Address | What it shows |
| --- | --- | --- |
| Grafana | http://localhost:3001 | Dashboards: system health, coordinator workflows, A2A agent traffic, MCP tools, LLM usage, and **Logs** |
| Jaeger | http://localhost:16686 | One trace per blood request across gateway, Coordinator, agents and MCP |
| Prometheus | http://localhost:9090 | The raw numbers behind the dashboards (Status -> Targets shows what is being scraped) |

Start them **before** the launcher so traces are recorded:

```
docker compose -f docker-compose.observability.yml up -d
python -m scripts.run_distributed
```

* The launcher prints `traces going to Jaeger` when it found Jaeger. If it says `traces off`, start the monitoring containers and restart the launcher.
* Grafana opens without a login (view only). To edit dashboards sign in as `admin` / `admin` (set `GRAFANA_ADMIN_PASSWORD` to change it).
* Logs: each service's output is also written to `logs/<service>.log` (JSON lines). Promtail ships them to Loki; in Grafana open the **Logs** dashboard, or Explore -> Loki. A `trace_id` in a log line links to its Jaeger trace.
* Metrics ports (9464-9478) are fixed and not shifted by `--port-offset`.
* The launcher keeps the blood bank / donor data between restarts. Use `--reseed` to wipe and regenerate it, `--no-observability` to switch monitoring off.
* Stop the monitoring containers with `docker compose -f docker-compose.observability.yml down`.
