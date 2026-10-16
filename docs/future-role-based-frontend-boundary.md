# Future role-based frontend boundary

This is a planning boundary for a later frontend phase. It does not add frontend screens, routes, roles, or API permissions.

| Role | Future application access | Must not access |
|---|---|---|
| **USER** | Submit a blood requirement; view their own request status and appropriate availability/match information; receive status notifications; manage their own profile and requests. | Internal agent topology, A2A/MCP details, prompts/responses, token usage, raw metrics, Grafana, Prometheus, Jaeger, or internal traces. |
| **HOSPITAL STAFF** | Manage hospital-side blood requirements and operational requests; review relevant availability/matches; coordinate fulfillment and view operational status. | Grafana, Prometheus, Jaeger, raw metrics, internal traces, LLM/token data, or A2A/MCP debugging information. |
| **ADMIN** | Administrative management plus system/agent health, A2A and MCP operations, LLM provider/model usage, metrics, dashboards, traces, and operational monitoring. | Access remains subject to explicit admin authentication and audit policy. |

The future frontend must rely on server-side authorization for every protected operation; hiding navigation items is not an authorization boundary. Observability access should remain on its separate operations surface and must not be proxied through ordinary user or hospital-staff application routes.

