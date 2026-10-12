# AGENTS.md

Kavrynt Labs: a disposable lab for testing the Kavrynt MCP control plane (runtime in
`kavrynt`, hosted control plane in `kavrynt-cloud`) end to end. Plan: [docs/PLAN.md](docs/PLAN.md).

## Branching

- Start from `main`; work on `feature/<short-kebab-case>`; one logical change per branch.
- Merge through a pull request once the lab workflow passes; delete the branch after.
- Commit, push, merge, or create cloud resources only when the owner asks.

## Boundaries

- The lab hosts and exercises features; it does not implement them. Runtime features
  (connector, Gateway auth, policy) belong in `kavrynt`; Cloud features in `kavrynt-cloud`;
  Azure foundations (resource group, identities, budgets) in `kavrynt-platform`'s landing zone.
- `policies/expectations.yaml` describes the governance we intend. Change it deliberately:
  it drives the dashboard and, later, the scenario acceptance suite.

## Rules

- Everything must be deletable in one command: `make lab-down` locally, the Azure Lab workflow's
  `down` operation (or its TTL reaper) on Azure.
- Azure changes only through the Azure Lab workflow on `main` (plan -> approval -> apply for `up`).
  Never run `terraform apply` for `infra/azure` from a laptop; `terraform plan` is read-only and
  allowed. Foundations (resource group, identity, roles, state, budget) change only in
  `kavrynt-platform/landing-zone/lab.tf`.
- Nothing in the lab is exposed publicly: ClusterIP services only (Kind adds `kind/nodeports.yaml`
  on 127.0.0.1); on AKS use `kubectl port-forward`.
- No secrets, kubeconfigs, tokens or customer data in the repository. Lab data is synthetic.
- Pin images by digest and chart versions by digest (`scripts/lab.sh`, manifests, `lab/Dockerfile`),
  GitHub Actions by commit SHA, Terraform providers in `.terraform.lock.hcl` for linux_amd64,
  darwin_arm64, darwin_amd64 and windows_amd64.
- Trivy findings are fixed, or accepted with a reason in `.trivyignore.yaml`.
- Scripts are committed executable: `git add --chmod=+x scripts/*.sh scripts/*.py .github/actions/approval/*.sh`
  (this repository has `core.filemode=false` on Windows).
- Record anything the lab reveals about the runtime or Cloud in `docs/FINDINGS.md`.

## Validation

```bash
make test          # ruff and unit tests for the lab servers and agents
make validate      # manifests render, scripts parse
make tf-check      # terraform fmt + validate for infra/azure
make lab-up        # Kind cluster + runtime + servers + agents + monitoring
make lab-check     # in-cluster checks
make lab-down
```

Procedures: `docs/runbooks/`.
