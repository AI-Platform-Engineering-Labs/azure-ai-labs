# Runbook: the lab on Kind

Everything runs in one Kind cluster on your machine and binds to `127.0.0.1` only.

## Before you start

- Docker with at least 4 GB of memory, [kind](https://kind.sigs.k8s.io/) 0.31+, kubectl,
  Helm 3 and Python 3.12+.
- Bash 4.4 or newer: Git Bash on Windows and Linux are fine; on macOS install it with
  Homebrew.
- Ports 3000, 9090 and 18080 free on localhost.

## Bring the lab up

```bash
make lab-up       # creates the cluster on first run; about 2 minutes
make lab-check    # in-cluster end-to-end checks; all lines must say PASS
```

| What | Where |
|---|---|
| Governance dashboard | http://localhost:3000/d/kavrynt-governance |
| Prometheus | http://localhost:9090 |
| Kavrynt Gateway | http://localhost:18080/v1/routes |

`make lab-up` is safe to run again: it reuses the cluster and only rolls pods whose image
changed. The lab image tag is derived from its content (`kavrynt-lab:<id>`).

## Change something

| Change | Then run |
|---|---|
| `policies/expectations.yaml` | `make lab-reload` (the agents restart with the new file) |
| Code in `lab/` or manifests in `cluster/` | `make lab-reload` |
| Kavrynt runtime code in `../kavrynt` | `RUNTIME=source make runtime-reload` (first time: `RUNTIME=source make lab-up`) |
| Back to the released runtime | `make runtime-reload` |

The released runtime is pinned in `scripts/lab.sh` (chart and image digests). To move to a
new release, update the version and the three digests together, in a pull request.

## Check what is going on

```bash
make lab-status                                   # pods, MCPServers, routes
kubectl --context kind-kavrynt-lab -n lab-agents logs deploy/rogue-agent --tail 20
kubectl --context kind-kavrynt-lab -n kavrynt-system logs deploy/kavrynt-gateway --tail 50
```

Each agent logs one JSON line per call: the expected decision, the outcome and the HTTP
status of the `tools/call` request.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `401 Unauthorized` or `429` while pulling from Docker Hub | A stale `docker login` or the anonymous rate limit. Run with `DOCKERHUB_MIRROR=mirror.gcr.io`, or `docker logout`. |
| `kind create cluster` fails on ports | Something else uses 3000, 9090 or 18080. Stop it, then `make lab-up`. |
| A deployment is not ready | `kubectl --context kind-kavrynt-lab -n <ns> describe deployment <name>` and the pod events. |
| `lab-check` fails on metrics | Prometheus needs a few scrapes after a fresh start. Run `make lab-check` again after a minute. |
| `lab-check` fails *direct call around the gateway is blocked* | The cluster does not enforce NetworkPolicy. kindnet in kind 0.31 does (verified); with an older kind, upgrade and recreate the cluster (`make lab-down && make lab-up`). Check `kubectl --context kind-kavrynt-lab get networkpolicies -A`. |
| Dashboard panels are empty | Same as above; also check http://localhost:9090/targets (all targets should be up). |

## Delete it

```bash
make lab-down     # deletes the Kind cluster and everything in it
make clean        # also removes the lab images from Docker and the .cache folder
```
