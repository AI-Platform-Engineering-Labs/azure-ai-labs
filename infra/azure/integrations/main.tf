# What the lab needs to work with the rest of the platform (Lab Integrations
# workflow), after the lab landing zone and the cluster:
#   - a secret store: a Key Vault for lab secrets (later the Kavrynt Cloud
#     cluster token and the agents' Zitadel credentials), kept across cluster
#     rebuilds so secrets survive a "down";
#   - a workload identity that lab pods use to read it, federated with the
#     cluster that is up now. Each cluster has its own OIDC issuer, so every
#     rebuild re-points the credential, and a "down" removes it.
# The Kavrynt Cloud dev firewall is opened in kavrynt-platform (repository
# variable DEV_ALLOWED_INGRESS_CIDRS) for the lab landing zone's egress IP; the
# workflow checks from inside the cluster that it is.

data "azurerm_client_config" "current" {}

data "azurerm_resource_group" "lab" {
  name = var.resource_group_name
}

data "terraform_remote_state" "landing_zone" {
  backend = "azurerm"
  config = merge(var.state_backend, {
    key              = "landing-zone.tfstate"
    use_azuread_auth = true
  })
}

# Empty while the lab is down (the cluster stack's state holds no outputs then).
data "terraform_remote_state" "cluster" {
  backend = "azurerm"
  config = merge(var.state_backend, {
    key              = "lab.tfstate"
    use_azuread_auth = true
  })
}

locals {
  cluster_issuer = try(data.terraform_remote_state.cluster.outputs.oidc_issuer_url, null)
  # The Kubernetes service account lab pods run as (cluster/integrations).
  workload_subject = "system:serviceaccount:${var.workload_service_account.namespace}:${var.workload_service_account.name}"
}

resource "random_string" "key_vault_suffix" {
  length  = 6
  special = false
  upper   = false
}

# trivy:ignore:AZU-0013 Lab only: GitHub-hosted runners have no fixed IPs, so the vault keeps public access with Entra RBAC as the gate, like Kavrynt Cloud dev's vault. It holds lab secrets only.
module "key_vault" {
  source  = "Azure/avm-res-keyvault-vault/azurerm"
  version = "0.11.0"

  name                = "${var.key_vault_name_prefix}-${random_string.key_vault_suffix.result}"
  resource_group_name = data.azurerm_resource_group.lab.name
  location            = data.azurerm_resource_group.lab.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  enable_telemetry    = var.enable_telemetry
  tags                = var.tags

  sku_name                      = "standard"
  purge_protection_enabled      = true
  soft_delete_retention_days    = 7
  public_network_access_enabled = true

  network_acls = {
    bypass         = "AzureServices"
    default_action = "Allow"
  }

  # RBAC only; the lab identity may grant exactly these two Key Vault roles in
  # rg-kavrynt-lab (kavrynt-platform landing-zone/lab.tf).
  role_assignments = {
    workload_secrets_user = {
      role_definition_id_or_name = "Key Vault Secrets User"
      principal_id               = module.workload_identity.principal_id
      principal_type             = "ServicePrincipal"
    }
    deployer_secrets_officer = {
      role_definition_id_or_name = "Key Vault Secrets Officer"
      principal_id               = data.azurerm_client_config.current.object_id
    }
    admins_secrets_officer = {
      role_definition_id_or_name = "Key Vault Secrets Officer"
      principal_id               = var.admins_group_object_id
      principal_type             = "Group"
    }
  }

  # A canary the in-cluster check reads through the CSI driver, proving the
  # whole path: workload identity -> Entra -> Key Vault -> mounted file. Not a
  # secret; written write-only so that real secrets later follow the same
  # pattern and never reach state.
  secrets = {
    canary = {
      name            = var.canary_secret.name
      content_type    = "text/plain"
      expiration_date = var.canary_secret.expires_at
    }
  }
  secrets_value_wo         = { canary = var.canary_secret.value }
  secrets_value_wo_version = { canary = var.canary_secret.version }

  # Role assignments can take a while to reach the Key Vault data plane.
  wait_for_rbac_before_secret_operations = {
    create = "120s"
  }
}

# Lab pods' Azure identity. Kept with the vault; only its federated credential
# follows the cluster.
module "workload_identity" {
  source  = "Azure/avm-res-managedidentity-userassignedidentity/azurerm"
  version = "0.5.3"

  name                = "id-${var.name}-workload"
  resource_group_name = data.azurerm_resource_group.lab.name
  location            = data.azurerm_resource_group.lab.location
  enable_telemetry    = var.enable_telemetry
  tags                = var.tags

  federated_identity_credentials = local.cluster_issuer == null ? {} : {
    cluster = {
      name     = "${var.name}-cluster-${var.workload_service_account.name}"
      audience = ["api://AzureADTokenExchange"]
      issuer   = local.cluster_issuer
      subject  = local.workload_subject
    }
  }
}
