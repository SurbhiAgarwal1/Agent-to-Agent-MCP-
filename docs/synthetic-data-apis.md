# Synthetic Blood Bank and Donor Data APIs

This repository has two separately runnable FastAPI data services. Each owns a SQLite database and uses its own SQLAlchemy models, Pydantic request schemas, and HTTP routes. `data_apis/geo.py` supplies deterministic fictional Indian metro coordinates. All generated donor and facility contact details are synthetic: phone numbers use the deliberately invalid `+91-00000-xxxxx` format and email uses `example.invalid`.

The APIs return data, not clinical decisions. Blood-group searches do not decide component-specific compatibility. Donor age, availability, history, verification, or recorded eligibility does not replace qualified medical review. A notification log does not indicate consent to donate or a commitment to respond.

## Services and ports

| Service | Local URL | OpenAPI docs | Database |
|---|---|---|---|
| Blood Bank Data API | `http://127.0.0.1:8105` | `/docs` | `data/blood_bank_data.db` |
| Individual Donor Data API | `http://127.0.0.1:8106` | `/docs` | `data/donor_data.db` |
| Official MCP SDK server | `http://127.0.0.1:8001/mcp` | Streamable HTTP | Connects to both APIs over HTTP |

The data APIs can be started without the existing coordinator backend:

```powershell
cd C:\path\to\Agent-to-Agent-MCP
.venv\Scripts\python.exe -m uvicorn blood_bank_api.main:app --host 127.0.0.1 --port 8105
.venv\Scripts\python.exe -m uvicorn donor_api.main:app --host 127.0.0.1 --port 8106
```

In separate terminals, start the MCP SDK server after both API processes are running:

```powershell
$env:BLOOD_BANK_API_URL = 'http://127.0.0.1:8105'
$env:DONOR_API_URL = 'http://127.0.0.1:8106'
$env:DATA_APIS_ENABLED = 'true'
.venv\Scripts\python.exe -m app.mcp.protocol_server
```

The MCP process registers the new tools on the repo's existing official `FastMCP` server at `/mcp`. It makes asynchronous HTTP requests to the two data APIs, with configurable timeouts and retries. A2A agents discover and invoke tools using the existing official MCP client (`app.mcp.client`). Set `DATA_APIS_ENABLED=true` for Matching and Location A2A agents to use the new data APIs; explicit in-memory inputs continue to use the existing test/domain path.

## Seed the requested datasets

Generation is explicit; API startup never generates the large datasets. From the repository root, run:

```powershell
.venv\Scripts\python.exe -m scripts.seed_blood_bank_data
.venv\Scripts\python.exe -m scripts.seed_donor_data
```

Inside the Docker Compose named volumes, generate the same datasets explicitly with:

```powershell
docker compose run --rm blood-bank-data-api python -m scripts.seed_blood_bank_data --reset
docker compose run --rm donor-data-api python -m scripts.seed_donor_data --reset
```

The default reproducible counts are:

| Dataset | Default |
|---|---:|
| Blood banks | 1,000 |
| Inventory entries | 16,000 (two components per bank and ABO/Rh group) |
| Hospitals | 500 |
| Historical blood requests | 20,000 |
| Individual donors | 100,000 |
| Donation history records | 50,000 |
| Donor notification records | 30,000 |

Blood-bank inventory supports `whole_blood` and `packed_red_blood_cells` (PRBC). Search and update endpoints accept a `component_type`; matches never mix components. Whole blood is limited to exact ABO/Rh group candidates, and PRBC uses the existing RBC compatibility matrix. All matches remain candidates for qualified clinical confirmation. Inventory quantities subtract reserved units and exclude expired stock from available searches.

The migrations are explicit and additive. Run `python -m scripts.migrate_blood_bank_inventory` to normalize legacy inventory (unsupported component quantities are zeroed, never relabeled) and `python -m scripts.migrate_donor_notifications` to add persistent delivery/response state. Neither command resets donor, bank, hospital, request, donation history, or inventory datasets.

Both generators accept `--seed` and `--as-of` (`YYYY-MM-DD`) so the same configuration recreates identical records later. Blood bank options: `--blood-banks`, `--inventory-records`, `--hospitals`, `--historical-requests`. Donor options: `--donors`, `--donation-records`, `--notification-records`, `--blood-bank-count`, `--blood-bank-offset`. Existing seeded data is preserved unless `--reset` is supplied. For example, a smaller repeatable development set is:

```powershell
.venv\Scripts\python.exe -m scripts.seed_blood_bank_data --seed 17 --blood-banks 20 --inventory-records 160 --hospitals 15 --historical-requests 20
.venv\Scripts\python.exe -m scripts.seed_donor_data --seed 17 --donors 100 --donation-records 50 --notification-records 30 --blood-bank-count 20
```

The donor generator checks donation-count/history consistency and notification consent snapshots. Blood bank generation checks all eight groups exist at every bank. Contact fields use fictional values only.

## REST API reference

All collections use `limit` and `offset`; the maximum page size is 200 for searchable data (500 for donation history). Filters are applied in SQL before pagination. Nearby queries use indexed coordinate bounds followed by exact haversine distance ordering.

### Blood Bank Data API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/blood-banks` | Paginated banks; filters: `city`, `district`, `state`, `blood_group`, `verification_status` |
| GET | `/api/v1/blood-banks/{blood_bank_id}` | Bank detail and groups with positive recorded stock |
| GET | `/api/v1/blood-banks/search` | Search by city, group, district or state |
| GET | `/api/v1/blood-banks/nearby?latitude=12.9716&longitude=77.5946&radius_km=20` | Banks in a radius, ordered by distance |
| GET | `/api/v1/blood-banks/{blood_bank_id}/inventory` | Inventory rows; optional `component_type` |
| GET | `/api/v1/blood-inventory/search` | Filter by `blood_group`, `component_type`, `city`, `minimum_available_units` |
| GET | `/api/v1/blood-inventory/available-groups` | Distinct groups with positive recorded units |
| GET | `/api/v1/blood-inventory/summary` | Stock by group/city, bank and request aggregates |
| PATCH | `/api/v1/blood-banks/{blood_bank_id}/inventory/{blood_group}` | Update available/reserved count for a component |
| GET | `/api/v1/hospitals` | Paginated hospitals; filters: `city`, `state` |
| GET | `/api/v1/hospitals/{hospital_id}` | Hospital detail |
| GET | `/api/v1/blood-requests` | Paginated requests; filters: `hospital_id`, `status`, `priority` |
| GET | `/api/v1/blood-requests/{request_id}` | Request detail |
| POST | `/api/v1/blood-requests` | Create a request for an existing hospital |
| PATCH | `/api/v1/blood-requests/{request_id}` | Update units, due time, priority, status or notes |

Example:

```bash
curl 'http://127.0.0.1:8105/api/v1/blood-inventory/search?blood_group=O%2B&city=Bengaluru&minimum_available_units=1&limit=10'
curl 'http://127.0.0.1:8105/api/v1/blood-banks/nearby?latitude=12.9716&longitude=77.5946&radius_km=20'
curl -X POST http://127.0.0.1:8105/api/v1/blood-requests -H 'Content-Type: application/json' -d '{"hospital_id":1,"required_blood_group":"O+","required_units":2,"priority":"emergency"}'
```

### Individual Donor Data API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/donors` | Use `/search` for filtered donor listing |
| GET | `/api/v1/donors/search` | Filter by group, city, district, state, availability, verification, eligibility, consent or donation count |
| GET | `/api/v1/donors/{donor_id}` | Donor detail; generated contact details are fictional |
| GET | `/api/v1/donors/nearby?latitude=12.9716&longitude=77.5946&radius_km=20` | Nearby donors, ordered by distance |
| GET | `/api/v1/donors/available` | Paginated available donors; optional location/group/consent filters |
| GET | `/api/v1/donors/statistics` | Donor and monthly donation aggregates |
| GET | `/api/v1/donors/{donor_id}/donation-history` | One donor's history |
| GET | `/api/v1/donation-history` | Paginated history; filter by donor, bank, status and dates |
| POST | `/api/v1/donors` | Register fictional contact details; starts as pending verification/eligibility |
| PATCH | `/api/v1/donors/{donor_id}` | Update availability, preferences, consent and staff-managed review fields |
| PATCH | `/api/v1/donors/{donor_id}/availability` | Update self-reported availability |
| POST | `/api/v1/donors/{donor_id}/donation-history` | Record a donation event and update the profile summary |
| POST | `/api/v1/donors/{donor_id}/notifications` | Record an attempted notification plus consent-at-attempt snapshot |
| POST | `/api/v1/donor-notifications/send` | Send or simulate an idempotent, consent-gated request with a secure donor response link |
| GET | `/api/v1/donor-notifications` | Query persisted delivery and response states |
| GET/POST | `/api/v1/donor-notifications/{notification_id}/respond` | Collect a token-protected donor response |
| POST | `/api/v1/blood-bank-notifications` | Contact a bank after checking emergency status and exact component/group inventory |
| GET | `/api/v1/blood-bank-notifications` | Query persisted bank delivery and availability responses |
| GET/POST | `/api/v1/blood-bank-notifications/{notification_id}/respond` | Collect a token-protected bank response with confirmed units |

Example:

```bash
curl 'http://127.0.0.1:8106/api/v1/donors/search?blood_group=O%2B&city=Bengaluru&available=true&limit=10'
curl 'http://127.0.0.1:8106/api/v1/donors/nearby?latitude=12.9716&longitude=77.5946&radius_km=20&limit=20'
curl 'http://127.0.0.1:8106/api/v1/donors/statistics'
```

Example collection shape:

```json
{"items":[{"id":1,"blood_group":"O+","city":"Bengaluru","available_units":12}],"total":1,"limit":10,"offset":0}
```

Individual API response fields vary by entity; each collection uses the same `items`/`total`/`limit`/`offset` envelope.

## Official MCP tool catalog

All tools are available on the existing official SDK Streamable HTTP server. Each tool has generated input schema, a purpose-specific description, FastMCP/Pydantic type validation, bounded pagination, structured JSON output, timeout handling, transient retries, and API error details.

| Tool names | Intended agent use |
|---|---|
| `list_blood_banks`, `get_blood_bank_details`, `search_blood_banks`, `find_nearby_blood_banks`, `get_blood_bank_inventory`, `search_blood_inventory`, `get_available_blood_groups`, `get_inventory_statistics` | Matching and Location agents discover bank stock and locations |
| `list_hospitals`, `get_hospital_details`, `create_blood_request`, `get_blood_request`, `update_blood_request` | Main Coordinator creates and tracks requests |
| `update_blood_inventory` | Authorized inventory workflow updates recorded stock |
| `search_donors`, `get_donor_details`, `find_nearby_donors`, `get_available_donors`, `get_donors_by_blood_group`, `get_donor_statistics`, `get_donation_history`, `register_donor`, `update_donor`, `update_donor_availability`, `record_donation`, `record_donor_notification` | Matching and Location query fictional donor data; Notification checks consent and availability, then records attempts separately from responses |

Tool schemas and detailed descriptions are served through official MCP `tools/list`; invocation uses official MCP `tools/call`. The new tools call the two APIs over HTTP and do not access their databases directly. In Docker Compose, API URLs are `http://blood-bank-data-api:8105` and `http://donor-data-api:8106`; the independent APIs have separate named data volumes and health checks. For production, set a strong `SERVICE_TO_SERVICE_TOKEN`, and protect API ingress according to the deployment boundary.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `BLOOD_BANK_DATABASE_URL` | `sqlite:///./data/blood_bank_data.db` | Blood bank API database; use PostgreSQL URL for deployment |
| `DONOR_DATABASE_URL` | `sqlite:///./data/donor_data.db` | Donor API database |
| `BLOOD_BANK_API_URL` | `http://127.0.0.1:8105` | MCP-to-bank API URL |
| `DONOR_API_URL` | `http://127.0.0.1:8106` | MCP-to-donor API URL |
| `DATA_API_TIMEOUT_SECONDS` | `8` | Per-request HTTP timeout |
| `DATA_API_MAX_RETRIES` | `2` | Retry count for timeouts, connection errors and server/temporary HTTP failures |
| `DATA_APIS_ENABLED` | `false` in local A2A agents; Compose defaults it to `true` | Routes matching/location agent data lookup through the MCP client |
| `NOTIFICATION_CHANNEL` | `console` | Default A2A notification channel (`console`, `email`, or `sms`) |
| `SMTP_HOST`, `SMTP_FROM`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | unset | Configure SMTP email delivery; without credentials or for synthetic addresses, notifications are marked simulated |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` | unset | Configure SMS delivery and verify Twilio status callbacks |
| `NOTIFICATION_PUBLIC_BASE_URL`, `NOTIFICATION_PUBLIC_DONOR_URL` | localhost URLs | Public callback/response-link origins for bank and donor APIs |
| `NOTIFICATION_WEBHOOK_TOKEN` | unset | Shared secret for authenticated non-Twilio delivery callbacks |
| `NOTIFICATION_RESPONSE_TOKEN_TTL_SECONDS` | `86400` | Lifetime of donor and blood-bank response links; successful responses consume the token |

