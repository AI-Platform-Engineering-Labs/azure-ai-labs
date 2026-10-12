terraform {
  # Azure Verified Modules require Terraform 1.12+. Same version as kavrynt-platform.
  required_version = ">= 1.12.0, < 2.0.0"

  required_providers {
    # AVM resource modules support azurerm 4.x only.
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.81"
    }
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.12"
    }
    modtm = {
      source  = "Azure/modtm"
      version = "~> 0.3"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
  }

  # Partial configuration: terraform -chdir=infra/azure init -backend-config=backend.hcl
  backend "azurerm" {}
}

provider "azurerm" {
  subscription_id = var.subscription_id
  # Plans must never change the subscription; providers are registered once
  # through docs/runbooks/azure-setup.md.
  resource_provider_registrations = "none"
  storage_use_azuread             = true

  features {}
}

provider "azapi" {
  subscription_id = var.subscription_id
}
