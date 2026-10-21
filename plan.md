# Implementation Plan: Communication Agent, Market Database, & Calling Agent

Implement advanced enterprise-grade emergency coordination capabilities in the Blood Donation Matching & Emergency Coordination System (`Agent-to-Agent-MCP-`):
1. **Communication Agent Subsystem**: Interactive bidirectional outreach with SLA deadlines and auto-escalation.
2. **Market-Grade Healthcare Database**: Realistic generation of 10 premier trauma hospitals, 8 certified blood banks, 64 component inventories, 43 GPS-tagged voluntary donors, 8 role-based user accounts, 3 realistic blood requests, and active communication sessions.
3. **Calling Agent (IVR Voice Telephony Subsystem)**: Automated outbound emergency phone dispatch, Text-to-Speech (TTS) synthesis, interactive touchtone (DTMF) keypress processing (1=Confirm, 2=Decline, 3=Delay), and bidirectional sync with communication sessions.

---

## Implementation Progress

### 1. Communication Agent Subsystem
- [x] Create SQLAlchemy models `CommunicationSession` and `CommunicationMessage` in `app/models/communication.py`
- [x] Register models in `app/models/__init__.py` and metadata
- [x] Create Pydantic schemas in `app/schemas/communication.py` and export in `app/schemas/__init__.py`
- [x] Implement business logic service `CommunicationService` in `app/services/communication_service.py`
- [x] Implement `CommunicationAgent` in `app/agents/communication_agent.py`
- [x] Register Communication A2A message types in `app/agents/a2a/message.py`
- [x] Register CommunicationAgent in `app/agents/a2a/discovery.py` and `app/agents/a2a/protocol_server.py`
- [x] Register CommunicationAgent on MessageBus in `app/agents/coordinator_agent.py`
- [x] Create MCP tools in `app/mcp/tools/communication_tool.py` and extended server in `app/mcp/server.py`
- [x] Implement FastAPI REST router in `app/api/v1/communication.py` and mount in `app/api/v1/__init__.py`
- [x] Implement unit tests in `tests/agents/test_communication_agent.py`
- [x] Implement REST API integration tests in `tests/api/test_api_communication.py`
- [x] Implement MCP tool tests in `tests/mcp/test_mcp_communication.py`

### 2. Market-Grade Database Generator
- [x] Implement realistic data generator `app/database/market_database.py`
- [x] Add CLI script `scripts/generate_market_database.py`
- [x] Populate `blood_donation.db` with 10 hospitals, 8 blood banks, 64 inventories, 43 donors, 8 pre-hashed user credentials (`Password@123`)
- [x] Implement database verification test suite `tests/db/test_market_database.py`

### 3. Calling Agent Subsystem
- [x] Create SQLAlchemy model `CallSession` in `app/models/calling.py` and export in `app/models/__init__.py`
- [x] Create Pydantic schemas `VoiceCallCreate`, `VoiceCallWebhookInput`, `CallSessionResponse`, `CallingStatsResponse` in `app/schemas/calling.py`
- [x] Create telephony provider abstraction in `app/services/voice_providers.py` (`BaseVoiceProvider`, `ConsoleVoiceProvider`, `TwilioVoiceProvider`)
- [x] Implement `CallingService` in `app/services/calling_service.py` with TTS prompt generation and DTMF response mapping
- [x] Implement `CallingAgent` in `app/agents/calling_agent.py` supporting A2A message types (`CALLING_DISPATCH_REQUEST`, `CALLING_CALLBACK_EVENT`, `CALLING_STATUS_POLL`)
- [x] Register CallingAgent on MessageBus in `app/agents/coordinator_agent.py`, `app/agents/a2a/discovery.py`, and `app/agents/a2a/protocol_server.py`
- [x] Create MCP tools in `app/mcp/tools/calling_tool.py` (`dispatch_emergency_call`, `check_call_session_status`)
- [x] Mount FastAPI REST router in `app/api/v1/calling.py` and `app/api/v1/__init__.py`
- [x] Implement unit tests in `tests/agents/test_calling_agent.py`
- [x] Implement REST API tests in `tests/api/test_api_calling.py`
- [x] Implement MCP tool tests in `tests/mcp/test_mcp_calling.py`
- [x] Verify full test suite passes with 0 failures

---

## Notes & Decisions
- Test suite expanded from 344 to 372 tests, all passing with zero regressions.
- SQLite offset-naive datetime compatibility handled via `.replace(tzinfo=timezone.utc)` where necessary.
- Telephony webhook `/api/v1/calling/webhook` is accessible without bearer auth to support carrier webhooks natively.

✅ COMPLETE
