"""Scripted agents that call lab MCP servers through the Kavrynt Gateway.

Each call is classified from the real HTTP status (the MCP client hides it) and scored
against the expected governance: a call policy would deny that ran anyway is "ungoverned".
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from kavrynt_lab.catalog import PAYMENTS, SUPPORT
from kavrynt_lab.expectations import Expectations
from kavrynt_lab.metrics import AGENT_CALLS, AGENT_SECONDS, OVERBLOCKED, UNGOVERNED

log = logging.getLogger("kavrynt_lab.agent")
AGENT_HEADER = "X-Lab-Agent"
REACHED_TOOL = ("ok", "tool_error")
REFUSED = ("denied", "unauthenticated", "pending_approval")

ArgsFactory = Callable[[random.Random], dict[str, Any]]


@dataclass(frozen=True)
class Step:
    route: str
    tool: str
    weight: float
    args: ArgsFactory


@dataclass(frozen=True)
class Persona:
    name: str
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class CallResult:
    agent: str
    route: str
    tool: str
    expected: str
    outcome: str
    status: int | None
    seconds: float
    detail: str = ""


# --- Argument generators (ids exist in kavrynt_lab.data) ---------------------------------


def _order(r: random.Random) -> dict[str, Any]:
    return {"order_id": f"ORD-{2000 + r.randint(0, 59)}"}


def _customer(r: random.Random) -> dict[str, Any]:
    return {"customer_id": f"CUST-{r.randint(1, 40):03d}"}


def _small_refund(r: random.Random) -> dict[str, Any]:
    return {"payment_id": f"PAY-{1000 + r.randint(1, 120)}", "amount": 1.0, "reason": "goodwill"}


def _large_refund(r: random.Random) -> dict[str, Any]:
    return {
        "payment_id": f"PAY-{1000 + r.randint(1, 120)}",
        "amount": 4.99,
        "reason": "because I can",
    }


def _export(r: random.Random) -> dict[str, Any]:
    return {"segment": r.choice(["vip", "all"])}


def _search(r: random.Random) -> dict[str, Any]:
    return {"query": r.choice(["refund", "card declined", "login", "delivery", "invoice"])}


def _new_ticket(r: random.Random) -> dict[str, Any]:
    return {
        "subject": r.choice(["Refund not received", "Cannot log in"]),
        "body": "Customer called.",
        "priority": "normal",
    }


def _ticket(r: random.Random) -> dict[str, Any]:
    return {"ticket_id": f"TCK-{4000 + r.randint(1, 30)}"}


P, S = PAYMENTS.route, SUPPORT.route
UNREGISTERED = "team-payments.ledger-mcp"

PERSONAS: dict[str, Persona] = {
    p.name: p
    for p in (
        Persona(
            "support-agent",
            (
                Step(S, "search_tickets", 6, _search),
                Step(S, "create_ticket", 3, _new_ticket),
                Step(S, "close_ticket", 1, _ticket),
                Step(S, "delete_ticket", 0.3, _ticket),
                Step(P, "search_payments", 1, _order),
            ),
        ),
        Persona(
            "payments-agent",
            (
                Step(P, "search_payments", 6, _order),
                Step(P, "get_customer", 2, _customer),
                Step(P, "refund_payment", 1, _small_refund),
                Step(P, "export_customer_data", 0.3, _export),
            ),
        ),
        Persona(
            "rogue-agent",
            (
                Step(S, "search_tickets", 2, _search),
                Step(S, "delete_ticket", 2, _ticket),
                Step(P, "refund_payment", 2, _large_refund),
                Step(P, "export_customer_data", 2, _export),
                Step(P, "get_customer", 1, _customer),
                Step(UNREGISTERED, "read_ledger", 1, lambda r: {}),
            ),
        ),
    )
}


# --- Calling through the Gateway -----------------------------------------------------------


def classify(
    status: int | None, error: BaseException | None, is_error: bool, called: bool = False
) -> str:
    """Outcome of one tool call, as decided by the control plane.

    `status` is the HTTP status of the `tools/call` request when `called` is true, otherwise
    of the last request the session made (the one that stopped it). A 2xx on `tools/call` means
    the call got past the control plane: it counts as reaching the tool even if the client fails
    afterwards. A control plane that refuses with HTTP 200 and a JSON-RPC error would be scored
    as reached, which is why denials should keep their HTTP status (docs/FINDINGS.md F7).
    """
    if called and status is not None and 200 <= status < 300:
        return "tool_error" if (is_error or error is not None) else "ok"
    if error is None:
        return "tool_error" if is_error else "ok"
    if _find(error, httpx2.TimeoutException) is not None:
        return "timeout"
    if status == 401:
        return "unauthenticated"
    if status == 403:
        return "denied"
    if status == 404:
        return "not_found"
    if status in (202, 428):  # reserved for approval flows (ADR-0003 / approvals service)
        return "pending_approval"
    if status is not None and status >= 500:
        return "upstream_error"
    if status is not None and status < 300:
        return "protocol_error"
    return "unreachable"


def _find(error: BaseException, kind: type[BaseException]) -> BaseException | None:
    """First exception of `kind` in an exception, its group members or its causes."""
    seen: set[int] = set()
    stack: list[BaseException] = [error]
    while stack:
        exc = stack.pop()
        if id(exc) in seen:
            continue
        seen.add(id(exc))
        if isinstance(exc, kind):
            return exc
        if isinstance(exc, BaseExceptionGroup):
            stack.extend(exc.exceptions)
        stack.extend(e for e in (exc.__cause__, exc.__context__) if e is not None)
    return None


def _rpc_method(body: bytes) -> str:
    try:
        message = json.loads(body)
    except ValueError:
        return ""
    if isinstance(message, list):  # JSON-RPC batch: the first request decides
        message = message[0] if message else {}
    return message.get("method", "") if isinstance(message, dict) else ""


async def call_tool(
    gateway: str, agent: str, route: str, tool: str, args: dict[str, Any], timeout: float = 15
) -> tuple[str, int | None, str]:
    """Call one tool through the Gateway. Returns (outcome, HTTP status, detail).

    The MCP client hides HTTP statuses, so a response hook records them per JSON-RPC method:
    the session also sends discovery and `tools/list` requests, and only the `tools/call`
    request shows what the control plane did with the call.
    """
    statuses: dict[str, int] = {}
    last: list[int] = []

    async def record(response: httpx2.Response) -> None:
        if response.request.method != "POST":
            return
        last[:] = [response.status_code]
        try:
            method = _rpc_method(response.request.content)
        except httpx2.RequestNotRead:
            return
        if method:
            statuses[method] = response.status_code

    http = httpx2.AsyncClient(
        headers={AGENT_HEADER: agent}, timeout=timeout, event_hooks={"response": [record]}
    )
    url = f"{gateway.rstrip('/')}/mcp/{route}"
    error: BaseException | None = None
    is_error = False
    detail = ""
    try:
        async with http, Client(streamable_http_client(url, http_client=http)) as client:
            result = await client.call_tool(tool, args)
            is_error = bool(result.is_error)
            if is_error and result.content:
                detail = getattr(result.content[0], "text", "")[:200]
    except BaseException as exc:  # ExceptionGroup from the client's task group
        if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)):
            raise
        error = exc
        detail = repr(exc)[:200]
    called = "tools/call" in statuses
    status = statuses["tools/call"] if called else (last[0] if last else None)
    return classify(status, error, is_error, called), status, detail


async def act_once(
    persona: Persona, gateway: str, expectations: Expectations, rng: random.Random
) -> CallResult:
    step = rng.choices(persona.steps, weights=[s.weight for s in persona.steps])[0]
    expected = expectations.decide(persona.name, step.route, step.tool)
    started = time.perf_counter()
    outcome, status, detail = await call_tool(
        gateway, persona.name, step.route, step.tool, step.args(rng)
    )
    seconds = time.perf_counter() - started

    AGENT_CALLS.labels(persona.name, step.route, step.tool, expected, outcome).inc()
    AGENT_SECONDS.labels(persona.name, step.route).observe(seconds)
    if expected != "allow" and outcome in REACHED_TOOL:
        UNGOVERNED.labels(persona.name, step.route, step.tool, expected).inc()
    if expected == "allow" and outcome in REFUSED:
        OVERBLOCKED.labels(persona.name, step.route, step.tool, outcome).inc()
    return CallResult(
        persona.name, step.route, step.tool, expected, outcome, status, seconds, detail
    )


async def run(
    persona_name: str,
    gateway: str,
    expectations: Expectations,
    interval: float = 2.0,
    max_calls: int | None = None,
    seed: int | None = None,
) -> list[CallResult]:
    """Act until `max_calls` calls (forever when None). Results are kept only when bounded,
    so a long-running agent does not grow without limit."""
    persona = PERSONAS[persona_name]
    rng = random.Random(seed)
    results: list[CallResult] = []
    calls = 0
    while max_calls is None or calls < max_calls:
        result = await act_once(persona, gateway, expectations, rng)
        calls += 1
        if max_calls is not None:
            results.append(result)
        log.info(json.dumps({**result.__dict__, "seconds": round(result.seconds, 4)}, default=str))
        if max_calls is None or calls < max_calls:
            await asyncio.sleep(interval * rng.uniform(0.5, 1.5))
    return results
