"""kavrynt-lab server | agent | check"""

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

        results = asyncio.run(run_checks(args.gateway, args.prometheus, args.metrics_timeout))
        width = max(len(r.name) for r in results)
        for r in results:
            print(f"{'PASS' if r.ok else 'FAIL'}  {r.name.ljust(width)}  {r.detail}")
        sys.exit(0 if all(r.ok for r in results) else 1)


if __name__ == "__main__":
    main()
