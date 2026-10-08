# Blood Donation Matching & Emergency Coordination System

An autonomous, multi-agent emergency coordination system connecting hospitals, blood banks, and voluntary donors during critical blood shortages.

---

## 1. Project Overview & System Phases (Parts 1–16)

The system is organized into a modular 16-part architecture:

* **Part 1: Project Scaffolding & FastAPI Foundation** — Core application structure and environment configuration.
* **Part 2: Relational Models & Synthetic Data** — SQLAlchemy ORM schema (`hospitals`, `blood_banks`, `blood_inventories`, `donors`, `blood_requests`, `matches`) and automated synthetic seeding.
* **Part 3: Blood Request Lifecycle APIs** — CRUD endpoints for emergency requests with validation and status state transitions.
* **Part 4: Requirement Agent** — Medical domain validation, input normalization, and hospital verification.
* **Part 5: Matching Agent & RBC Engine** — Red blood cell ABO/Rh compatibility matrix with institutional stock prioritization.
* **Part 6: Location Agent** — Spherical Haversine distance engine and urban emergency transit estimation.
* **Part 7: Agent-to-Agent (A2A) Protocol** — Structured message envelope and in-process message bus (`app/agents/a2a/`) replacing direct function coupling.
* **Part 8: Model Context Protocol (MCP) Server** — Exposes core agents as standardized MCP tools (`app/mcp/`) for external agentic and LLM tool calling.
* **Part 9: Coordinator Agent** — Full coordination lifecycle owning the formal request state machine (`RECEIVED -> VALIDATED -> MATCHED -> LOCATED -> COMPLETED / FAILED`) and persistence.
* **Part 10: Multi-Source Optimization Engine** — Combines multiple blood banks and voluntary donors to meet large unit quotas (`app/services/optimization_service.py`), respecting the 1-unit donor medical limit.
* **Part 11: Real Routing & Road Network ETA** — Swappable `RoutingProvider` (`app/services/routing_provider.py`) supporting real road-network distance/ETA via OSRM with automatic Haversine fallback.
* **Part 12: Notification Agent & Dispatch Alerting** — Multi-channel alerting (`app/agents/notification_agent.py`) notifying hospitals and dispatching pickup orders to blood banks/donors (Console, Email, SMS).
* **Part 13: Emergency Command Center UI** — Real-time Single Page Application dashboard (`frontend/` and `/dashboard`) with live 5s polling, interactive dispatch, and coordination visualizer.
* **Part 14: LLM Natural Language Interface** — Natural language interface (`app/llm/`) parsing free-form clinical dispatch text into validated actions via `POST /api/v1/nl-request`.
* **Part 15: Authentication & Audit Logging** — JWT bearer token authentication, role-based access control (`HOSPITAL_STAFF`, `BLOOD_BANK_STAFF`, `ADMIN`), and immutable `AuditLog` records for sensitive actions.
* **Part 16: Docker, CI/CD & Observability** — Multi-stage `Dockerfile`, `docker-compose.yml`, GitHub Actions workflow (`.github/workflows/ci.yml`), and real-time operational `/metrics`.

---

## 2. Multi-Agent & Service Architecture

```
               [ Emergency Free-Text / REST API / UI ]
                                  │
                                  ▼
                     ┌──────────────────────────┐
                     │   Authentication & RBAC  │ (Part 15)
                     └────────────┬─────────────┘
                                  │
                                  ▼
                     ┌──────────────────────────┐
                     │  NL / LLM Parser (NLP)   │ (Part 14)
                     └────────────┬─────────────┘
                                  │
                                  ▼
                     ┌──────────────────────────┐
                     │    Coordinator Agent     │ (Part 9)
                     │ (Full Lifecycle / State) │
                     └────────────┬─────────────┘
                                  │
            ┌─────────────────────┼─────────────────────┐
            ▼                     ▼                     ▼
     ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
     │ Requirement  │      │   Matching   │      │   Location   │
     │    Agent     │      │    Agent     │      │    Agent     │
     │  (Validation)│      │(Compatibility)      │  (OSRM/ETA)  │
     └──────────────┘      └──────────────┘      └──────────────┘
            │                     │                     │
            └─────────────────────┼─────────────────────┘
                                  │
                                  ▼
                     ┌──────────────────────────┐
                     │   Optimization Engine    │ (Part 10)
                     │ (Multi-Source Allocation)│
                     └────────────┬─────────────┘
                                  │
                                  ▼
                     ┌──────────────────────────┐
                     │    Notification Agent    │ (Part 12)
                     │ (Hospital/Bank/Donor)    │
                     └────────────┬─────────────┘
                                  │
                                  ▼
                     ┌──────────────────────────┐
                     │    Audit Log & Metrics   │ (Part 15 & 16)
                     └──────────────────────────┘
```

---

## 3. Running with Docker Compose

To spin up the entire system (FastAPI backend + Command Center frontend) in a single command:

```bash
docker-compose up --build
```

- **Backend API**: `http://localhost:8000`
- **Swagger Documentation**: `http://localhost:8000/docs`
- **Operational Metrics**: `http://localhost:8000/metrics`
- **Command Center Dashboard**: `http://localhost:8000/dashboard` or `http://localhost:3000`

---

## 4. Local Development & Testing

### Setup Environment
```bash
python -m venv venv
venv\Scripts\activate   # Windows
# or source venv/bin/activate  # Linux/macOS

pip install -r requirements.txt
```

### Run All Tests (120 Tests across Parts 1–16)
```bash
pytest -v
```

### Run Tests with Coverage
```bash
pytest -v --cov=app --cov-report=term-missing
```

### Run Local Backend Server
```bash
uvicorn app.main:app --reload --port 8000
```

---

## 5. API Reference Summary

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Service health status. |
| `GET` | `/metrics` | Real-time operational request counts, latencies, and agent statistics. |
| `GET` | `/dashboard` | Interactive Emergency Command Center web UI. |
| `POST` | `/api/v1/auth/register` | Register new staff user with role. |
| `POST` | `/api/v1/auth/login` | Authenticate and obtain JWT access token. |
| `GET` | `/api/v1/auth/me` | Fetch currently authenticated user profile. |
| `GET` | `/api/v1/auth/audit-logs` | Retrieve security and operational audit logs. |
| `POST` | `/api/v1/blood-requests` | Submit an emergency blood request. |
| `GET` | `/api/v1/blood-requests` | List all active blood requests. |
| `POST` | `/api/v1/blood-requests/{id}/coordinate` | Trigger Coordinator Agent lifecycle & multi-source optimization. |
| `POST` | `/api/v1/nl-request` | Free-form natural language blood request parser & dispatcher. |
| `GET` | `/api/v1/mcp/tools` | List registered Model Context Protocol (MCP) tools. |
| `POST` | `/api/v1/mcp/invoke` | Invoke MCP tools externally. |

---

## 6. Continuous Integration (CI/CD)

The GitHub Actions workflow (`.github/workflows/ci.yml`) executes automatically on every `push` and `pull_request` to:
1. Run syntax and lint checks across Python 3.11 and 3.12.
2. Execute the entire 120-test test suite with code coverage assertions.
3. Validate clean Docker image container builds for both backend and frontend.
