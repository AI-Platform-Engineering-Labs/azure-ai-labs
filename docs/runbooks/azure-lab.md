# Runbook: the Azure lab, on demand

The same lab as on Kind, on a one-node AKS cluster in `rg-kavrynt-lab`. It exists only while
you need it: you create it with the **Azure Lab** workflow, and it is destroyed by the same
workflow (operation **down**) or by the TTL reaper when its time is up.

Prerequisite: [azure-setup.md](azure-setup.md) is done (the workflow's Azure jobs are skipped
until the repository variables exist).

## What it costs

About **USD 0.20 an hour** while up (one `Standard_D2ds_v6` node, its disk, the load
balancer for outbound traffic, a Basic registry; the AKS Free tier control plane is free),
so roughly USD 1.60 for an 8-hour session at pay-as-you-go list prices. When it is down,
only the landing-zone foundations remain, at about zero. A monthly budget on
`rg-kavrynt-lab` emails the subscription Owners at 50% spent and at 100% forecast.

## Create it

**Actions → Azure Lab → Run workflow**, branch `main`, operation **up**, and a TTL. Or:

```bash
gh workflow run lab-azure.yml --repo kavrynt/kavrynt-labs --ref main -f operation=up -f ttl_hours=8
```

1. **Plan** shows what will change.
2. **Approval** opens an issue with the plan. An approver (variable `LAB_APPROVERS`, default
   you) comments `approve`. Nothing is created before that; with no decision within an hour
   the run stops.
3. **Apply and deploy** (about 10–15 minutes on a fresh create) applies the approved plan,
   builds and pushes the lab image, installs Kavrynt, Prometheus, Grafana, the MCP servers
   and agents, and runs the same end-to-end checks as `make lab-check`.

The run summary shows when the lab expires and how to connect.

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

From a kavrynt-labs checkout, `TARGET=aks KUBE_CONTEXT=aks-kavrynt-lab bash scripts/lab.sh status`
and `... check` work too.

## Extend it, or deploy a change

Run the workflow again with operation **up** and a new TTL. The plan changes the
`kavrynt-lab-expires-at` tag (and anything else that changed on `main`), and the deploy step
rolls out the lab image built from the run's commit. To try unmerged code, merge it first:
the workflow trusts `main` only.

## Destroy it

**Actions → Azure Lab → Run workflow**, operation **down**. Or:

```bash
gh workflow run lab-azure.yml --repo kavrynt/kavrynt-labs --ref main -f operation=down
```

No approval is needed: removing the lab is always safe. The run destroys the cluster and the
registry, then fails loudly if anything is still in `rg-kavrynt-lab` or its node resource
group (see *Leftovers*).

## The TTL reaper

Every two hours (cron `41 */2 * * *`) the workflow checks `rg-kavrynt-lab`. If there are
resources and no cluster whose `kavrynt-lab-expires-at` tag is still in the future, it runs
the same destroy as operation **down**, without approval. So a lab lives at most its TTL
plus two hours. Each check uses about one Actions minute. To see what it decided, open the
latest scheduled run of **Azure Lab**: the summary says *No lab is running*, *within its TTL*,
or *expired: destroying it*.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Azure jobs are skipped | Repository variables are missing: [azure-setup.md](azure-setup.md), step 4. |
| `AADSTS700213` / no matching federated identity | The run is not on `main` (or a pull request), or the OIDC subject prefix changed: compare with step 4 of the setup. |
| Approval issue timed out | Nothing was created. Run the workflow again. |
| `Saved plan is stale` | Another run changed the state between plan and apply. Run the workflow again. |
| `state blob is already locked` | A run was interrupted. Confirm no run is active, then an Owner breaks the lease: `az storage blob lease break --account-name stkavryntstate01 --container-name tfstate-lab --blob-name lab.tfstate --auth-mode login`. |
| `OperationNotAllowed` / quota on create | vCPU quota: [azure-setup.md](azure-setup.md), step 2. Run **down**, fix the quota, run **up**. |
| Image push fails (401) | The AcrPush role is still propagating; the step retries for 4 minutes. If it still fails, run **up** again. |
| `Forbidden` from kubectl | Azure RBAC for the cluster takes a few minutes after create; for people, check membership of `kavrynt-platform-admins` and run `kubelogin convert-kubeconfig -l azurecli` again. |
| Pods in `ImagePullBackOff` | AcrPull for the kubelet is still propagating; pods retry by themselves. The deploy waits up to 10 minutes per deployment. |
| Deploy or checks failed | The cluster stays up for debugging (see the run's Diagnostics step and *Connect to it*). Fix, then run **up** again, or run **down**. |

### Leftovers

If **down** reports resources left behind:

```bash
az resource list --resource-group rg-kavrynt-lab -o table
az group list --query "[?starts_with(name, 'MC_rg-kavrynt-lab_')].name" -o tsv
```

Run **down** once more first (a deletion may still have been in progress). If something
remains that Terraform no longer tracks, an Owner deletes it in the portal or with
`az resource delete --ids <id>`. Never delete `rg-kavrynt-lab` itself: the landing zone owns
it, its budget and the identity's roles.
