# Runbook: one-time Azure setup

The Azure lab runs in the Kavrynt dev subscription, in its own resource group. Do these
steps once, in order. Every step after the first two goes through a pipeline.

What you need: Owner on the subscription (steps 1 and 2 only), admin on the
`kavrynt-platform` and `kavrynt-labs` repositories, the Azure CLI, and membership in the
`kavrynt-platform-admins` Entra group (to reach the cluster later).

## 1. Register the resource providers (Owner)

Plans never change the subscription (`resource_provider_registrations = "none"`), so
register what the lab uses once:

```bash
az account set --subscription b19634ad-4c1d-422b-a9f1-b877ad42e36b
for ns in Microsoft.ContainerService Microsoft.ContainerRegistry Microsoft.Consumption; do
  az provider register --namespace "$ns"
done
az provider list --query "[?namespace=='Microsoft.ContainerService' || namespace=='Microsoft.ContainerRegistry' || namespace=='Microsoft.Consumption'].{ns:namespace, state:registrationState}" -o table
```

Wait until all three say `Registered`.

## 2. Check the vCPU quota

The lab uses one `Standard_B2s_v2` node (2 vCPUs) in `centralus`
(`infra/azure/terraform.tfvars`, and the region from the landing zone):

```bash
az vm list-usage --location centralus -o table | grep -Ei "total regional|BSv2"
```

You need at least 2 free vCPUs in both rows. If not, request more quota in the portal
(Quotas, Compute), or pick a size whose family has quota and change `node_vm_size`.

## 3. Create the landing zone foundations (kavrynt-platform)

The lab's resource group, budget, state container and GitHub identity live in
`kavrynt-platform/landing-zone/lab.tf`.

1. Merge the kavrynt-platform pull request that adds `landing-zone/lab.tf`.
2. In kavrynt-platform, run **Actions → Landing Zone → Run workflow** on `main`.
3. Read the plan in the approval issue. It should only *add*: the identity
   `id-kavrynt-github-lab` with two federated credentials, the resource group
   `rg-kavrynt-lab` with two role assignments, the container `tfstate-lab` with one role
   assignment, and the budget. Comment `approve`.

## 4. Set the kavrynt-labs repository variables

From a kavrynt-platform checkout, the same way as its `docs/RUNBOOK-dev.md` (identifiers,
not secrets: the workflow signs in with OIDC):

```bash
make lz-init
OUT=$(terraform -chdir=landing-zone output -json github_actions_variables)
for key in AZURE_CLIENT_ID AZURE_TENANT_ID AZURE_SUBSCRIPTION_ID; do
  gh variable set "$key" -R kavrynt/kavrynt-labs \
    --body "$(jq -r --arg k "$key" '.["kavrynt-labs"][$k]' <<<"$OUT")"
done
# Optional: who may approve "up" (default: whoever starts the run).
gh variable set LAB_APPROVERS -R kavrynt/kavrynt-labs --body "login1,login2"
```

**Check:** `gh variable list -R kavrynt/kavrynt-labs` lists them, and the identity's subject
prefix equals what GitHub reports for the repository:

```bash
terraform -chdir=landing-zone output -json github_subject_prefixes | jq -r '."kavrynt-labs"'
gh api repos/kavrynt/kavrynt-labs/actions/oidc/customization/sub --jq .sub_claim_prefix
```

From now on the **Azure Lab** workflow's Azure jobs run, and the TTL reaper checks every two
hours.

## 5. First run

1. **Actions → Azure Lab → Run workflow** on `main` with operation **plan-only**. The plan
   should create the AKS cluster, the registry and their role assignments.
2. Then follow [azure-lab.md](azure-lab.md) to create the lab.

## Undo the setup

The lab stack must be down first (operation **down**; the run's last step confirms that
nothing is left). Then remove `lab.tf` and the `lab` value from kavrynt-platform through a
pull request and the Landing Zone workflow, and delete the four repository variables.
