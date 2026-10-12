# The Azure lab: one small AKS cluster and a registry for the lab image, inside
# the landing-zone-owned rg-kavrynt-lab. Everything here is destroyed when the
# lab is not in use (the Azure Lab workflow: operation "down" or the TTL
# reaper); the resource group, budget, state container and GitHub identity stay
# in kavrynt-platform's landing zone at about zero cost.

locals {
  # The TTL reaper reads these tags from the cluster (docs/runbooks/azure-lab.md).
  tags = merge(var.tags, {
    "kavrynt-lab-expires-at"   = var.expires_at
    "kavrynt-lab-requested-by" = var.requested_by
  })
}

data "azurerm_client_config" "current" {}

data "azurerm_resource_group" "lab" {
  name = var.resource_group_name
}

resource "random_string" "registry_suffix" {
  length  = 6
  special = false
  upper   = false
}

# Holds the kavrynt-lab image that the workflow builds for each run. It lives
# and dies with the lab, so a rebuild pushes a fresh image.
#
# Public endpoint (lab only): GitHub-hosted runners have no fixed IPs. Push and
# pull still require Entra RBAC: no admin user, no anonymous pull.
module "registry" {
  source  = "Azure/avm-res-containerregistry-registry/azurerm"
  version = "0.8.0"

  name                = "${var.registry_name_prefix}${random_string.registry_suffix.result}"
  resource_group_name = data.azurerm_resource_group.lab.name
  location            = data.azurerm_resource_group.lab.location
  enable_telemetry    = var.enable_telemetry
  tags                = local.tags

  sku                           = "Basic"
  zone_redundancy_enabled       = false
  admin_enabled                 = false
  anonymous_pull_enabled        = false
  public_network_access_enabled = true

  # AcrPull and AcrPush are the only roles the lab identity may delegate in
  # rg-kavrynt-lab besides AKS RBAC Cluster Admin (landing zone condition).
  role_assignments = {
    # Whoever applies this stack (the workflow identity) pushes the lab image.
    deployer_push = {
      role_definition_id_or_name = "AcrPush"
      principal_id               = data.azurerm_client_config.current.object_id
    }
    kubelet_pull = {
      role_definition_id_or_name = "AcrPull"
      principal_id               = module.aks.kubelet_identity.objectId
      principal_type             = "ServicePrincipal"
    }
  }
}

# Free tier control plane, one node, no in-place upgrades: the lab is rebuilt
# rather than maintained.
#
# Public API server (lab only): GitHub-hosted runners have no fixed IPs, so
# authorized IP ranges cannot be used. Local accounts are disabled; every call
# needs an Entra token and an Azure RBAC role on this cluster. No workload is
# exposed: the lab has no ingress and no LoadBalancer services.
module "aks" {
  source  = "Azure/avm-res-containerservice-managedcluster/azurerm"
  version = "0.8.4"

  name               = var.cluster_name
  location           = data.azurerm_resource_group.lab.location
  parent_id          = data.azurerm_resource_group.lab.id
  dns_prefix         = var.cluster_name
  kubernetes_version = var.kubernetes_version
  enable_telemetry   = var.enable_telemetry
  tags               = local.tags

  sku = {
    name = "Base"
    tier = "Free"
  }

  managed_identities = {
    system_assigned = true
  }

  aad_profile = {
    managed                = true
    enable_azure_rbac      = true
    tenant_id              = data.azurerm_client_config.current.tenant_id
    admin_group_object_ids = []
  }
  disable_local_accounts = true

  default_agent_pool = {
    name            = "system"
    mode            = "System"
    count_of        = var.node_count
    vm_size         = var.node_vm_size
    os_sku          = "AzureLinux"
    os_disk_size_gb = 64

    upgrade_settings = {
      max_surge = "10%"
    }
  }

  network_profile = {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    load_balancer_sku   = "standard"
    outbound_type       = "loadBalancer"
  }

  auto_upgrade_profile = {
    upgrade_channel         = "none"
    node_os_upgrade_channel = "None"
  }

  role_assignments = {
    # The workflow deploys the lab with kubectl and Helm.
    deployer_cluster_admin = {
      role_definition_id_or_name = "Azure Kubernetes Service RBAC Cluster Admin"
      principal_id               = data.azurerm_client_config.current.object_id
    }
    # Platform administrators inspect the lab (port-forward Grafana, kubectl).
    admins_cluster_admin = {
      role_definition_id_or_name = "Azure Kubernetes Service RBAC Cluster Admin"
      principal_id               = var.admins_group_object_id
      principal_type             = "Group"
    }
  }
}
