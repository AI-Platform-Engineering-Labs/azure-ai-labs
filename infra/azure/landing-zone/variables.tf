# Values live in infra/azure/landing-zone/terraform.tfvars.

variable "subscription_id" {
  description = "Subscription that hosts the lab (the Kavrynt dev subscription)."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", var.subscription_id))
    error_message = "subscription_id must be a GUID."
  }
}

variable "resource_group_name" {
  description = "Existing lab resource group. kavrynt-platform's landing zone owns it, its budget, and the lab's GitHub identity; this stack only fills it."
  type        = string
}

variable "name" {
  description = "Base name of the lab's resources (vnet-<name>, pip-<name>-egress, id-<name>-aks)."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,30}$", var.name))
    error_message = "name must be 3-31 lowercase letters, digits or hyphens, starting with a letter."
  }
}

variable "network" {
  description = "Lab VNet and its AKS node subnet. Must not overlap Kavrynt Cloud dev (10.40.0.0/16) or the cluster's pod and service ranges (10.244.0.0/16, 10.0.0.0/16)."
  type = object({
    address_space     = string
    aks_subnet_prefix = string
  })

  validation {
    condition     = can(cidrhost(var.network.address_space, 0)) && can(cidrhost(var.network.aks_subnet_prefix, 0))
    error_message = "network.address_space and network.aks_subnet_prefix must be CIDR ranges."
  }
}

variable "enable_telemetry" {
  description = "Azure Verified Modules usage telemetry sent to Microsoft."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
}
