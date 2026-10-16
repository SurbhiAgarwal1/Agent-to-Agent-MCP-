"""Network-boundary tests for the independently hosted official A2A services."""

import json
import asyncio
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models import BloodBank, BloodInventory, BloodRequest, Hospital


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_card(url, process):
    deadline = time.monotonic() + 25
    last_error = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"A2A service exited during startup with code {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                card = json.loads(response.read())
            assert card["name"]
            assert card["supportedInterfaces"]
            return card
        except Exception as exc:  # service may need several seconds to import
            last_error = exc
            time.sleep(0.2)
    raise AssertionError(f"Agent Card was not available at {url}: {last_error}")


async def _exercise_mcp_boundary(monkeypatch, mcp_url):
    """Run discovery and domain tool cases through an independent MCP socket."""
    monkeypatch.setenv("MCP_URL", mcp_url)
    from app.mcp.client import MCPClientError, call_remote_tool, discover_remote_tools

    discovered = await discover_remote_tools()
    schemas = {tool["name"]: tool["inputSchema"] for tool in discovered}
    assert set(schemas) == {
        "validate_blood_request", "find_blood_sources", "calculate_distance", "dispatch_notifications"
    }
    assert {"hospital_id", "blood_group", "units_required", "urgency"} <= set(schemas["validate_blood_request"]["properties"])
    assert {"origin_latitude", "destination_latitude"} <= set(schemas["calculate_distance"]["properties"])

    valid = await call_remote_tool("validate_blood_request", {
        "hospital_id": 1, "blood_group": "o+", "units_required": 1, "urgency": "HIGH"
    })
    assert valid["valid"] is True and valid["blood_group"] == "O+"
    invalid = await call_remote_tool("validate_blood_request", {
        "hospital_id": 1, "blood_group": "not-a-group", "units_required": 1, "urgency": "HIGH"
    })
    assert invalid["valid"] is False

    matched = await call_remote_tool("find_blood_sources", {"blood_group": "O+", "request_id": 1})
    assert len(matched["matches"]) >= 1
    no_match = await call_remote_tool("find_blood_sources", {"blood_group": "AB-", "request_id": 1})
    assert no_match["matches"] == []

    distance = await call_remote_tool("calculate_distance", {
        "origin_latitude": 12, "origin_longitude": 77,
        "destination_latitude": 12.1, "destination_longitude": 77.1,
    })
    assert distance["distance_km"] > 0
    with pytest.raises(MCPClientError) as bad_coordinates:
        await call_remote_tool("calculate_distance", {
            "origin_latitude": 91, "origin_longitude": 77,
            "destination_latitude": 12, "destination_longitude": 77,
        })
    assert bad_coordinates.value.code == "tool_execution_failed", repr(bad_coordinates.value.__cause__)

    notification = await call_remote_tool("dispatch_notifications", {
        "hospital_id": 1, "request_id": 1,
        "fulfillment_plan": {"status": "UNFULFILLED", "total_units": 0, "details": {"units_required": 0}, "plan": []},
    })
    assert notification["success"] is True and notification["dispatched_count"] == 1
    with pytest.raises(MCPClientError) as missing_args:
        await call_remote_tool("calculate_distance", {})
    assert missing_args.value.code == "invalid_arguments"
    with pytest.raises(MCPClientError) as unknown_tool:
        await call_remote_tool("not_a_tool", {})
    assert unknown_tool.value.code == "tool_not_found"

    # Exercise the official SDK's own unknown-tool protocol error as well as the
    # client-side discovery guard above.
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    async with streamable_http_client(mcp_url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            protocol_error = await session.call_tool("not_a_tool", arguments={})
            assert protocol_error.isError

    monkeypatch.setenv("MCP_URL", "http://127.0.0.1:1/mcp")
    monkeypatch.setenv("MCP_TIMEOUT_SECONDS", "0.2")
    monkeypatch.setenv("MCP_MAX_RETRIES", "0")
    with pytest.raises(MCPClientError) as unavailable:
        await call_remote_tool("calculate_distance", {})
    assert unavailable.value.code in {"connection_failed", "timeout"}, repr(unavailable.value.__cause__)

    # Tiny timeout forces a real Streamable HTTP request timeout at initialization
    # or tool discovery; retries are disabled to keep this failure bounded.
    monkeypatch.setenv("MCP_URL", mcp_url)
    monkeypatch.setenv("MCP_TIMEOUT_SECONDS", "0.000001")
    with pytest.raises(MCPClientError) as timed_out:
        await call_remote_tool("calculate_distance", {
            "origin_latitude": 12, "origin_longitude": 77,
            "destination_latitude": 12.1, "destination_longitude": 77.1,
        })
    assert timed_out.value.code == "timeout"


def test_independent_services_discover_cards_and_coordinate_over_a2a_http(tmp_path, monkeypatch):
    """Coordinator reaches all four specialized services over real local sockets."""
    db_path = (tmp_path / "a2a-integration.sqlite").as_posix()
    database_url = f"sqlite:///{db_path}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        hospital = Hospital(name="A2A Test Hospital", latitude=12.0, longitude=77.0, address="Test Road")
        bank = BloodBank(name="A2A Test Bank", latitude=12.1, longitude=77.1, address="Bank Road")
        db.add_all([hospital, bank])
        db.flush()
        db.add(BloodRequest(hospital_id=hospital.hospital_id, blood_group="O+", units_required=1, urgency="HIGH"))
        db.add(BloodInventory(bank_id=bank.bank_id, blood_group="O+", units_available=3,
                              expiry_date=date.today() + timedelta(days=30)))
        db.commit()

    ports = {name: _free_port() for name in ("coordinator", "requirement", "matching", "location", "notification", "mcp")}
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    base_env = os.environ.copy()
    base_env.update({
        "JWT_SECRET_KEY": "integration-test-secret-key-long-enough",
        "DATABASE_URL": database_url,
        "MCP_URL": f"http://127.0.0.1:{ports['mcp']}/mcp",
        "A2A_TIMEOUT_SECONDS": "10",
        "A2A_MAX_RETRIES": "1",
        "MCP_TIMEOUT_SECONDS": "6",
        "MCP_MAX_RETRIES": "1",
        "LLM_PROVIDER": "mock",
    })
    python = sys.executable or shutil.which("py")
    assert python, "Python launcher required to start isolated A2A services"
    launch_prefix = [python]
    processes = []
    urls = {}
    cards = {}
    try:
        mcp_env = {**base_env, "MCP_PORT": str(ports["mcp"])}
        processes.append(subprocess.Popen(
            [*launch_prefix, "-m", "app.mcp.protocol_server"], cwd=root, env=mcp_env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ))
        mcp_ready = time.monotonic() + 25
        while time.monotonic() < mcp_ready:
            if processes[0].poll() is not None:
                raise AssertionError("MCP service exited during startup")
            try:
                with socket.create_connection(("127.0.0.1", ports["mcp"]), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise AssertionError("MCP HTTP service did not start")
        __import__("asyncio").run(_exercise_mcp_boundary(
            monkeypatch, f"http://127.0.0.1:{ports['mcp']}/mcp"
        ))

        for name in ("coordinator", "requirement", "matching", "location", "notification"):
            env = {**base_env, "A2A_AGENT": name}
            port = ports[name]
            agent = name.upper() + "AGENT"
            urls[name] = f"http://127.0.0.1:{port}"
            env[f"{agent}_A2A_URL"] = f"{urls[name]}/a2a"
            if name != "coordinator":
                env[f"{agent}_BASE_URL"] = urls[name]
            for target in ("requirement", "matching", "location", "notification"):
                target_agent = target.upper() + "AGENT"
                env[f"{target_agent}_BASE_URL"] = f"http://127.0.0.1:{ports[target]}"
            process = subprocess.Popen(
                [*launch_prefix, "-m", "uvicorn", "app.agents.a2a.service:create_service",
                 "--factory", "--host", "127.0.0.1", "--port", str(port)],
                cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            processes.append(process)
            card = _wait_for_card(f"{urls[name]}/.well-known/agent-card.json", process)
            cards[name] = card
            assert card["name"] == f"{name.title()}Agent"

        monkeypatch.setenv("A2A_TIMEOUT_SECONDS", "20")
        monkeypatch.setenv("A2A_MAX_RETRIES", "1")
        for name in ("coordinator", "requirement", "matching", "location", "notification"):
            monkeypatch.setenv(name.upper() + "AGENT_BASE_URL", urls[name])
        from app.agents.a2a.client import call_remote_agent
        asyncio = __import__("asyncio")
        requirement = asyncio.run(call_remote_agent("REQUIREMENTAGENT", {
            "request_id": 1, "hospital_id": 1, "blood_group": "O+", "units_required": 1, "urgency": "HIGH"
        }, port=ports["requirement"]))
        assert requirement["requirement"]["valid"] is True
        matching = asyncio.run(call_remote_agent("MATCHINGAGENT", {"blood_group": "O+", "request_id": 1}, port=ports["matching"]))
        assert "matches" in matching
        location = asyncio.run(call_remote_agent("LOCATIONAGENT", {
            "hospital_coords": {"latitude": 12.0, "longitude": 77.0}, "candidates": []
        }, port=ports["location"]))
        assert location["candidates"] == []
        notification = asyncio.run(call_remote_agent("NOTIFICATIONAGENT", {
            "hospital_id": 1, "request_id": 1, "fulfillment_plan": {
                "status": "UNFULFILLED", "total_units": 0, "details": {"units_required": 0}, "plan": []
            }
        }, port=ports["notification"]))
        assert notification["request_id"] == 1
        with pytest.raises(RuntimeError, match="Requirement validation failed"):
            asyncio.run(call_remote_agent("REQUIREMENTAGENT", {
                "request_id": 1, "hospital_id": 1, "blood_group": "BAD", "units_required": 1, "urgency": "HIGH"
            }, port=ports["requirement"]))
        monkeypatch.setenv("COORDINATORAGENT_BASE_URL", urls["coordinator"])
        result = __import__("asyncio").run(call_remote_agent(
            "COORDINATORAGENT", {
                "user_request": "Urgently need 1 unit of O+ at A2A Test Hospital",
                "request_id": 1,
                "persist": True,
            }, port=ports["coordinator"]
        ))
        assert result["success"] is True
        assert result["request_id"] == 1
        assert result["plan"]["blood_group"] == "O+"
        assert "llm" not in result
        assert result["notifications"]["request_id"] == 1
        assert result["notifications"]["success"] is True
        assert {item["receiver"] for item in result["a2a_trace"]} >= {
            "RequirementAgent", "MatchingAgent", "LocationAgent", "NotificationAgent"
        }
        assert any(
            item["sender"] == "MatchingAgent" and item["receiver"] == "LocationAgent"
            for item in result["a2a_trace"]
        )
        monkeypatch.setenv("REQUIREMENTAGENT_BASE_URL", "http://127.0.0.1:1")
        monkeypatch.setenv("A2A_TIMEOUT_SECONDS", "0.25")
        monkeypatch.setenv("A2A_MAX_RETRIES", "0")
        started = time.monotonic()
        with pytest.raises(RuntimeError, match="A2A call to 'REQUIREMENTAGENT' failed"):
            asyncio.run(call_remote_agent(
                "REQUIREMENTAGENT", {"hospital_id": 1}, port=1
            ))
        assert time.monotonic() - started < 3

        class MalformedOrSlowHandler(BaseHTTPRequestHandler):
            mode = "malformed"

            def log_message(self, *args):
                pass

            def do_GET(self):
                card = dict(cards["requirement"])
                card["supportedInterfaces"] = [dict(card["supportedInterfaces"][0], url=f"http://127.0.0.1:{self.server.server_port}/a2a")]
                body = json.dumps(card).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                if self.mode == "slow":
                    time.sleep(0.5)
                    body = b"{}"
                else:
                    body = b"{malformed-json"
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except OSError:
                    pass  # expected when the client times out

        def assert_protocol_failure(mode, timeout):
            MalformedOrSlowHandler.mode = mode
            server = ThreadingHTTPServer(("127.0.0.1", 0), MalformedOrSlowHandler)
            server.daemon_threads = True
            process = __import__("threading").Thread(target=server.serve_forever, daemon=True)
            process.start()
            try:
                monkeypatch.setenv("REQUIREMENTAGENT_BASE_URL", f"http://127.0.0.1:{server.server_port}")
                monkeypatch.setenv("A2A_TIMEOUT_SECONDS", str(timeout))
                monkeypatch.setenv("A2A_MAX_RETRIES", "0")
                with pytest.raises(RuntimeError, match="A2A call to 'REQUIREMENTAGENT' failed"):
                    asyncio.run(call_remote_agent("REQUIREMENTAGENT", {}, port=1))
            finally:
                server.shutdown()
                server.server_close()
                process.join(timeout=2)

        assert_protocol_failure("malformed", 2)
        assert_protocol_failure("slow", 0.15)
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        engine.dispose()

