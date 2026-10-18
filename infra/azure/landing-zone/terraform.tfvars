# Lab landing zone values. kavrynt-platform's landing zone creates the resource
# group, its budget, the state container and the workflow identity
# (docs/runbooks/azure-setup.md); names here must match its terraform.tfvars.

subscription_id     = "b19634ad-4c1d-422b-a9f1-b877ad42e36b"
resource_group_name = "rg-kavrynt-lab" # region comes from the resource group

name = "kavrynt-lab"

# Kavrynt Cloud dev is 10.40.0.0/16; the lab takes the next /16.
network = {
  address_space     = "10.41.0.0/16"
  aks_subnet_prefix = "10.41.0.0/24"
}

tags = {
  product    = "kavrynt"
  managed_by = "terraform"
  stack      = "lab-landing-zone"
}
