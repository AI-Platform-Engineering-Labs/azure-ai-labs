"""Prometheus metrics. The Gateway only exports global counters today, so per-agent and
per-tool visibility comes from the lab's own servers and agents (see docs/FINDINGS.md)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from prometheus_client import Counter, Histogram

# --- Server side: what the MCP servers actually executed ---------------------------------

SERVER_CALLS = Counter(
    "kavrynt_lab_mcp_tool_calls_total",
    "Tool calls executed by a lab MCP server.",
    ["route", "tool", "agent", "risk", "side_effect", "outcome"],
)
SERVER_SECONDS = Histogram(
    "kavrynt_lab_mcp_tool_seconds",
    "Tool execution time in a lab MCP server.",
    ["route", "tool"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

# --- Agent side: what agents attempted, and what governance should have decided ---------

AGENT_CALLS = Counter(
    "kavrynt_lab_agent_calls_total",
    "Tool calls attempted by lab agents through the Gateway.",
    ["agent", "route", "tool", "expected", "outcome"],
)
AGENT_SECONDS = Histogram(
    "kavrynt_lab_agent_call_seconds",
    "End-to-end tool call time through the Gateway.",
    ["agent", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
UNGOVERNED = Counter(
    "kavrynt_lab_ungoverned_calls_total",
    "Calls that policy says should be denied or need approval, but ran anyway.",
    ["agent", "route", "tool", "expected"],
)
OVERBLOCKED = Counter(
    "kavrynt_lab_overblocked_calls_total",
    "Calls that policy allows, but the control plane refused.",
    ["agent", "route", "tool", "outcome"],
)


@contextmanager
def observe_tool(route: str, tool: str, agent: str, risk: str, side_effect: str) -> Iterator[None]:
    started = time.perf_counter()
    outcome = "ok"
    try:
        yield
    except Exception:
        outcome = "error"
        raise
    finally:
        SERVER_SECONDS.labels(route, tool).observe(time.perf_counter() - started)
        SERVER_CALLS.labels(route, tool, agent, risk, side_effect, outcome).inc()
