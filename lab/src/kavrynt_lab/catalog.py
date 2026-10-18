"""The lab's MCP servers and their tools, with the governance metadata each tool carries.

Risk and side-effect levels use the same vocabulary as Kavrynt Cloud's tool records
(`riskLevel`, `sideEffectLevel`), and are published on each tool as MCP `_meta` so a
connector can sync them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Risk = Literal["low", "medium", "high"]
SideEffect = Literal["read", "write", "destructive"]

META_RISK = "kavrynt.io/risk"
META_SIDE_EFFECT = "kavrynt.io/side-effect"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    risk: Risk
    side_effect: SideEffect

    @property
    def meta(self) -> dict[str, str]:
        return {META_RISK: self.risk, META_SIDE_EFFECT: self.side_effect}


@dataclass(frozen=True)
class ServerSpec:
    persona: str
    name: str  # MCPServer name
    namespace: str  # Kubernetes namespace = owning team
    owner: str
    description: str
    tools: tuple[ToolSpec, ...]

    @property
    def route(self) -> str:
        """Gateway route id: <namespace>.<name>."""
        return f"{self.namespace}.{self.name}"

    @property
    def direct_url(self) -> str:
        """The server's own Service, around the Gateway. NetworkPolicy should refuse it."""
        return f"http://{self.name}.{self.namespace}.svc.cluster.local:8080/mcp"


PAYMENTS = ServerSpec(
    persona="payments",
    name="payments-mcp",
    namespace="team-payments",
    owner="payments-team",
    description="Payments and customer data for the payments team",
    tools=(
        ToolSpec("search_payments", "Find payments for an order id.", "low", "read"),
        ToolSpec(
            "get_customer",
            "Read one customer's profile, including contact details.",
            "medium",
            "read",
        ),
        ToolSpec(
            "refund_payment", "Refund all or part of a payment to the customer.", "high", "write"
        ),
        ToolSpec(
            "export_customer_data",
            "Export every customer in a segment, with contact details.",
            "high",
            "read",
        ),
    ),
)

SUPPORT = ServerSpec(
    persona="support",
    name="support-mcp",
    namespace="team-support",
    owner="support-team",
    description="Customer support desk for the support team",
    tools=(
        ToolSpec("search_tickets", "Search support tickets by text.", "low", "read"),
        ToolSpec("create_ticket", "Open a new support ticket.", "medium", "write"),
        ToolSpec("close_ticket", "Close a support ticket as resolved.", "medium", "write"),
        ToolSpec(
            "delete_ticket", "Permanently delete a ticket and its history.", "high", "destructive"
        ),
    ),
)

SERVERS: dict[str, ServerSpec] = {s.persona: s for s in (PAYMENTS, SUPPORT)}
ROUTES: dict[str, ServerSpec] = {s.route: s for s in SERVERS.values()}


def tool_spec(route: str, tool: str) -> ToolSpec | None:
    server = ROUTES.get(route)
    if server is None:
        return None
    return next((t for t in server.tools if t.name == tool), None)
