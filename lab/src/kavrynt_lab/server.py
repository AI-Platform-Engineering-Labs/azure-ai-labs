"""Lab MCP servers (Streamable HTTP, stateless JSON responses).

Stateless JSON keeps every MCP request a plain request/response, which is what the Gateway
MVP proxies today (it copies response bodies without flushing a stream).
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from kavrynt_lab import __version__
from kavrynt_lab.catalog import SERVERS, ServerSpec, ToolSpec
from kavrynt_lab.data import Store, seed
from kavrynt_lab.metrics import observe_tool

AGENT_HEADER = "x-lab-agent"


def _annotations(tool: ToolSpec) -> ToolAnnotations:
    return ToolAnnotations(
        title=tool.name.replace("_", " ").capitalize(),
        read_only_hint=tool.side_effect == "read",
        destructive_hint=tool.side_effect == "destructive",
        idempotent_hint=tool.side_effect == "read",
        open_world_hint=False,
    )


def _agent(ctx: Context) -> str:
    headers = ctx.headers or {}
    return headers.get(AGENT_HEADER) or "unknown"


class _Toolbox:
    """Registers a server's tools and wraps each call in metrics."""

    def __init__(self, server: MCPServer, spec: ServerSpec) -> None:
        self.server = server
        self.spec = spec
        self.tools = {t.name: t for t in spec.tools}

    def tool(self, name: str):  # type: ignore[no-untyped-def]
        tool = self.tools[name]
        return self.server.tool(
            name=name, description=tool.description, annotations=_annotations(tool), meta=tool.meta
        )

    def observe(self, name: str, ctx: Context):  # type: ignore[no-untyped-def]
        tool = self.tools[name]
        return observe_tool(self.spec.route, name, _agent(ctx), tool.risk, tool.side_effect)


def _payments(box: _Toolbox, store: Store) -> None:
    @box.tool("search_payments")
    async def search_payments(order_id: str, ctx: Context) -> dict[str, Any]:
        with box.observe("search_payments", ctx):
            found = [p for p in store.payments.values() if p["order_id"] == order_id]
            return {"order_id": order_id, "payments": found}

    @box.tool("get_customer")
    async def get_customer(customer_id: str, ctx: Context) -> dict[str, Any]:
        with box.observe("get_customer", ctx):
            customer = store.customers.get(customer_id)
            if customer is None:
                raise ToolError(f"no customer {customer_id}")
            return customer

    @box.tool("refund_payment")
    async def refund_payment(
        payment_id: str, amount: float, reason: str, ctx: Context
    ) -> dict[str, Any]:
        with box.observe("refund_payment", ctx):
            payment = store.payments.get(payment_id)
            if payment is None:
                raise ToolError(f"no payment {payment_id}")
            remaining = float(payment["amount"]) - float(payment["refunded"])  # type: ignore[arg-type]
            if amount <= 0 or amount > remaining:
                raise ToolError(f"amount must be between 0 and {remaining:.2f}")
            payment["refunded"] = round(float(payment["refunded"]) + amount, 2)  # type: ignore[arg-type]
            return {"payment_id": payment_id, "refunded": amount, "remaining": remaining - amount}

    @box.tool("export_customer_data")
    async def export_customer_data(
        segment: Literal["retail", "business", "vip", "all"], ctx: Context
    ) -> dict[str, Any]:
        with box.observe("export_customer_data", ctx):
            rows = [
                c for c in store.customers.values() if segment == "all" or c["segment"] == segment
            ]
            return {"segment": segment, "count": len(rows), "customers": rows}


def _support(box: _Toolbox, store: Store) -> None:
    @box.tool("search_tickets")
    async def search_tickets(query: str, ctx: Context) -> dict[str, Any]:
        with box.observe("search_tickets", ctx):
            words = {w.lower() for w in query.split()}
            hits = [
                t
                for t in store.tickets.values()
                if words & {w.lower() for w in str(t["subject"]).split()}
            ]
            return {"query": query, "tickets": hits[:10]}

    @box.tool("create_ticket")
    async def create_ticket(
        subject: str, body: str, priority: Literal["low", "normal", "high"], ctx: Context
    ) -> dict[str, Any]:
        with box.observe("create_ticket", ctx):
            tid = f"TCK-{store.next_ticket}"
            store.next_ticket += 1
            ticket = {"id": tid, "subject": subject, "status": "open", "priority": priority}
            store.tickets[tid] = ticket
            return ticket

    @box.tool("close_ticket")
    async def close_ticket(ticket_id: str, ctx: Context) -> dict[str, Any]:
        with box.observe("close_ticket", ctx):
            ticket = store.tickets.get(ticket_id)
            if ticket is None:
                raise ToolError(f"no ticket {ticket_id}")
            ticket["status"] = "closed"
            return ticket

    @box.tool("delete_ticket")
    async def delete_ticket(ticket_id: str, ctx: Context) -> dict[str, Any]:
        with box.observe("delete_ticket", ctx):
            if store.tickets.pop(ticket_id, None) is None:
                raise ToolError(f"no ticket {ticket_id}")
            return {"deleted": ticket_id}


def build_server(persona: str, store: Store | None = None) -> MCPServer:
    spec = SERVERS[persona]
    store = store or seed()
    server = MCPServer(name=spec.name, version=__version__, description=spec.description)
    box = _Toolbox(server, spec)
    {"payments": _payments, "support": _support}[persona](box, store)

    @server.custom_route("/metrics", methods=["GET"], include_in_schema=False)
    async def metrics(_: Request) -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @server.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def healthz(_: Request) -> Response:
        return JSONResponse({"status": "ok", "server": spec.name})

    return server


def build_app(persona: str, store: Store | None = None):  # type: ignore[no-untyped-def]
    # host="0.0.0.0": requests arrive from the Gateway with the Service's host name, so the
    # SDK's localhost-only DNS-rebinding guard must not apply inside the cluster.
    return build_server(persona, store).streamable_http_app(
        json_response=True, stateless_http=True, host="0.0.0.0"
    )


def serve(persona: str, port: int) -> None:
    import uvicorn

    uvicorn.run(build_app(persona), host="0.0.0.0", port=port, log_level="info")
