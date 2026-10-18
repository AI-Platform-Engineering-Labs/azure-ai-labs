# Read by the cluster and integrations stacks (terraform_remote_state) and by
# the workflows' "Require ..." steps.

output "resource_group_name" {
  value = data.azurerm_resource_group.lab.name
}

output "location" {
  value = data.azurerm_resource_group.lab.location
}

output "vnet_id" {
  value = module.vnet.resource_id
}

output "aks_subnet_id" {
  value = module.vnet.subnets["aks"].resource_id
}

output "egress_ip_id" {
  value = module.egress_ip.public_ip_id
}

output "egress_ip_address" {
  description = "Add <address>/32 to kavrynt-platform's DEV_ALLOWED_INGRESS_CIDRS so the lab can reach Kavrynt Cloud dev."
  value       = module.egress_ip.public_ip_address
}

output "aks_identity_id" {
  value = module.aks_identity.resource_id
}
