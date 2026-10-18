# terraform -chdir=infra/azure/landing-zone init -backend-config=backend.hcl
# The container is created by kavrynt-platform's landing zone; the lab identity
# can read and write this container only. One key per lab stack.
resource_group_name  = "rg-kavrynt-platform"
storage_account_name = "stkavryntstate01"
container_name       = "tfstate-lab"
key                  = "landing-zone.tfstate"
use_azuread_auth     = true
