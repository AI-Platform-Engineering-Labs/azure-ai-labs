"""Integration checks (AKS): the Key Vault canary and Kavrynt Cloud reachability."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from kavrynt_lab.check import run_integration_checks


def _cloud(status: int) -> Starlette:
    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok" if status == 200 else "blocked"}, status_code=status)

    return Starlette(routes=[Route("/healthz", healthz)])


async def test_integrations_pass_with_canary_and_reachable_cloud(background, tmp_path):
    secret = tmp_path / "lab-canary"
    secret.write_text("kavrynt-lab-canary\n", encoding="utf-8")
    with background(_cloud(200)) as srv:
        results = await run_integration_checks(str(secret), "kavrynt-lab-canary", srv.url)
    assert [r.ok for r in results] == [True, True]


@pytest.mark.parametrize("content", [None, "something else"])
async def test_missing_or_wrong_canary_fails_without_printing_it(background, tmp_path, content):
    secret = tmp_path / "lab-canary"
    if content is not None:
        secret.write_text(content, encoding="utf-8")
    with background(_cloud(200)) as srv:
        mounted, _ = await run_integration_checks(str(secret), "kavrynt-lab-canary", srv.url)
    assert not mounted.ok
    assert "something else" not in mounted.detail and "kavrynt-lab-canary" not in mounted.detail


async def test_cloud_firewall_refusal_says_what_to_change(background, tmp_path):
    secret = tmp_path / "lab-canary"
    secret.write_text("kavrynt-lab-canary", encoding="utf-8")
    with background(_cloud(403)) as srv:
        _, cloud = await run_integration_checks(str(secret), "kavrynt-lab-canary", srv.url)
    assert not cloud.ok and "DEV_ALLOWED_INGRESS_CIDRS" in cloud.detail
