---
name: azure-lab
description: Create, check, connect to, or destroy the on-demand Kavrynt lab on AKS through the Azure Lab GitHub workflow (up with a TTL, down, plan-only), then confirm cost is back to about zero. Use when asked to run the lab in Azure.
argument-hint: "<up [ttl hours 2|4|8|12|24] | down | status | plan-only>"
disable-model-invocation: true
---

# Run the lab in Azure

Operation: `$ARGUMENTS`. Daily use: `docs/runbooks/azure-lab.md`. One-time setup:
`docs/runbooks/azure-setup.md`.

Rules: Azure changes only through the **Azure Lab** workflow on `main`. Never run
`terraform apply` for `infra/azure` from a laptop. Never comment `approve` on the approval
issue: an approver in `LAB_APPROVERS` does. About USD 0.20 an hour while up.

## Preconditions

```bash
gh variable list -R kavrynt/kavrynt-labs      # AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID
```

If they are missing, the Azure jobs are skipped: the landing zone (`kavrynt-platform`
`landing-zone/lab.tf`) must be applied and the variables set first (azure-setup.md).

## up **[ask]**

TTL is 2, 4, 8 (default), 12, or 24 hours.

```bash
gh workflow run lab-azure.yml --repo kavrynt/kavrynt-labs --ref main -f operation=up -f ttl_hours=8
sleep 5
RUN=$(gh run list -R kavrynt/kavrynt-labs --workflow lab-azure.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view "$RUN" -R kavrynt/kavrynt-labs
```

The run plans, then opens an approval issue: give the owner the link. After approval it
applies, deploys the lab, and runs the same checks as Kind. Watch with
`gh run watch "$RUN" -R kavrynt/kavrynt-labs --exit-status`.

## Connect (status)

You must be in `kavrynt-platform-admins`.

```bash
az aks get-credentials --resource-group rg-kavrynt-lab --name aks-kavrynt-lab
kubelogin convert-kubeconfig -l azurecli
kubectl --context aks-kavrynt-lab get pods -A
kubectl --context aks-kavrynt-lab -n lab-monitoring port-forward svc/grafana 3000:3000
kubectl --context aks-kavrynt-lab -n kavrynt-system port-forward svc/kavrynt-gateway 18080:8080
```

Dashboard: http://localhost:3000/d/kavrynt-governance.

Nothing is public; always port-forward. Expiry is the `kavrynt-lab-expires-at` tag:
`az group show -n rg-kavrynt-lab --query tags`.

## down **[ask]**

```bash
gh workflow run lab-azure.yml --repo kavrynt/kavrynt-labs --ref main -f operation=down
```

No approval is needed: removing the lab is always safe. The run ends with a check that
nothing is left. The resource group, budget, state container, and identity stay (about zero
cost). The TTL reaper destroys an expired lab at most two hours late.

## After

Confirm `az resource list -g rg-kavrynt-lab -o table` is empty after `down`. Report the
operation, run link, check results, and when the lab expires (for `up`).
