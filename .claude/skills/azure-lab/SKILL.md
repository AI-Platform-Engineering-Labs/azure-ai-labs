---
name: azure-lab
description: Create, check, connect to, or destroy the on-demand Kavrynt lab on AKS through the lab GitHub workflows (Lab Landing Zone, then Azure Lab up with a TTL / down / plan-only, then Lab Integrations), then confirm the cluster is gone after down. Use when asked to run the lab in Azure.
argument-hint: "<up [ttl hours 2|4|8|12|24] | down | status | plan-only>"
disable-model-invocation: true
---

# Run the lab in Azure

Operation: `$ARGUMENTS`. Daily use: `docs/runbooks/azure-lab.md`. One-time setup:
`docs/runbooks/azure-setup.md`.

Rules: Azure changes only through the lab workflows on `main` (Lab Landing Zone → Azure Lab
→ Lab Integrations). Never run `terraform apply` for `infra/azure` from a laptop. Never
comment `approve` on an approval issue: an approver in `LAB_APPROVERS` does. About USD 0.20
an hour while the cluster is up, about USD 4 a month between labs.

## Preconditions

```bash
gh variable list -R AI-Platform-Engineering-Labs/azure-ai-labs      # AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID
```

If they are missing, the Azure jobs are skipped: kavrynt-platform's landing zone
(`landing-zone/lab.tf`) must be applied and the variables set first (azure-setup.md).

The lab landing zone must be applied once (Azure Lab refuses to plan without it):

```bash
gh run list -R AI-Platform-Engineering-Labs/azure-ai-labs --workflow lab-landing-zone.yml --status success --limit 1
# none? **[ask]** then:
gh workflow run lab-landing-zone.yml --repo AI-Platform-Engineering-Labs/azure-ai-labs --ref main -f operation=apply
```

## up **[ask]**

TTL is 2, 4, 8 (default), 12, or 24 hours.

```bash
gh workflow run lab-azure.yml --repo AI-Platform-Engineering-Labs/azure-ai-labs --ref main -f operation=up -f ttl_hours=8
sleep 5
RUN=$(gh run list -R AI-Platform-Engineering-Labs/azure-ai-labs --workflow lab-azure.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view "$RUN" -R AI-Platform-Engineering-Labs/azure-ai-labs
```

The run plans, then opens an approval issue: give the owner the link. After approval it
applies, deploys the lab, and runs the same checks as Kind. Watch with
`gh run watch "$RUN" -R AI-Platform-Engineering-Labs/azure-ai-labs --exit-status`.

Then **Lab Integrations** starts by itself (Key Vault, workload identity, Cloud dev check):
`gh run list -R AI-Platform-Engineering-Labs/azure-ai-labs --workflow lab-integrations.yml --limit 1`.
It asks for approval only when more than the federated credential changes. A 403 from Cloud
dev means its firewall lacks the lab's egress IP (azure-setup.md, step 6).

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

Nothing is public; always port-forward. Expiry is the cluster's `kavrynt-lab-expires-at` tag:
`az aks show -g rg-kavrynt-lab -n aks-kavrynt-lab --query tags`.

## down **[ask]**

```bash
gh workflow run lab-azure.yml --repo AI-Platform-Engineering-Labs/azure-ai-labs --ref main -f operation=down
```

No approval is needed: removing the cluster is always safe. The run ends with a check that
no cluster or registry is left; Lab Integrations follows and removes the federation. The lab
landing zone and Key Vault stay (about USD 4 a month), as do kavrynt-platform's resource
group, budget, state container and identity. The TTL reaper destroys an expired cluster at
most two hours late.

## After

After `down`, confirm `az aks list -g rg-kavrynt-lab -o table` and `az acr list -g rg-kavrynt-lab -o table`
are empty. Report the operation, run links (Azure Lab and Lab Integrations), check results,
and when the lab expires (for `up`).
