# The lab's landing zone: the network the cluster is built into, kept across
# cluster rebuilds (Lab Landing Zone workflow). It costs about USD 4 a month,
# the static egress IP; everything else here is free.
#
# kavrynt-platform's landing zone (landing-zone/lab.tf) owns what must exist
# before any lab workflow can sign in: rg-kavrynt-lab itself, its budget, the
# state container and this workflow's identity. The order of the lab's stacks:
#   1. landing-zone   this stack
#   2. cluster        AKS and a registry, built into this network (Azure Lab)
#   3. integrations   Key Vault and the cluster's workload identity (Lab Integrations)

data "azurerm_resource_group" "lab" {
  name = var.resource_group_name
}

# Azure's default rules only: inbound from the internet is denied, traffic
# inside the VNet and from the Azure load balancer is allowed. Attached
# explicitly so that lab rules have one place to go.
module "aks_nsg" {
  source  = "Azure/avm-res-network-networksecuritygroup/azurerm"
  version = "0.5.2"

  name                = "nsg-${var.name}-aks"
  resource_group_name = data.azurerm_resource_group.lab.name
  location            = data.azurerm_resource_group.lab.location
  enable_telemetry    = var.enable_telemetry
  tags                = var.tags
}

# Address space next to Kavrynt Cloud dev (10.40.0.0/16) without overlapping
# it, so the two can be peered later. Azure CNI Overlay gives pods addresses
# outside the VNet; the subnet holds nodes only.
module "vnet" {
  source  = "Azure/avm-res-network-virtualnetwork/azurerm"
  version = "0.22.2"

  name             = "vnet-${var.name}"
  parent_id        = data.azurerm_resource_group.lab.id
  location         = data.azurerm_resource_group.lab.location
  address_space    = [var.network.address_space]
  enable_telemetry = var.enable_telemetry
  tags             = var.tags

  subnets = {
    aks = {
      name           = "snet-aks"
      address_prefix = var.network.aks_subnet_prefix
      # Egress leaves through the cluster load balancer and the static IP
      # below, never through Azure's default outbound access.
      default_outbound_access_enabled = false
      network_security_group          = { id = module.aks_nsg.resource_id }

      role_assignments = {
        aks_network_contributor = {
          role_definition_id_or_name = "Network Contributor"
          principal_id               = module.aks_identity.principal_id
          principal_type             = "ServicePrincipal"
        }
      }
    }
  }
}

# The lab's one public address: every connection from the cluster to the
# internet uses it, so Kavrynt Cloud dev can allow it by IP
# (kavrynt-platform repository variable DEV_ALLOWED_INGRESS_CIDRS). Nothing
# listens on it: the lab has no ingress and no LoadBalancer services.
module "egress_ip" {
  source  = "Azure/avm-res-network-publicipaddress/azurerm"
  version = "0.2.1"

  name                = "pip-${var.name}-egress"
  resource_group_name = data.azurerm_resource_group.lab.name
  location            = data.azurerm_resource_group.lab.location
  enable_telemetry    = var.enable_telemetry
  tags                = var.tags

  sku               = "Standard"
  allocation_method = "Static"
  ip_version        = "IPv4"

  role_assignments = {
    aks_network_contributor = {
      role_definition_id_or_name = "Network Contributor"
      principal_id               = module.aks_identity.principal_id
      principal_type             = "ServicePrincipal"
    }
  }
}

# The AKS control plane's identity. User-assigned so that its roles on the
# subnet and the egress IP exist before the cluster does, and survive rebuilds.
module "aks_identity" {
  source  = "Azure/avm-res-managedidentity-userassignedidentity/azurerm"
  version = "0.5.3"

  name                = "id-${var.name}-aks"
  resource_group_name = data.azurerm_resource_group.lab.name
  location            = data.azurerm_resource_group.lab.location
  enable_telemetry    = var.enable_telemetry
  tags                = var.tags
}
