# azure-ai-labs

Kavrynt Labs (formerly `kavrynt/kavrynt-labs`): a disposable lab for watching the Kavrynt MCP control plane govern real MCP traffic. Two
teams' MCP servers sit behind the Kavrynt Gateway; three scripted agents (one of them rogue)
call their tools all the time; Grafana shows what each agent did against what policy says it
should have been allowed to do.

It runs on your laptop (Kind) or on demand in Azure (AKS), with the same manifests and
checks. The plan, phases and decisions are in [docs/PLAN.md](docs/PLAN.md); operating
procedures in [docs/runbooks/](docs/runbooks/README.md); what the lab has revealed about the
runtime in [docs/FINDINGS.md](docs/FINDINGS.md).

## Run it locally

Needs Docker (4 GB+), [kind](https://kind.sigs.k8s.io/), kubectl, Helm 3, Python 3.12+ and
Bash 4.4+.

```bash
make lab-up       # Kind cluster, Kavrynt runtime, Prometheus + Grafana, servers and agents
make lab-check    # end-to-end checks from inside the cluster
make lab-down     # delete the cluster (make clean also removes the lab images and .cache)
```

| What | Where |
|---|---|
| Governance dashboard | http://localhost:3000/d/kavrynt-governance |
| Prometheus | http://localhost:9090 |
| Kavrynt Gateway | http://localhost:18080/v1/routes |
| MCP endpoints (any MCP client) | `http://localhost:18080/mcp/team-support.support-mcp`, `.../mcp/team-payments.payments-mcp` |

Everything binds to `127.0.0.1`. If Docker Hub pulls fail on your machine (rate limits, a
stale `docker login`), pull through a mirror: `DOCKERHUB_MIRROR=mirror.gcr.io make lab-up`.
More in [docs/runbooks/local-lab.md](docs/runbooks/local-lab.md), including running the
runtime from a `../kavrynt` checkout (`RUNTIME=source`).

## Run it in Azure, on demand

Three GitHub Actions workflows build the lab in the dev subscription, in dependency order.
Each one refuses to run until the one before it is applied:

| # | Workflow | What it does |
|---|---|---|
| 1 | **Lab Landing Zone** | VNet, AKS subnet and NSG, a static egress IP, the AKS control-plane identity; kept between labs |
| 2 | **Azure Lab** | one-node AKS cluster (Azure CNI Overlay + Cilium, NetworkPolicy, workload identity) and a registry; deploys the same lab and runs the same checks. `up` with a TTL of 2–24 h (plan → approval → apply → deploy → checks), `down` (no approval), and a TTL reaper every 2 h |
| 3 | **Lab Integrations** | after every manual Azure Lab run: Key Vault and a workload identity for the running cluster, then checks from inside the cluster that the Key Vault secret mounts and Kavrynt Cloud dev accepts the lab's egress IP |

kavrynt-platform's landing zone provides what comes before step 1: the resource group, its
budget, the Terraform state container and the workflows' identity.

About USD 0.20 an hour while the cluster is up, about USD 4 a month between labs (the
static egress IP). Nothing is exposed publicly; you connect with `kubectl port-forward`.
One-time setup: [azure-setup.md](docs/runbooks/azure-setup.md); daily use:
[azure-lab.md](docs/runbooks/azure-lab.md).

## What is in the cluster

| Namespace | What |
|---|---|
| `kavrynt-system` | Kavrynt Gateway and Operator (Helm release `kavrynt`, pinned by digest) |
| `team-payments` | `payments-mcp`: `search_payments` (low), `get_customer` (medium), `refund_payment` (high, write), `export_customer_data` (high) |
| `team-support` | `support-mcp`: `search_tickets` (low), `create_ticket`, `close_ticket` (medium, write), `delete_ticket` (high, destructive) |
| `lab-agents` | `support-agent`, `payments-agent`, `rogue-agent`, and the `lab-check` Job |
| `lab-monitoring` | Prometheus and Grafana |

Each server registers through an `MCPServer` resource, so the Gateway routes
`/mcp/<namespace>.<name>` to it. NetworkPolicies let only the Kavrynt runtime (and
Prometheus) reach the team namespaces, so no caller can go around the Gateway; the rogue
agent keeps trying, and those attempts show up as `direct:<namespace>.<name>`. Tools carry MCP annotations (`readOnlyHint`,
`destructiveHint`, ...) and Kavrynt risk metadata in `_meta`. All data is synthetic.

## Reading the dashboard

[`policies/expectations.yaml`](policies/expectations.yaml) is the governance we want:
deny by default, which agent may call which tool, and which calls need approval. The agents
score every call against it, using what the control plane did with the `tools/call` request:

- **Ungoverned** - policy says deny or approve, but the call got through to the tool.
- **Over-blocked** - policy says allow, but the control plane refused.
- **not_found** - the Gateway has no route for that server; today this is the only control
  the runtime enforces.

With the current runtime (no authentication or policy yet) the ungoverned count keeps
growing. That is the gap later phases close; when enforcement lands it should stay at zero.

## Developing the lab

```bash
make venv         # lab/.venv with the lab package and dev tools
make test         # ruff + pytest
make validate     # render the Kubernetes manifests, check the scripts
make tf-check     # terraform fmt + validate for the infra/azure stacks (Terraform 1.12+)
```

The lab package (`lab/`) is one image with three roles: `kavrynt-lab server`, `agent` and
`check`. CI (`.github/workflows/lab.yml`) runs all of the above, a Trivy scan, and the whole
lab on Kind. Repository rules for people and coding agents are in [CLAUDE.md](CLAUDE.md).
