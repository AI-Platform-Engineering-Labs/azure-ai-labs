# Runbook: one-time Azure setup

The Azure lab runs in the Kavrynt dev subscription, in its own resource group. Do these
steps once, in order. Every step after the first two goes through a pipeline.

What you need: Owner on the subscription (steps 1 and 2 only), admin on
`kavrynt/kavrynt-platform` and `AI-Platform-Engineering-Labs/azure-ai-labs`, the Azure CLI,
and membership in the `kavrynt-platform-admins` Entra group (to reach the cluster later).

How the pieces depend on each other:

```text
kavrynt-platform  Landing Zone workflow (landing-zone/lab.tf)
                  rg-kavrynt-lab, budget, state container tfstate-lab,
                  identity id-kavrynt-github-lab and the roles it may grant
        |
azure-ai-labs     1. Lab Landing Zone   VNet, subnet, NSG, static egress IP, AKS identity (kept)
                  2. Azure Lab          AKS (Cilium, NetworkPolicy) + registry, on demand, TTL
                  3. Lab Integrations   Key Vault + workload identity, Cloud dev reachability
```

## 1. Register the resource providers (Owner)

Plans never change the subscription (`resource_provider_registrations = "none"`), so
register what the lab uses once:

```bash
az account set --subscription b19634ad-4c1d-422b-a9f1-b877ad42e36b
namespaces="Microsoft.ContainerService Microsoft.ContainerRegistry Microsoft.Consumption Microsoft.Network Microsoft.KeyVault Microsoft.ManagedIdentity"
for ns in $namespaces; do az provider register --namespace "$ns"; done
for ns in $namespaces; do echo "$ns $(az provider show -n "$ns" --query registrationState -o tsv)"; done
```

Wait until all of them say `Registered` (Kavrynt Cloud dev already uses the last three).

## 2. Check the vCPU quota

The lab uses one `Standard_D2ds_v6` node (2 vCPUs) in `centralus`
(`infra/azure/cluster/terraform.tfvars`, and the region from the landing zone):

```bash
az vm list-usage --location centralus -o table | grep -Ei "total regional|Ddsv6"
```

You need at least 2 free vCPUs in both rows. If not, request more quota in the portal
(Quotas, Compute), or pick a size whose family has quota and change `node_vm_size`
(`Standard_D2ds_v5` is the fallback).

## 3. Create the kavrynt-platform foundations

The lab's resource group, budget, state container and GitHub identity live in
`kavrynt-platform/landing-zone/lab.tf`. The identity trusts this repository by GitHub's
immutable subject, `repo:AI-Platform-Engineering-Labs@344078652/azure-ai-labs@1414451235`,
so it must name the repository's current owner (the repository moved from
`kavrynt/kavrynt-labs`).

1. Merge the kavrynt-platform pull request that points `lab.identity` at
   `AI-Platform-Engineering-Labs/azure-ai-labs`.
2. In kavrynt-platform, run **Actions → Landing Zone → Run workflow** on `main`.
3. Read the plan in the approval issue. For the lab it should only *add*: the identity
   `id-kavrynt-github-lab` with two federated credentials, the resource group
   `rg-kavrynt-lab` with two role assignments (Contributor, and RBAC Administrator limited to
   AcrPull, AcrPush, AKS RBAC Cluster Admin, Network Contributor, Key Vault Secrets User and
   Key Vault Secrets Officer), the container `tfstate-lab` with one role assignment, and the
   budget. Comment `approve`.

## 4. Set the azure-ai-labs repository variables

From a kavrynt-platform checkout, the same way as its `docs/RUNBOOK-dev.md` (identifiers,
not secrets: the workflows sign in with OIDC):

```bash
REPO=AI-Platform-Engineering-Labs/azure-ai-labs
make lz-init
OUT=$(terraform -chdir=landing-zone output -json github_actions_variables)
for key in AZURE_CLIENT_ID AZURE_TENANT_ID AZURE_SUBSCRIPTION_ID; do
  gh variable set "$key" -R "$REPO" --body "$(jq -r --arg k "$key" '.["azure-ai-labs"][$k]' <<<"$OUT")"
done
# Optional: who may approve (default: whoever starts the run).
gh variable set LAB_APPROVERS -R "$REPO" --body "login1,login2"
```

**Check:** `gh variable list -R "$REPO"` lists them, and the identity's subject prefix
equals what GitHub reports for the repository:

```bash
terraform -chdir=landing-zone output -json github_subject_prefixes | jq -r '."azure-ai-labs"'
gh api "repos/$REPO/actions/oidc/customization/sub" --jq .sub_claim_prefix
```

From now on the lab workflows' Azure jobs run, and the TTL reaper checks every two hours.

## 5. Apply the lab landing zone

**Actions → Lab Landing Zone → Run workflow** on `main`, operation **apply**. Approve the
plan in the issue: a VNet with one subnet and an NSG, a static public IP, and the AKS
control-plane identity with Network Contributor on the subnet and the IP. The run summary
shows the lab's **egress IP**.

## 6. Open the Kavrynt Cloud dev firewall to the lab

Kavrynt Cloud dev accepts only listed IPs (`ip_restrictions` from
`DEV_ALLOWED_INGRESS_CIDRS` in kavrynt-platform). Add the egress IP from step 5, keeping the
existing entries:

```bash
gh variable list -R kavrynt/kavrynt-platform | grep DEV_ALLOWED_INGRESS_CIDRS
gh variable set DEV_ALLOWED_INGRESS_CIDRS -R kavrynt/kavrynt-platform \
  --body '["<existing entries>", "<egress ip>/32"]'
```

Then run kavrynt-platform's **Dev Environment** workflow (apply) so the API picks it up.
The egress IP stays the same until the lab landing zone is destroyed. Lab Integrations
checks this from inside the cluster and fails with a 403 until it is done.

## 7. First lab

1. **Actions → Azure Lab → Run workflow** on `main` with operation **plan-only**. The plan
   should create the AKS cluster (in the landing zone's subnet), the registry and their role
   assignments.
2. Then follow [azure-lab.md](azure-lab.md) to create the lab; Lab Integrations follows by
   itself.

## Undo the setup

In reverse order: Azure Lab **down**; Lab Integrations **destroy**; Lab Landing Zone
**destroy**; remove the egress IP from `DEV_ALLOWED_INGRESS_CIDRS`; then remove `lab.tf` and
the `lab` value from kavrynt-platform through a pull request and the Landing Zone workflow,
and delete the four repository variables.
