# Values live in infra/azure/cluster/terraform.tfvars; expires_at and
# requested_by come from the Azure Lab workflow for every run.

variable "subscription_id" {
  description = "Subscription that hosts the lab (the Kavrynt dev subscription)."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", var.subscription_id))
    error_message = "subscription_id must be a GUID."
  }
}

variable "resource_group_name" {
  description = "Existing lab resource group. kavrynt-platform's landing zone owns it, its budget, and this stack's GitHub identity; this stack only fills it."
  type        = string
}

variable "state_backend" {
  description = "Where the lab stacks keep their state (must match backend.hcl); the cluster reads the lab landing zone's outputs from there."
  type = object({
    resource_group_name  = string
    storage_account_name = string
    container_name       = string
  })
}

variable "cluster_name" {
  description = "AKS cluster name; also its DNS prefix and kubectl context."
  type        = string
}

variable "registry_name_prefix" {
  description = "Container registry name prefix. A random suffix keeps the globally unique name free across rebuilds."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]{5,44}$", var.registry_name_prefix))
    error_message = "registry_name_prefix must be 5-44 lowercase letters or digits."
  }
}

variable "node_vm_size" {
  description = "VM size of the single system node pool. Needs at least 2 vCPUs and 4 GiB, and regional vCPU quota for its family."
  type        = string
}

variable "node_count" {
  description = "Nodes in the system pool. One is enough for the lab."
  type        = number

  validation {
    condition     = var.node_count >= 1 && var.node_count <= 3
    error_message = "node_count must be between 1 and 3."
  }
}

variable "kubernetes_version" {
  description = "Kubernetes <major.minor>, or null for the AKS default. The lab never upgrades in place: it is rebuilt."
  type        = string
  default     = null
}

variable "admins_group_object_id" {
  description = "Entra group of platform administrators (kavrynt-platform-admins). Gets cluster admin through Azure RBAC so people can inspect the lab with kubectl."
  type        = string
}

variable "expires_at" {
  description = "UTC time (RFC 3339, e.g. 2026-10-12T18:00:00Z) after which the TTL reaper destroys the lab. Set by the Azure Lab workflow."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", var.expires_at))
    error_message = "expires_at must be a UTC timestamp like 2026-10-12T18:00:00Z."
  }
}

variable "requested_by" {
  description = "Who asked for this lab (GitHub login or ttl-reaper). Recorded as a tag."
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
