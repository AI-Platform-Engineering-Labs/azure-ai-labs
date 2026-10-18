"""kavrynt-lab server | agent | check | integrations-check"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="kavrynt-lab")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("server", help="run a lab MCP server")
    p.add_argument("--persona", choices=["payments", "support"], required=True)
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))

    p = sub.add_parser("agent", help="run a scripted agent through the Gateway")
    p.add_argument("--persona", required=True)
    p.add_argument(
        "--gateway",
        default=os.environ.get("KAVRYNT_GATEWAY", "http://kavrynt-gateway.kavrynt-system.svc:8080"),
    )
    p.add_argument(
        "--expectations",
        default=os.environ.get("LAB_EXPECTATIONS", "/etc/kavrynt-lab/expectations.yaml"),
    )
    p.add_argument("--interval", type=float, default=float(os.environ.get("AGENT_INTERVAL", "2")))
    p.add_argument("--metrics-port", type=int, default=int(os.environ.get("METRICS_PORT", "9100")))

    p = sub.add_parser("check", help="end-to-end checks from inside the cluster")
    p.add_argument(
        "--gateway",
        default=os.environ.get("KAVRYNT_GATEWAY", "http://kavrynt-gateway.kavrynt-system.svc:8080"),
    )
    p.add_argument(
        "--prometheus",
        default=os.environ.get("PROMETHEUS", "http://prometheus.lab-monitoring.svc:9090"),
    )
    p.add_argument("--metrics-timeout", type=float, default=120)

    p = sub.add_parser(
        "integrations-check", help="AKS: secret store and Kavrynt Cloud reachability"
    )
    p.add_argument("--secret-file", default="/mnt/secrets/lab-canary")
    p.add_argument("--expected-secret", default=os.environ.get("EXPECTED_SECRET", ""))
    p.add_argument("--cloud-url", default=os.environ.get("CLOUD_API_URL", ""))

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in ("httpx2", "httpx", "mcp"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if args.command == "server":
        from kavrynt_lab.server import serve

        serve(args.persona, args.port)
    elif args.command == "agent":
        from prometheus_client import start_http_server

        from kavrynt_lab.agent import run
        from kavrynt_lab.expectations import Expectations

        # Exit promptly on pod termination instead of waiting out the grace period.
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        start_http_server(args.metrics_port)
        expectations = Expectations.load(args.expectations)
        asyncio.run(run(args.persona, args.gateway, expectations, interval=args.interval))
    elif args.command == "check":
        from kavrynt_lab.check import run_checks

        _report(asyncio.run(run_checks(args.gateway, args.prometheus, args.metrics_timeout)))
    elif args.command == "integrations-check":
        from kavrynt_lab.check import run_integration_checks

        if not args.cloud_url or not args.expected_secret:
            parser.error("integrations-check needs --cloud-url and --expected-secret")
        _report(
            asyncio.run(
                run_integration_checks(args.secret_file, args.expected_secret, args.cloud_url)
            )
        )


def _report(results) -> None:  # type: ignore[no-untyped-def]
    width = max(len(r.name) for r in results)
    for r in results:
        print(f"{'PASS' if r.ok else 'FAIL'}  {r.name.ljust(width)}  {r.detail}")
    sys.exit(0 if all(r.ok for r in results) else 1)


if __name__ == "__main__":
    main()
