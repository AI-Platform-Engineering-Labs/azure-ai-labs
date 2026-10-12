"""In-cluster checks: the lab works end to end and the metrics tell the governance story."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from kavrynt_lab.agent import UNREGISTERED, call_tool
from kavrynt_lab.catalog import META_RISK, SERVERS


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


async def _gateway_ready(gateway: str) -> Check:
    async with httpx2.AsyncClient(timeout=10) as http:
        resp = await http.get(f"{gateway}/readyz")
    return Check("gateway ready", resp.status_code == 200, resp.text.strip()[:120])


async def _routes(gateway: str, timeout: float = 60) -> Check:
    """The Gateway syncs routes from MCPServer resources shortly after they are applied."""
    expected = {s.route for s in SERVERS.values()}
    deadline = time.monotonic() + timeout
    async with httpx2.AsyncClient(timeout=10) as http:
        while True:
            body = (await http.get(f"{gateway}/v1/routes")).json()
            routes = {r["name"] for r in body["routes"]}
            missing = expected - routes
            if not missing or time.monotonic() > deadline:
                break
            await asyncio.sleep(3)
    return Check(
        "lab routes registered", not missing, f"routes={sorted(routes)} missing={sorted(missing)}"
    )


async def _tools_through_gateway(gateway: str) -> list[Check]:
    checks = []
    for spec in SERVERS.values():
        http = httpx2.AsyncClient(headers={"X-Lab-Agent": "lab-check"}, timeout=15)
        async with (
            http,
            Client(streamable_http_client(f"{gateway}/mcp/{spec.route}", http_client=http)) as c,
        ):
            listed = (await c.list_tools()).tools
        names = {t.name for t in listed}
        expected = {t.name for t in spec.tools}
        with_risk = sum(1 for t in listed if (t.meta or {}).get(META_RISK))
        checks.append(
            Check(
                f"tools via gateway: {spec.route}",
                names == expected and with_risk == len(expected),
                f"{len(names)} tools, {with_risk} with risk metadata",
            )
        )
    return checks


async def _call_paths(gateway: str) -> list[Check]:
    ok, status, detail = await call_tool(
        gateway, "lab-check", SERVERS["support"].route, "search_tickets", {"query": "refund"}
    )
    missing, m_status, _ = await call_tool(gateway, "lab-check", UNREGISTERED, "read_ledger", {})
    return [
        Check(
            "read-only call through gateway", ok == "ok", f"outcome={ok} status={status} {detail}"
        ),
        Check(
            "unregistered server is refused",
            missing == "not_found",
            f"outcome={missing} status={m_status}",
        ),
    ]


async def _prometheus(prometheus: str, query: str) -> float:
    async with httpx2.AsyncClient(timeout=10) as http:
        data = (await http.get(f"{prometheus}/api/v1/query", params={"query": query})).json()
    # Several series can match (for example after a Gateway restart): add them up.
    return sum(float(r["value"][1]) for r in data.get("data", {}).get("result", []))


async def _metrics(prometheus: str, timeout: float) -> list[Check]:
    queries = {
        "gateway proxied requests scraped": "kavrynt_gateway_proxied_requests_total",
        "agent calls scraped": "sum(kavrynt_lab_agent_calls_total)",
        "server tool calls scraped": "sum(kavrynt_lab_mcp_tool_calls_total)",
    }
    deadline = time.monotonic() + timeout
    values: dict[str, float] = {}
    while True:
        values = {name: await _prometheus(prometheus, q) for name, q in queries.items()}
        if all(v > 0 for v in values.values()) or time.monotonic() > deadline:
            break
        await asyncio.sleep(5)
    checks = [Check(name, value > 0, f"{value:g}") for name, value in values.items()]
    gap = await _prometheus(prometheus, "sum(kavrynt_lab_ungoverned_calls_total)")
    # Informational: positive until the runtime enforces policy (ADR-0003).
    checks.append(
        Check("ungoverned risky calls (expected > 0 before enforcement)", True, f"{gap:g}")
    )
    return checks


async def run_checks(gateway: str, prometheus: str, metrics_timeout: float = 120) -> list[Check]:
    gateway = gateway.rstrip("/")
    steps: list[tuple[str, Callable[[], Awaitable[Check | list[Check]]]]] = [
        ("gateway ready", lambda: _gateway_ready(gateway)),
        ("lab routes registered", lambda: _routes(gateway)),
        ("tools via gateway", lambda: _tools_through_gateway(gateway)),
        ("call paths through gateway", lambda: _call_paths(gateway)),
        ("metrics in prometheus", lambda: _metrics(prometheus.rstrip("/"), metrics_timeout)),
    ]
    results: list[Check] = []
    for name, step in steps:
        try:
            outcome = await step()
        except Exception as exc:  # report and keep going: one table shows everything
            outcome = Check(name, False, repr(exc)[:200])
        results.extend(outcome if isinstance(outcome, list) else [outcome])
    return results
