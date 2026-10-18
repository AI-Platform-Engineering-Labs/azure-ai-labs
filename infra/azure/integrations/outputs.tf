# Read by the Lab Integrations workflow to configure the cluster
# (scripts/lab.sh integrations).

output "key_vault_name" {
  value = module.key_vault.name
}

output "key_vault_uri" {
  value = module.key_vault.uri
}

output "tenant_id" {
  value = data.azurerm_client_config.current.tenant_id
}

output "workload_client_id" {
  value = module.workload_identity.client_id
}

output "workload_service_account" {
  value = "${var.workload_service_account.namespace}/${var.workload_service_account.name}"
}

output "canary_secret_name" {
  value = var.canary_secret.name
}

output "canary_secret_value" {
  description = "Not a secret: what the in-cluster check expects to read from the vault."
  value       = var.canary_secret.value
}

output "cloud_api_url" {
  value = var.cloud_api_url
}

output "egress_ip_address" {
  description = "Must be in kavrynt-platform's DEV_ALLOWED_INGRESS_CIDRS (as /32). Null once the landing zone is gone, so this stack can still be destroyed."
  value       = try(data.terraform_remote_state.landing_zone.outputs.egress_ip_address, null)
}

output "cluster_federated" {
  description = "Whether the workload identity trusts a running cluster (false while the lab is down)."
  value       = local.cluster_issuer != null
}
