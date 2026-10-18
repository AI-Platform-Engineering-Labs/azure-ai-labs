# Values live in infra/azure/integrations/terraform.tfvars.

variable "subscription_id" {
  description = "Subscription that hosts the lab (the Kavrynt dev subscription)."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", var.subscription_id))
    error_message = "subscription_id must be a GUID."
  }
}

variable "resource_group_name" {
  description = "Existing lab resource group (kavrynt-platform's landing zone)."
  type        = string
}

variable "state_backend" {
  description = "Where the lab stacks keep their state (must match backend.hcl); this stack reads the landing zone's and the cluster's outputs from there."
  type = object({
    resource_group_name  = string
    storage_account_name = string
    container_name       = string
  })
}

variable "name" {
  description = "Base name of the lab's resources (id-<name>-workload)."
  type        = string
}

variable "key_vault_name_prefix" {
  description = "Key Vault name prefix. A random suffix keeps the globally unique name free: a deleted vault stays reserved during soft delete."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,16}$", var.key_vault_name_prefix))
    error_message = "key_vault_name_prefix must be 3-17 lowercase letters, digits or hyphens, starting with a letter."
  }
}

variable "workload_service_account" {
  description = "Kubernetes service account that lab pods use for workload identity (cluster/integrations/workload.yaml)."
  type = object({
    namespace = string
    name      = string
  })
}

variable "canary_secret" {
  description = "Non-secret value the in-cluster check reads from the vault. Increase version to rewrite it."
  type = object({
    name       = string
    value      = string
    version    = number
    expires_at = string
  })
}

variable "cloud_api_url" {
  description = "Kavrynt Cloud dev API that the lab must reach through its egress IP (checked from inside the cluster)."
  type        = string

  validation {
    condition     = can(regex("^https://", var.cloud_api_url))
    error_message = "cloud_api_url must be an https:// URL."
  }
}

variable "admins_group_object_id" {
  description = "Entra group of platform administrators (kavrynt-platform-admins). Manages lab secrets."
  type        = string
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
