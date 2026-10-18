# Azure lab values. kavrynt-platform's landing zone creates the resource group,
# its budget, the state container and the workflow identity
# (docs/runbooks/azure-setup.md); names here must match its terraform.tfvars.

subscription_id     = "b19634ad-4c1d-422b-a9f1-b877ad42e36b"
resource_group_name = "rg-kavrynt-lab" # region comes from the resource group

# Same container as backend.hcl; the landing zone's state is landing-zone.tfstate.
state_backend = {
  resource_group_name  = "rg-kavrynt-platform"
  storage_account_name = "stkavryntstate01"
  container_name       = "tfstate-lab"
}

cluster_name         = "aks-kavrynt-lab"
registry_name_prefix = "acrkavryntlab"

# 2 vCPUs / 8 GiB: enough for Kavrynt, Cilium, two MCP servers, three agents,
# Prometheus and Grafana. Check family quota before the first run
# (az vm list-usage --location <region>).
node_vm_size = "Standard_D2ds_v6"
node_count   = 1

# kavrynt-platform-admins (Entra group).
admins_group_object_id = "b4df042c-2a8e-436e-8fb8-4f6ee59482b0"

tags = {
  product    = "kavrynt"
  managed_by = "terraform"
  stack      = "lab-cluster"
}
