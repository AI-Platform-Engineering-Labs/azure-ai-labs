# Lab integrations values. Applied after the lab landing zone and, to federate
# the workload identity, after the cluster (docs/runbooks/azure-lab.md).

subscription_id     = "b19634ad-4c1d-422b-a9f1-b877ad42e36b"
resource_group_name = "rg-kavrynt-lab" # region comes from the resource group

# Same container as backend.hcl.
state_backend = {
  resource_group_name  = "rg-kavrynt-platform"
  storage_account_name = "stkavryntstate01"
  container_name       = "tfstate-lab"
}

name                  = "kavrynt-lab"
key_vault_name_prefix = "kv-kavrynt-lab"

workload_service_account = {
  namespace = "lab-agents"
  name      = "lab-workload"
}

canary_secret = {
  name       = "lab-canary"
  value      = "kavrynt-lab-canary"
  version    = 1
  expires_at = "2027-10-01T00:00:00Z"
}

# Kavrynt Cloud dev (kavrynt-platform environments/dev, custom_domain).
cloud_api_url = "https://app.dev.kavrynt.com"

# kavrynt-platform-admins (Entra group).
admins_group_object_id = "b4df042c-2a8e-436e-8fb8-4f6ee59482b0"

tags = {
  product    = "kavrynt"
  managed_by = "terraform"
  stack      = "lab-integrations"
}
