"""Synthetic, deterministic data. Nothing here is real."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

_rng = random.Random(2026)
_FIRST = ["Asha", "Ben", "Chen", "Dara", "Elif", "Farah", "Gus", "Hana", "Ivan", "Jo"]
_LAST = ["Rao", "Smith", "Wei", "Okafor", "Kaya", "Haddad", "Berg", "Sato", "Petrov", "Lee"]
_SUBJECTS = [
    "Card declined at checkout",
    "Refund not received",
    "Cannot log in",
    "Wrong item delivered",
    "Change delivery address",
    "Invoice copy needed",
    "Subscription cancelled by mistake",
    "App crashes on payment",
]


@dataclass
class Store:
    customers: dict[str, dict[str, str]] = field(default_factory=dict)
    payments: dict[str, dict[str, object]] = field(default_factory=dict)
    tickets: dict[str, dict[str, object]] = field(default_factory=dict)
    next_ticket: int = 5001


def seed() -> Store:
    store = Store()
    for i in range(1, 41):
        cid = f"CUST-{i:03d}"
        first, last = _rng.choice(_FIRST), _rng.choice(_LAST)
        store.customers[cid] = {
            "id": cid,
            "name": f"{first} {last}",
            "email": f"{first.lower()}.{last.lower()}{i}@example.test",
            "segment": _rng.choice(["retail", "business", "vip"]),
        }
    for i in range(1, 121):
        pid = f"PAY-{1000 + i}"
        store.payments[pid] = {
            "id": pid,
            "order_id": f"ORD-{2000 + (i % 60)}",
            "customer_id": f"CUST-{(i % 40) + 1:03d}",
            "amount": round(_rng.uniform(5, 400), 2),
            "currency": "USD",
            "refunded": 0.0,
        }
    for i in range(1, 31):
        tid = f"TCK-{4000 + i}"
        store.tickets[tid] = {
            "id": tid,
            "subject": _rng.choice(_SUBJECTS),
            "status": _rng.choice(["open", "open", "pending", "closed"]),
            "priority": _rng.choice(["low", "normal", "high"]),
        }
    return store
