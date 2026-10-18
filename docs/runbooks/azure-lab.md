# Runbook: the Azure lab, on demand

The same lab as on Kind, on a one-node AKS cluster in `rg-kavrynt-lab`. The cluster exists
only while you need it: you create it with the **Azure Lab** workflow, and it is destroyed by
the same workflow (operation **down**) or by the TTL reaper when its time is up. What it is
built on, and what connects it to the platform, stays between labs.

Prerequisite: [azure-setup.md](azure-setup.md) is done (the workflows' Azure jobs are skipped
until the repository variables exist).

## Order of the workflows

Each workflow refuses to run until the one before it is applied, and says which one to run.

| # | Workflow | Stack | What | Lifetime |
|---|---|---|---|---|
| 0 | kavrynt-platform **Landing Zone** | `landing-zone/lab.tf` | resource group, budget, state, workflow identity | permanent |
| 1 | **Lab Landing Zone** | `infra/azure/landing-zone` | VNet `10.41.0.0/16`, AKS subnet + NSG, static egress IP, AKS control-plane identity | kept; destroy needs the cluster down |
| 2 | **Azure Lab** | `infra/azure/cluster` | AKS (Azure CNI Overlay + Cilium, NetworkPolicy, workload identity, Key Vault CSI driver), registry, the lab | on demand, TTL 2–24 h |
| 3 | **Lab Integrations** | `infra/azure/integrations`, `cluster/integrations` | Key Vault, workload identity federated with the running cluster; checks Key Vault and Kavrynt Cloud dev from inside the cluster | vault kept; federation follows the cluster |

Lab Integrations runs by itself after every manual Azure Lab run on `main`: after **up** it
federates and checks the new cluster, after **down** it removes the federation. All lab
workflows share one queue on `main`, so they never change stacks under each other.

## What it costs

About **USD 0.20 an hour** while the cluster is up (one `Standard_D2ds_v6` node, its disk,
the load balancer, a Basic registry; the AKS Free tier control plane is free), so roughly
USD 1.60 for an 8-hour session at pay-as-you-go list prices. Between labs, about **USD 4 a
month**: the static egress IP (Key Vault, VNet, NSG and identities cost nothing at rest). A
monthly budget on `rg-kavrynt-lab` emails the subscription Owners at 50% spent and at 100%
forecast.

## Create it

**Actions → Azure Lab → Run workflow**, branch `main`, operation **up**, and a TTL. Or:

```bash
gh workflow run lab-azure.yml --repo AI-Platform-Engineering-Labs/azure-ai-labs --ref main -f operation=up -f ttl_hours=8
```

1. **Plan** checks that the lab landing zone is applied, then shows what will change.
2. **Approval** opens an issue with the plan. An approver (variable `LAB_APPROVERS`, default
   you) comments `approve`. Nothing is created before that; with no decision within an hour
   the run stops. The TTL counts from the plan.
3. **Apply and deploy** (about 10–15 minutes on a fresh create) applies the approved plan,
   builds and pushes the lab image, installs Kavrynt, Prometheus, Grafana, the MCP servers,
   agents and NetworkPolicies, and runs the same end-to-end checks as `make lab-check`
   (including: a direct call to an MCP server, around the Gateway, is blocked).
4. **Lab Integrations** then runs: it federates the lab workload identity with the new
   cluster without approval, applies the service account and Key Vault wiring, and checks
   that the Key Vault canary mounts and that Kavrynt Cloud dev answers. It asks for approval
   only when anything else changes (for example the first time, when it creates the vault).

The run summaries show when the lab expires, how to connect, and the integration results.

## Connect to it

Nothing in the lab is exposed to the internet. You reach it through the Kubernetes API with
your Entra account (you must be in `kavrynt-platform-admins`):

```bash
az login
az aks get-credentials --resource-group rg-kavrynt-lab --name aks-kavrynt-lab
kubelogin convert-kubeconfig -l azurecli
kubectl --context aks-kavrynt-lab -n lab-monitoring port-forward svc/grafana 3000:3000
```

Open http://localhost:3000/d/kavrynt-governance. For the Gateway (any MCP client):

```bash
kubectl --context aks-kavrynt-lab -n kavrynt-system port-forward svc/kavrynt-gateway 18080:8080
```

From an azure-ai-labs checkout, `TARGET=aks KUBE_CONTEXT=aks-kavrynt-lab bash scripts/lab.sh status`
and `... check` work too.

## Use the secret store

Lab pods read secrets from the lab Key Vault (`kv-kavrynt-lab-<suffix>`, in the Lab
Integrations summary) with workload identity; no secret is stored in the cluster or in this
repository.

1. A member of `kavrynt-platform-admins` adds the secret:
   `az keyvault secret set --vault-name <vault> --name <name> --value <value>`.
2. Add it under `objects` in `cluster/integrations/workload.yaml` (SecretProviderClass
   `lab-key-vault`) through a pull request.
3. The pod runs as service account `lab-agents/lab-workload` and mounts the
   `secrets-store.csi.k8s.io` volume with `secretProviderClass: lab-key-vault`, like
   `cluster/integrations/check-job.yaml`.

## Extend it, or deploy a change

Run Azure Lab again with operation **up** and a new TTL. The plan changes the
`kavrynt-lab-expires-at` tag (and anything else that changed on `main`), and the deploy step
rolls out the lab image built from the run's commit. To try unmerged code, merge it first:
the workflows trust `main` only. To re-run only the integration checks (for example after
the Cloud dev firewall changed), run **Lab Integrations** with operation **apply**.

## Destroy it

**Actions → Azure Lab → Run workflow**, operation **down**. Or:

```bash
gh workflow run lab-azure.yml --repo AI-Platform-Engineering-Labs/azure-ai-labs --ref main -f operation=down
```

No approval is needed: removing the cluster is always safe. The run destroys the cluster and
the registry, then fails loudly if a cluster, registry or AKS node resource group is left (see
*Leftovers*). Lab Integrations follows and removes the workload identity's federation. The
lab landing zone and the Key Vault stay, at about USD 4 a month.

To remove everything (rarely): Azure Lab **down**, then Lab Integrations **destroy** (confirm
`destroy lab integrations`; the vault is soft-deleted for 7 days and cannot be purged), then
Lab Landing Zone **destroy** (confirm `destroy lab landing zone`; refused while a cluster
runs). Both need an approval.

## The TTL reaper

Every two hours (cron `41 */2 * * *`) Azure Lab checks `rg-kavrynt-lab`. If a cluster or
registry exists and no cluster's `kavrynt-lab-expires-at` tag is still in the future, it runs
the same destroy as operation **down**, without approval. So a lab lives at most its TTL plus
two hours. Each check uses about one Actions minute. To see what it decided, open the latest
scheduled run of **Azure Lab**: the summary says *No lab cluster is running*, *within its
TTL*, or *expired: destroying it*. A reaped cluster leaves the workload identity federated
with an issuer that no longer exists, which trusts nothing; the next Lab Integrations run
removes it.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Azure jobs are skipped | Repository variables are missing: [azure-setup.md](azure-setup.md), step 4. |
| `AADSTS700213` / no matching federated identity | The run is not on `main` (or a pull request), or the OIDC subject changed (repository renamed or moved): compare with step 4 of the setup. |
| *Blocked: infra/azure/landing-zone is not applied* | Run **Lab Landing Zone** (apply) first. |
| *Blocked: infra/azure/cluster is not applied* (Lab Integrations) | Run **Azure Lab** with operation **up** first. |
| Approval issue timed out | Nothing was created. Run the workflow again. |
| `Saved plan is stale` | Another run changed the state between plan and apply. Run the workflow again. |
| `state blob is already locked` | A run was interrupted. Confirm no run is active, then an Owner breaks the lease: `az storage blob lease break --account-name stkavryntstate01 --container-name tfstate-lab --blob-name <stack>.tfstate --auth-mode login` (`landing-zone`, `lab` or `integrations`). |
| `OperationNotAllowed` / quota on create | vCPU quota: [azure-setup.md](azure-setup.md), step 2. Run **down**, fix the quota, run **up**. |
| AKS create fails on the subnet or egress IP (`LinkedAuthorizationFailed`) | The control-plane identity's Network Contributor role is still propagating, or the lab landing zone was not applied. Run **up** again. |
| Image push fails (401) | The AcrPush role is still propagating; the step retries for 4 minutes. If it still fails, run **up** again. |
| `Forbidden` from kubectl | Azure RBAC for the cluster takes a few minutes after create; for people, check membership of `kavrynt-platform-admins` and run `kubelogin convert-kubeconfig -l azurecli` again. |
| Pods in `ImagePullBackOff` | AcrPull for the kubelet is still propagating; pods retry by themselves. The deploy waits up to 10 minutes per deployment. |
| Check *direct call around the gateway is blocked* fails | NetworkPolicy is not enforced: the cluster was created without Cilium, or `cluster/workloads/network-policies.yaml` was not applied (`kubectl get networkpolicies -A`). |
| *key vault secret mounted* fails, Job pod stuck in `ContainerCreating` | `kubectl -n lab-agents describe pod -l job-name=lab-integrations-check`: a `FailedMount` usually means the federated credential or the Key Vault Secrets User role is still propagating. Run **Lab Integrations** again after a few minutes. |
| *kavrynt cloud dev reachable* fails with 403 | The Cloud dev firewall does not allow the egress IP yet: [azure-setup.md](azure-setup.md), step 6, then run **Lab Integrations** again. |
| Deploy or checks failed | The cluster stays up for debugging (see the run's Diagnostics step and *Connect to it*). Fix, then run **up** again, or run **down**. |

### Leftovers

If **down** reports resources left behind:

```bash
az resource list --resource-group rg-kavrynt-lab -o table
az group list --query "[?starts_with(name, 'MC_rg-kavrynt-lab_')].name" -o tsv
```

The VNet, NSG, public IP, Key Vault and the two `id-kavrynt-lab-*` identities belong to the
lab landing zone and integrations and are meant to stay. Run **down** once more first (a
deletion may still have been in progress). If a cluster or registry remains that Terraform no
longer tracks, an Owner deletes it in the portal or with `az resource delete --ids <id>`.
Never delete `rg-kavrynt-lab` itself: kavrynt-platform's landing zone owns it, its budget and
the identity's roles.
