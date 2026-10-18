"""Agents: outcome classification from real HTTP statuses, and governance scoring."""

from __future__ import annotations

import asyncio
import random

import httpx2
import pytest
from prometheus_client import REGISTRY
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from kavrynt_lab import agent
from kavrynt_lab.agent import PERSONAS, call_tool, classify
from kavrynt_lab.catalog import PAYMENTS, SUPPORT
from kavrynt_lab.expectations import Expectations
from kavrynt_lab.server import build_app
from tests.conftest import EXPECTATIONS


def test_expectations_file():
    e = Expectations.load(EXPECTATIONS)
    assert e.decide("support-agent", SUPPORT.route, "search_tickets") == "allow"
    assert e.decide("support-agent", SUPPORT.route, "delete_ticket") == "approve"
    assert e.decide("payments-agent", PAYMENTS.route, "refund_payment") == "approve"
    assert e.decide("payments-agent", PAYMENTS.route, "export_customer_data") == "deny"
    assert e.decide("rogue-agent", PAYMENTS.route, "export_customer_data") == "deny"
    assert e.decide("someone-new", SUPPORT.route, "search_tickets") == "deny"  # default


def test_every_persona_targets_known_tools():
    for persona in PERSONAS.values():
        assert persona.steps and all(s.weight > 0 for s in persona.steps)


@pytest.mark.parametrize(
    ("status", "outcome"),
    [(401, "unauthenticated"), (403, "denied"), (404, "not_found"), (502, "upstream_error")],
)
async def test_refusals_are_classified_from_http_status(background, status, outcome):
    async def refuse(_: Request) -> JSONResponse:
        return JSONResponse({"error": "refused"}, status_code=status)

    app = Starlette(routes=[Route("/mcp/{route}", refuse, methods=["POST", "GET", "DELETE"])])
    with background(app) as srv:
        got, got_status, _ = await call_tool(
            srv.url, "rogue-agent", "x.y", "anything", {}, timeout=5
        )
    assert (got, got_status) == (outcome, status)


def test_classify_without_http_error():
    assert classify(200, None, False) == "ok"
    assert classify(200, None, True) == "tool_error"
    assert classify(None, RuntimeError("down"), False) == "unreachable"
    # tools/call answered 2xx: it got past the control plane, even if the client failed later.
    assert classify(200, RuntimeError("later"), False, called=True) == "tool_error"
    assert classify(None, ExceptionGroup("g", [httpx2.ReadTimeout("slow")]), False) == "timeout"


async def test_risky_calls_that_run_count_as_ungoverned(monkeypatch):
    async def fake_call(gateway, name, route, tool, args, timeout=15):
        return "ok", 200, ""

    monkeypatch.setattr(agent, "call_tool", fake_call)
    labels = {
        "agent": "rogue-agent",
        "route": PAYMENTS.route,
        "tool": "export_customer_data",
        "expected": "deny",
    }
    before = REGISTRY.get_sample_value("kavrynt_lab_ungoverned_calls_total", labels) or 0.0

    rogue = PERSONAS["rogue-agent"]
    only_export = type(rogue)(
        rogue.name, tuple(s for s in rogue.steps if s.tool == "export_customer_data")
    )
    result = await agent.act_once(
        only_export, "http://gw", Expectations.load(EXPECTATIONS), random.Random(1)
    )

    assert (result.expected, result.outcome) == ("deny", "ok")
    assert REGISTRY.get_sample_value("kavrynt_lab_ungoverned_calls_total", labels) == before + 1


async def test_enforced_denial_is_not_ungoverned(monkeypatch):
    async def denied(gateway, name, route, tool, args, timeout=15):
        return "denied", 403, ""

    monkeypatch.setattr(agent, "call_tool", denied)
    rogue = PERSONAS["rogue-agent"]
    only_delete = type(rogue)(
        rogue.name, tuple(s for s in rogue.steps if s.tool == "delete_ticket")
    )
    labels = {
        "agent": "rogue-agent",
        "route": SUPPORT.route,
        "tool": "delete_ticket",
        "expected": "deny",
    }
    before = REGISTRY.get_sample_value("kavrynt_lab_ungoverned_calls_total", labels) or 0.0
    await agent.act_once(
        only_delete, "http://gw", Expectations.load(EXPECTATIONS), random.Random(1)
    )
    assert (
        REGISTRY.get_sample_value("kavrynt_lab_ungoverned_calls_total", labels) or 0.0
    ) == before


class InterceptMethod:
    """ASGI middleware in front of a real lab server: serves it at the Gateway's route path
    and lets one JSON-RPC method be refused with an HTTP status or delayed."""

    def __init__(self, app, method: str, status: int | None = None, delay: float = 0) -> None:  # type: ignore[no-untyped-def]
        self.app, self.method, self.status, self.delay = app, method, status, delay

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        scope = {**scope, "path": "/mcp", "raw_path": b"/mcp"}
        messages, body, more = [], b"", True
        while scope["method"] == "POST" and more:
            message = await receive()
            messages.append(message)
            body += message.get("body", b"")
            more = message.get("more_body", False)
        if agent._rpc_method(body) == self.method:
            if self.status is not None:
                return await JSONResponse({"error": "refused"}, self.status)(scope, receive, send)
            await asyncio.sleep(self.delay)

        async def replay():  # type: ignore[no-untyped-def]
            return messages.pop(0) if messages else await receive()

        await self.app(scope, replay, send)


def _executed(tool: str) -> float:
    labels = {
        "route": SUPPORT.route,
        "tool": tool,
        "agent": "probe-agent",
        "risk": "high",
        "side_effect": "destructive",
        "outcome": "ok",
    }
    return REGISTRY.get_sample_value("kavrynt_lab_mcp_tool_calls_total", labels) or 0.0


async def test_outcome_follows_tools_call_not_later_requests(background):
    # Refusing only tools/list must not hide that the tool ran: the control plane let it through.
    app = InterceptMethod(build_app("support"), "tools/list", status=403)
    before = _executed("delete_ticket")
    with background(app) as srv:
        outcome, status, _ = await call_tool(
            srv.url, "probe-agent", SUPPORT.route, "delete_ticket", {"ticket_id": "TCK-4001"}
        )
    assert outcome in agent.REACHED_TOOL and status == 200
    assert _executed("delete_ticket") == before + 1


async def test_refused_tools_call_is_denied_and_never_runs(background):
    app = InterceptMethod(build_app("support"), "tools/call", status=403)
    before = _executed("delete_ticket")
    with background(app) as srv:
        outcome, status, _ = await call_tool(
            srv.url, "probe-agent", SUPPORT.route, "delete_ticket", {"ticket_id": "TCK-4002"}
        )
    assert (outcome, status) == ("denied", 403)
    assert _executed("delete_ticket") == before


async def test_slow_tools_call_is_a_timeout(background):
    app = InterceptMethod(build_app("support"), "tools/call", delay=3)
    with background(app) as srv:
        outcome, _, _ = await call_tool(
            srv.url, "probe-agent", SUPPORT.route, "search_tickets", {"query": "x"}, timeout=1
        )
    assert outcome == "timeout"


@pytest.mark.parametrize(
    "rule",
    [
        "{agent: a, server: s, tools: t, decision: allow}",  # typo: tools
        "{agent: a, server: s, decision: allow}",  # missing tool
        "{agent: a, server: s, tool: , decision: allow}",  # empty tool
        "{agent: a, server: s, tool: t, decision: maybe}",
    ],
)
def test_expectations_reject_rules_that_would_widen(tmp_path, rule):
    path = tmp_path / "expectations.yaml"
    path.write_text(f"default: deny\nrules:\n  - {rule}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        Expectations.load(path)


def test_direct_calls_around_the_gateway_are_always_denied():
    rogue = PERSONAS["rogue-agent"]
    direct = [s for s in rogue.steps if s.direct]
    assert direct and all(s.scored_route == f"{agent.DIRECT}{s.route}" for s in direct)
    e = Expectations.load(EXPECTATIONS)
    assert all(e.decide("rogue-agent", s.scored_route, s.tool) == "deny" for s in direct)
    # Even an agent allowed everything on the server through the Gateway.
    assert (
        e.decide("payments-agent", f"{agent.DIRECT}{PAYMENTS.route}", "search_payments") == "deny"
    )


async def test_direct_step_calls_the_service_and_scores_it_apart(monkeypatch):
    seen = {}

    async def fake_call(gateway, name, route, tool, args, timeout=15, url=None):
        seen.update(url=url, timeout=timeout)
        return "ok", 200, ""

    monkeypatch.setattr(agent, "call_tool", fake_call)
    rogue = PERSONAS["rogue-agent"]
    only_direct = type(rogue)(rogue.name, tuple(s for s in rogue.steps if s.direct))
    labels = {
        "agent": "rogue-agent",
        "route": f"{agent.DIRECT}{PAYMENTS.route}",
        "tool": "get_customer",
        "expected": "deny",
    }
    before = REGISTRY.get_sample_value("kavrynt_lab_ungoverned_calls_total", labels) or 0.0

    result = await agent.act_once(
        only_direct, "http://gw", Expectations.load(EXPECTATIONS), random.Random(1)
    )

    assert seen == {"url": PAYMENTS.direct_url, "timeout": agent.DIRECT_TIMEOUT}
    assert result.route == labels["route"]
    # A direct call that reaches the tool is ungoverned: nothing stopped it.
    assert REGISTRY.get_sample_value("kavrynt_lab_ungoverned_calls_total", labels) == before + 1


async def test_call_tool_honours_an_explicit_url(background):
    app = InterceptMethod(build_app("support"), "none")
    with background(app) as srv:
        outcome, status, _ = await call_tool(
            "http://127.0.0.1:9",  # nothing listens here: the URL must win
            "probe-agent",
            SUPPORT.route,
            "search_tickets",
            {"query": "refund"},
            url=f"{srv.url}/mcp",
        )
    assert (outcome, status) == ("ok", 200)


async def test_blocked_connection_is_not_reaching_the_tool():
    # Port 9 (discard) refuses: what a NetworkPolicy reject looks like to the agent.
    outcome, status, _ = await call_tool(
        "http://gw",
        "probe-agent",
        SUPPORT.route,
        "search_tickets",
        {},
        timeout=2,
        url="http://127.0.0.1:9/mcp",
    )
    assert outcome in ("timeout", "unreachable") and status is None
