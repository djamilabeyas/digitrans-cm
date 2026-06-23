# ============================================================
# DIGITRANS-CM – Environnement Production
# ============================================================

terraform {
  required_version = ">= 1.7"

  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 3.90" }
    aws     = { source = "hashicorp/aws",     version = "~> 5.40" }
  }

  backend "azurerm" {
    resource_group_name  = "digitrans-tfstate-rg"
    storage_account_name = "digitranstfstateprod"
    container_name       = "tfstate"
    key                  = "prod/terraform.tfstate"
    use_oidc             = true   # authentification sans credentials stockés
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
    resource_group {
      prevent_deletion_if_contains_resources = true
    }
  }
  use_oidc = true
}

provider "aws" {
  region = "af-south-1"
}

# ------------------------------------------------------------------
# Modules
# ------------------------------------------------------------------
module "networking" {
  source       = "../../modules/networking"
  project      = local.project
  env          = local.env
  azure_region = "egyptcentral"
  aws_region   = "af-south-1"
}

module "security" {
  source                   = "../../modules/security"
  project                  = local.project
  env                      = local.env
  resource_group_name      = module.networking.resource_group_name
  resource_group_location  = module.networking.resource_group_location
  public_subnet_id         = module.networking.azure_public_subnet
  app_subnet_id            = module.networking.azure_app_subnet
  aks_principal_id         = module.compute.aks_principal_id
  allowed_ip_ranges        = ["197.234.0.0/16"]  # IP ranges Cameroun CAMTEL/MTN
}

module "compute" {
  source                            = "../../modules/compute"
  project                           = local.project
  env                               = local.env
  resource_group_name               = module.networking.resource_group_name
  resource_group_location           = module.networking.resource_group_location
  app_subnet_id                     = module.networking.azure_app_subnet
  aws_private_subnets               = module.networking.aws_private_subnets
  aws_kms_key_arn                   = var.aws_kms_key_arn
  redis_backup_storage_connection   = var.redis_backup_storage_connection
}

module "database" {
  source                   = "../../modules/database"
  project                  = local.project
  env                      = local.env
  resource_group_name      = module.networking.resource_group_name
  resource_group_location  = module.networking.resource_group_location
  db_subnet_id             = module.networking.azure_db_subnet
  vnet_id                  = module.networking.azure_vnet_id
  tenant_id                = var.tenant_id
  app_service_principal_id = var.app_service_principal_id
  db_admin_user            = var.db_admin_user
  db_admin_password        = var.db_admin_password
  aws_private_subnets      = module.networking.aws_private_subnets
  aws_vpc_id               = module.networking.aws_vpc_id
  aws_kms_key_arn          = var.aws_kms_key_arn
  bi_db_user               = var.bi_db_user
  bi_db_password           = var.bi_db_password
}

locals {
  project = "digitrans-cm"
  env     = "prod"
}
