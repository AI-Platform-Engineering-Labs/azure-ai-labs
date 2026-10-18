output "resource_group_name" {
  value = data.azurerm_resource_group.lab.name
}

output "cluster_name" {
  value = module.aks.name
}

output "kubernetes_version" {
  value = module.aks.current_kubernetes_version
}

output "oidc_issuer_url" {
  description = "Issuer of the cluster's service account tokens; infra/azure/integrations federates the lab workload identity with it."
  value       = module.aks.oidc_issuer_profile_issuer_url
}

output "node_resource_group_name" {
  description = "Created and deleted by AKS together with the cluster."
  value       = module.aks.node_resource_group_name
}

output "registry_name" {
  value = module.registry.name
}

output "registry_login_server" {
  value = module.registry.login_server
}

output "expires_at" {
  description = "When the TTL reaper destroys the lab."
  value       = var.expires_at
}
