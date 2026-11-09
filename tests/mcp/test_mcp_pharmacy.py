import pytest
from app.database.session import Base, SessionLocal, engine
from app.database.seed import seed_database
from app.mcp.server import create_extended_mcp_server
from app.mcp.tools.pharmacy_tool import (
    FIND_SUBSTITUTES_TOOL_NAME,
    CHECK_STOCK_TOOL_NAME,
)


@pytest.fixture(scope="module")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_database(db)
    yield db
    db.close()


def test_mcp_extended_server_has_pharmacy_tools():
    server = create_extended_mcp_server()
    tools = [t["name"] for t in server.list_tools()]
    assert FIND_SUBSTITUTES_TOOL_NAME in tools
    assert CHECK_STOCK_TOOL_NAME in tools


def test_mcp_find_substitutes_tool(db_session):
    server = create_extended_mcp_server()
    res = server.invoke_tool(
        FIND_SUBSTITUTES_TOOL_NAME,
        {"medicine_name": "Dolo 650"},
        db=db_session,
    )
    assert res["isError"] is False
    assert len(res["content"]) == 1
    assert "Calpol 650" in res["content"][0]["text"]


def test_mcp_check_stock_tool(db_session):
    server = create_extended_mcp_server()
    res = server.invoke_tool(
        CHECK_STOCK_TOOL_NAME,
        {"medicine_id": 1, "latitude": 28.6315, "longitude": 77.2167},
        db=db_session,
    )
    assert res["isError"] is False
    assert len(res["content"]) == 1
    assert '"available": true' in res["content"][0]["text"]
