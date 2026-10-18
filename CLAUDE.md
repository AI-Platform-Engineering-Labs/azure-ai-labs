# CLAUDE.md

Kavrynt Labs (`AI-Platform-Engineering-Labs/azure-ai-labs`, formerly
`kavrynt/kavrynt-labs`): a disposable lab for testing the Kavrynt MCP control
plane (runtime in `kavrynt`, hosted control plane in `kavrynt-cloud`) end to
end. Two teams' MCP servers sit behind the Kavrynt Gateway; three scripted
agents, one of them rogue, call their tools continuously; Grafana shows what
each agent did against what policy says it should have been allowed to do.
Private repository. Plan and phases: [docs/PLAN.md](docs/PLAN.md).

## Status

| Phase | Status |
| --- | --- |
| 1. Local lab on Kind | done |
| 2. Azure lab on AKS (on demand) | built: three workflows (landing zone, cluster with Cilium, integrations); the first Azure run waits for kavrynt-platform's Landing Zone apply |
| 3. Visibility: runtime connector syncs to Kavrynt Cloud | planned (connector is built in `kavrynt`) |
| 4. Enforcement: Gateway OAuth, OPA policies, approvals, scenario suite | planned |

What the lab has revealed lives in [docs/FINDINGS.md](docs/FINDINGS.md) (F1–F10;
the fixes are owned by `kavrynt`). With today's runtime the "ungoverned" count
grows by design: nothing authenticates or authorizes calls yet.

## Layout

```text
lab/                    Python package kavrynt_lab: one image, three roles
  src/kavrynt_lab/      server.py, agent.py, check.py, catalog.py, expectations.py, metrics.py, cli.py
  tests/                pytest (test_servers.py, test_agents.py)
  Dockerfile, pyproject.toml, constraints.txt
cluster/workloads/      namespaces, MCP servers, agents, NetworkPolicies, check Job (kustomize)
cluster/integrations/   AKS only: workload identity service account, Key Vault SecretProviderClass, check Job
cluster/monitoring/     Prometheus, Grafana, governance dashboard (kustomize)
policies/expectations.yaml   intended governance: deny by default, who may call what, what needs approval
kind/                   Kind cluster and 127.0.0.1 NodePorts
infra/azure/            Azure lab stacks (AVM), each with its own state key, applied in this order:
  landing-zone/         1. VNet, AKS subnet + NSG, static egress IP, AKS control-plane identity (kept)
  cluster/              2. one-node AKS (Free tier, Entra ID + Azure RBAC, Cilium), Basic registry (on demand)
  integrations/         3. Key Vault, lab workload identity federated with the running cluster (kept)
scripts/lab.sh          up / check / integrations / status / reload / runtime-reload / down / clean
scripts/fetch_chart.py  pulls the pinned runtime chart
.github/workflows/      lab.yml (CI on Kind), lab-landing-zone.yml, lab-azure.yml (Azure Lab), lab-integrations.yml
.github/actions/        approval/ (issue-comment approval, as kavrynt-platform), terraform-plan/, require-stack/
docs/runbooks/          local-lab.md, azure-setup.md, azure-lab.md
```

In-cluster namespaces: `kavrynt-system` (Gateway and Operator, Helm release
`kavrynt`), `team-payments` (`payments-mcp`), `team-support` (`support-mcp`),
`lab-agents` (`support-agent`, `payments-agent`, `rogue-agent`, `lab-check`
Job), `lab-monitoring`. Each server registers through an `MCPServer`, routed at
`/mcp/<namespace>.<name>`. Tools carry MCP annotations (`readOnlyHint`,
`destructiveHint`) and Kavrynt risk metadata in `_meta`. Agents send
`X-Lab-Agent` (self-asserted) and score each call against the expectations.
NetworkPolicies let only `kavrynt-system` (and Prometheus) reach the team
namespaces; the rogue agent's direct calls are scored as server
`direct:<namespace>.<name>` and must end in `timeout` or `unreachable`.

## Commands

```bash
make venv            # lab/.venv with the lab package and dev tools
make test            # ruff check + ruff format --check + pytest
make validate        # kustomize renders, bash -n on scripts
make tf-check        # terraform fmt + validate for the three infra/azure stacks (no Azure access)
make lab-up          # Kind + runtime + monitoring + servers + agents
make lab-check       # in-cluster end-to-end checks
make lab-status      # pods, MCPServers, routes, URLs
make lab-reload      # rebuild the lab image, re-apply manifests and expectations
make runtime-reload  # reinstall Kavrynt (rebuilds images with RUNTIME=source)
make lab-down        # delete the Kind cluster
make clean           # lab-down, remove lab images and .cache
```

Options for `scripts/lab.sh` and the Make targets:

- `RUNTIME=release` (default): the public Docker Hub chart and images, pinned by
  digest in `scripts/lab.sh`.
- `RUNTIME=source`: builds the runtime from `KAVRYNT_SRC` (default
  `../kavrynt`), Kind only. Change runtime Go code, then `make runtime-reload`.
- `DOCKERHUB_MIRROR=mirror.gcr.io` when Docker Hub pulls fail (401, 429, a
  stale `docker login`).
- `TARGET=aks` runs the same manifests and checks on the Azure lab;
  `scripts/lab.sh integrations` (AKS only) is what Lab Integrations runs.

Local URLs (all on `127.0.0.1`): Grafana `http://localhost:3000/d/kavrynt-governance`,
Prometheus `:9090`, Gateway `:18080/v1/routes`.

Needs Docker (4 GB+), kind, kubectl, Helm 3, Python 3.12+, Bash 4.4+,
Terraform 1.12+ for `tf-check`.

## CI And The Azure Lab

- `lab.yml` (pull requests and pushes to `main`, manual): lint, unit tests,
  manifests, Terraform, Trivy, then the whole lab on Kind with the pinned
  released runtime. No Azure access.
- Azure, three workflows in dependency order (docs/runbooks/azure-lab.md). Each
  refuses to plan until its upstream stack is applied (`require-stack`), and all
  share one concurrency queue on `main`:
  1. `lab-landing-zone.yml` (Lab Landing Zone), manual: `apply` / `plan-only` /
     `destroy` (confirm, cluster must be down). Every change needs approval.
  2. `lab-azure.yml` (Azure Lab), manual: `up` with a TTL of 2–24 h (plan →
     approval → apply → deploy → checks), `down` (destroy, no approval, then a
     check that no cluster or registry is left), `plan-only`. A TTL reaper runs
     every 2 h and destroys a cluster whose `kavrynt-lab-expires-at` has passed.
  3. `lab-integrations.yml` (Lab Integrations): runs after every manual Azure
     Lab run, or manually (`apply` / `plan-only` / `destroy`). Re-pointing the
     federated credential at the current cluster needs no approval; anything
     else does. Then wires the cluster and checks Key Vault and Cloud dev.
  - Pull requests touching a stack get a read-only plan of that stack.
- Approvers: `LAB_APPROVERS` repository variable (default: whoever started the
  run), who comment exactly `approve` or `deny`. Azure jobs are skipped until
  `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and `AZURE_SUBSCRIPTION_ID` are set
  (docs/runbooks/azure-setup.md).
- Cost: about USD 0.20 an hour while the cluster is up; about USD 4 a month
  between labs (the static egress IP).

## Branching

- Trunk-based: start from `main`; work on `feature/<short-kebab-case>`; one
  logical change per branch.
- Merge through a pull request once the Lab workflow passes; delete the branch
  after.
- Commit, push, merge, or create cloud resources only when the owner asks.
- Never comment `approve` or `deny` on an approval issue; the owner does that.

## Boundaries

- The lab hosts and exercises features; it does not implement them. Runtime
  features (connector, Gateway auth, policy) belong in `kavrynt`; Cloud features
  in `kavrynt-cloud`; Azure foundations (resource group `rg-kavrynt-lab`,
  identity `id-kavrynt-github-lab`, the roles it may grant, state, budget) in
  `kavrynt-platform/landing-zone/lab.tf`. Everything inside the resource group
  (network, cluster, Key Vault) is this repository's `infra/azure`.
- The Kavrynt Cloud dev firewall is kavrynt-platform's
  `DEV_ALLOWED_INGRESS_CIDRS`; it must include the lab landing zone's egress IP.
- `policies/expectations.yaml` describes the governance we intend. Change it
  deliberately: it drives the dashboard and, later, the scenario acceptance
  suite.
- The `kavrynt` runtime is source-available under the Elastic License 2.0;
  never call it open source.

## Rules

- Everything must be deletable: `make lab-down` locally. On Azure, the Azure
  Lab `down` operation (or its TTL reaper) removes everything that costs money
  by the hour; Lab Integrations and Lab Landing Zone `destroy` remove the rest.
- Azure changes only through the lab workflows on `main`. Never run
  `terraform apply` for `infra/azure` from a laptop; `terraform plan` is
  read-only and allowed.
- Nothing in the lab is exposed publicly: ClusterIP services only (Kind adds
  `kind/nodeports.yaml` on 127.0.0.1); on AKS use `kubectl port-forward`.
- No secrets, kubeconfigs, tokens, or customer data in the repository. Lab data
  is synthetic. Lab secrets live in the lab Key Vault and reach pods through
  workload identity and the CSI driver, never as Kubernetes Secrets in Git.
- Pin images and charts by digest (`scripts/lab.sh`, manifests,
  `lab/Dockerfile`), GitHub Actions by commit SHA, Python dependencies in
  `lab/constraints.txt`, and Terraform providers in `.terraform.lock.hcl` for
  linux_amd64, darwin_arm64, darwin_amd64, and windows_amd64.
- Trivy findings are fixed, or accepted with a reason in `.trivyignore.yaml`.
- Scripts are committed executable:
  `git add --chmod=+x scripts/*.sh scripts/*.py .github/actions/approval/*.sh`
  (the repository has `core.filemode=false` on Windows).
- Record anything the lab reveals about the runtime or Cloud in
  `docs/FINDINGS.md`, naming the owning repository.

## Validation Before A Pull Request

```bash
make test && make validate && make tf-check
make lab-up && make lab-check && make lab-down
```
