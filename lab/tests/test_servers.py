"""Lab MCP servers: tools, governance metadata, behaviour, and metrics per calling agent."""

from __future__ import annotations

from mcp import Client
from prometheus_client import REGISTRY

from kavrynt_lab.agent import call_tool
from kavrynt_lab.catalog import META_RISK, META_SIDE_EFFECT, PAYMENTS, SUPPORT
from kavrynt_lab.server import build_server


async def test_tools_carry_governance_metadata():
    async with Client(build_server("payments")) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {t.name for t in PAYMENTS.tools}
    refund = tools["refund_payment"]
    assert refund.meta[META_RISK] == "high" and refund.meta[META_SIDE_EFFECT] == "write"
    assert refund.annotations.read_only_hint is False
    assert tools["search_payments"].annotations.read_only_hint is True


async def test_support_desk_behaviour():
    async with Client(build_server("support")) as client:
        found = await client.call_tool("search_tickets", {"query": "refund"})
        created = await client.call_tool(
            "create_ticket", {"subject": "Lab", "body": "hi", "priority": "high"}
        )
        ticket_id = created.structured_content["id"]
        deleted = await client.call_tool("delete_ticket", {"ticket_id": ticket_id})
        missing = await client.call_tool("delete_ticket", {"ticket_id": ticket_id})
    assert not found.is_error
    assert deleted.structured_content == {"deleted": ticket_id}
    assert missing.is_error  # second delete: the tool reports an error, the call still worked


async def test_refund_rules():
    async with Client(build_server("payments")) as client:
        bad = await client.call_tool(
            "refund_payment", {"payment_id": "PAY-1001", "amount": -5, "reason": "x"}
        )
        good = await client.call_tool(
            "refund_payment", {"payment_id": "PAY-1001", "amount": 1, "reason": "x"}
        )
    assert bad.is_error and not good.is_error


async def test_over_http_metrics_name_the_calling_agent(background):
    # Serve the MCP endpoint at /mcp/<route>, the path an agent uses through the Gateway.
    app = build_server("support").streamable_http_app(
        streamable_http_path=f"/mcp/{SUPPORT.route}",
        json_response=True,
        stateless_http=True,
        host="0.0.0.0",
    )

    def calls() -> float:
        return (
            REGISTRY.get_sample_value(
                "kavrynt_lab_mcp_tool_calls_total",
                {
                    "route": SUPPORT.route,
                    "tool": "search_tickets",
                    "agent": "support-agent",
                    "risk": "low",
                    "side_effect": "read",
                    "outcome": "ok",
                },
            )
            or 0.0
        )

    before = calls()
    with background(app) as srv:
        outcome, status, _ = await call_tool(
            srv.url, "support-agent", SUPPORT.route, "search_tickets", {"query": "login"}
        )
    assert (outcome, status) == ("ok", 200)
    assert calls() == before + 1
