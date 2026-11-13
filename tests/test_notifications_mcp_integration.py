"""Isolated real-socket verification of Coordinator -> A2A NotificationAgent -> MCP -> data APIs."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from blood_bank_api.models import Base as BankBase, BloodBank as ApiBank, BloodInventory as ApiInventory
from donor_api.models import Base as DonorBase, Donor as ApiDonor
from app.database.session import Base as CoreBase
from app.models import BloodBank, BloodInventory, Hospital


def _port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _wait_http(url, process, timeout=35):
    deadline=time.monotonic()+timeout
    last=None
    while time.monotonic()<deadline:
        if process.poll() is not None:
            raise AssertionError(f"service exited ({process.returncode}) while waiting for {url}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return response.read()
        except Exception as exc:
            last=exc
            time.sleep(.2)
    raise AssertionError(f"service did not become ready at {url}: {last}")


def _seed_isolated_databases(tmp_path):
    bank_url=f"sqlite:///{(tmp_path/'bank-api.db').as_posix()}"
    donor_url=f"sqlite:///{(tmp_path/'donor-api.db').as_posix()}"
    core_url=f"sqlite:///{(tmp_path/'coordinator.db').as_posix()}"
    now=datetime.now(timezone.utc)

    engine=create_engine(bank_url)
    BankBase.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        bank=ApiBank(name="Integration Blood Centre",registration_number="INT-BB-1",address="1 Test Road",city="Bengaluru",district="Bengaluru Urban",state="Karnataka",pin_code="560001",latitude=12.9716,longitude=77.5946,contact_number="+91-00000-00001",contact_email="centre@example.invalid",operating_hours="24 hours",emergency_available=True,verification_status="verified",bank_type="government",last_updated=now)
        db.add(bank);db.flush()
        db.add(ApiInventory(blood_bank_id=bank.id,blood_group="A+",component_type="packed_red_blood_cells",available_units=5,reserved_units=0,last_updated=now,expiry_date=now+timedelta(days=20),availability_status="available"))
        db.commit()
    engine.dispose()

    engine=create_engine(donor_url)
    DonorBase.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        donor=ApiDonor(name="Consent Test Donor",age=30,blood_group="A+",city="Bengaluru",district="Bengaluru Urban",state="Karnataka",pin_code="560001",latitude=12.9716,longitude=77.5946,phone="+91-12345-12345",email="donor@example.invalid",registration_date=date.today()-timedelta(days=400),last_donation_date=date.today()-timedelta(days=120),donation_count=1,available=True,preferred_contact_method="email",notification_consent=True,verification_status="verified",eligibility_status="eligible",last_updated=now)
        db.add(donor);db.commit()
    engine.dispose()

    engine=create_engine(core_url)
    CoreBase.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        hospital=Hospital(name="MCP Notification Hospital",latitude=12.9716,longitude=77.5946,address="2 Test Road")
        bank=BloodBank(name="Integration Blood Centre",latitude=12.9716,longitude=77.5946,address="1 Test Road")
        db.add_all([hospital,bank]);db.flush()
        db.add(BloodInventory(bank_id=bank.bank_id,blood_group="A+",component_type="packed_red_blood_cells",units_available=5,expiry_date=date.today()+timedelta(days=20)))
        db.commit()
    engine.dispose()
    return bank_url,donor_url,core_url


def test_notification_agent_uses_existing_mcp_stack_and_coordinator_receives_results(tmp_path,monkeypatch):
    bank_url,donor_url,core_url=_seed_isolated_databases(tmp_path)
    ports={name:_port() for name in ("bank_api","donor_api","mcp","coordinator","requirement","matching","location","notification")}
    root=Path(__file__).resolve().parents[1]
    env=os.environ.copy()
    env.update({
        "OBSERVABILITY_ENABLED":"false","ENVIRONMENT":"development","LLM_PROVIDER":"mock",
        "DATABASE_URL":core_url,"BLOOD_BANK_DATABASE_URL":bank_url,"DONOR_DATABASE_URL":donor_url,
        "BLOOD_BANK_API_URL":f"http://127.0.0.1:{ports['bank_api']}","DONOR_API_URL":f"http://127.0.0.1:{ports['donor_api']}",
        "DATA_APIS_ENABLED":"true","NOTIFICATION_CHANNEL":"console",
        "MCP_URL":f"http://127.0.0.1:{ports['mcp']}/mcp","MCP_TIMEOUT_SECONDS":"12","MCP_MAX_RETRIES":"0",
        "A2A_TIMEOUT_SECONDS":"15","A2A_MAX_RETRIES":"0",
        "NOTIFICATION_PUBLIC_BASE_URL":f"http://127.0.0.1:{ports['bank_api']}",
        "NOTIFICATION_PUBLIC_DONOR_URL":f"http://127.0.0.1:{ports['donor_api']}",
    })
    procs=[]
    try:
        specs=[
            ("bank_api",[sys.executable,"-m","uvicorn","blood_bank_api.main:app","--host","127.0.0.1","--port",str(ports["bank_api"])]),
            ("donor_api",[sys.executable,"-m","uvicorn","donor_api.main:app","--host","127.0.0.1","--port",str(ports["donor_api"])]),
            ("mcp",[sys.executable,"-m","app.mcp.protocol_server"]),
        ]
        for name in ("coordinator","requirement","matching","location","notification"):
            specs.append((name,[sys.executable,"-m","uvicorn","app.agents.a2a.service:create_service","--factory","--host","127.0.0.1","--port",str(ports[name])]))
        for name,command in specs:
            child_env={**env,"A2A_AGENT":name,"MCP_PORT":str(ports["mcp"])}
            if name in {"coordinator","requirement","matching","location","notification"}:
                child_env[f"{name.upper()}AGENT_A2A_URL"]=f"http://127.0.0.1:{ports[name]}/a2a"
            for target in ("coordinator","requirement","matching","location","notification"):
                child_env[f"{target.upper()}AGENT_BASE_URL"]=f"http://127.0.0.1:{ports[target]}"
            proc=subprocess.Popen(command,cwd=root,env=child_env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            procs.append(proc)
            if name in {"bank_api","donor_api"}:
                _wait_http(f"http://127.0.0.1:{ports[name]}/health",proc)
            elif name=="mcp":
                deadline=time.monotonic()+35
                while time.monotonic()<deadline:
                    if proc.poll() is not None:raise AssertionError("MCP server exited during startup")
                    try:
                        with socket.create_connection(("127.0.0.1",ports["mcp"]),timeout=.5):break
                    except OSError:time.sleep(.2)
                else:raise AssertionError("official MCP server did not start")
            else:
                _wait_http(f"http://127.0.0.1:{ports[name]}/.well-known/agent-card.json",proc)

        monkeypatch.setenv("MCP_URL",env["MCP_URL"])
        monkeypatch.setenv("DATA_APIS_ENABLED","true")
        monkeypatch.setenv("NOTIFICATIONAGENT_BASE_URL",f"http://127.0.0.1:{ports['notification']}")
        monkeypatch.setenv("COORDINATORAGENT_BASE_URL",f"http://127.0.0.1:{ports['coordinator']}")
        from app.mcp.client import call_remote_tool
        import asyncio
        bank_tool=asyncio.run(call_remote_tool("send_blood_bank_notification",{
            "blood_bank_id":1,"blood_request_id":700,"blood_group":"A+","inventory_blood_group":"A+","component_type":"packed_red_blood_cells","required_units":1,"channel":"console","message":"MCP integration test","idempotency_key":"mcp-bank-700-1",
        }))
        donor_tool=asyncio.run(call_remote_tool("send_donor_notification",{
            "donor_id":1,"blood_request_id":700,"blood_group":"A+","component_type":"packed_red_blood_cells","channel":"console","message":"MCP integration test","hospital_latitude":12.9716,"hospital_longitude":77.5946,"idempotency_key":"mcp-donor-700-1",
        }))
        for output in (bank_tool,donor_tool):
            assert output["delivery_status"]=="simulated"
            assert output["response_status"]=="pending"
            assert output.get("delivered_at") is None

        from app.agents.a2a.client import call_remote_agent
        coordinator=asyncio.run(call_remote_agent("COORDINATORAGENT",{
            "user_request":"Urgently need 1 unit of A+ packed red blood cells at MCP Notification Hospital","persist":True,
        },port=ports["coordinator"]))
        assert coordinator["success"] is True
        assert coordinator["notifications"]["success"] is True
        assert coordinator["notifications"]["recipient_notifications"]
        assert all(item["delivery_status"]=="simulated" for item in coordinator["notifications"]["recipient_notifications"])

        agent_result=asyncio.run(call_remote_agent("NOTIFICATIONAGENT",{
            "hospital_id":1,"request_id":701,"hospital_name":"MCP Notification Hospital","blood_group":"A+","component_type":"packed_red_blood_cells",
            "hospital_coords":{"latitude":12.9716,"longitude":77.5946},
            "fulfillment_plan":{"status":"PARTIALLY_FULFILLED","total_units":2,"details":{"units_required":3},"plan":[
                {"source_type":"BLOOD_BANK","source_id":1,"blood_group":"A+","component_type":"packed_red_blood_cells","units":1},
                {"source_type":"DONOR","source_id":1,"blood_group":"A+","component_type":"packed_red_blood_cells","units":1},
            ]},
        },port=ports["notification"]))
        results=agent_result["recipient_notifications"]
        assert len(results)==2
        assert any("blood_bank_id" in item for item in results)
        assert any("donor_id" in item for item in results)
        assert all(item["delivery_status"]=="simulated" and item["response_status"]=="pending" for item in results)

        bank_db=__import__("sqlite3").connect(f"file:{(tmp_path/'bank-api.db').as_posix()}?mode=ro",uri=True)
        donor_db=__import__("sqlite3").connect(f"file:{(tmp_path/'donor-api.db').as_posix()}?mode=ro",uri=True)
        assert bank_db.execute("select count(*) from blood_bank_notifications").fetchone()[0]==3
        assert donor_db.execute("select count(*) from donor_notifications where idempotency_key='mcp-donor-700-1'").fetchone()[0]==1
        assert bank_db.execute("select delivery_status,response_status from blood_bank_notifications order by id").fetchall()==[("simulated","pending")]*3
        assert donor_db.execute("select delivery_status,response_status from donor_notifications where idempotency_key='mcp-donor-700-1'").fetchone()==("simulated","pending")
        bank_db.close();donor_db.close()
    finally:
        for proc in reversed(procs):
            if proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
