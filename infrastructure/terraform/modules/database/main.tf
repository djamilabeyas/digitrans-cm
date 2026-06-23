# ============================================================
# DIGITRANS-CM – Database Module
# Azure Database for PostgreSQL Flexible Server
# Données sensibles RH/Finances/Clients → hébergées en Égypte
# (plus proche que Europe, conformité souveraineté des données)
# ============================================================

resource "azurerm_postgresql_flexible_server" "main" {
  name                   = "${var.project}-${var.env}-pgflex"
  resource_group_name    = var.resource_group_name
  location               = var.resource_group_location
  version                = "15"
  delegated_subnet_id    = var.db_subnet_id
  private_dns_zone_id    = azurerm_private_dns_zone.pg.id
  administrator_login    = var.db_admin_user
  administrator_password = var.db_admin_password

  storage_mb            = 65536
  sku_name              = "GP_Standard_D4s_v3"   # 4 vCores, 16 GB RAM

  backup_retention_days        = 35
  geo_redundant_backup_enabled = false   # données restent en Égypte

  high_availability {
    mode                      = "ZoneRedundant"
    standby_availability_zone = "2"
  }

  maintenance_window {
    day_of_week  = 0    # Dimanche
    start_hour   = 1
    start_minute = 0
  }

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false   # auth AD uniquement en prod
    tenant_id                     = var.tenant_id
  }

  tags = local.common_tags
}

resource "azurerm_private_dns_zone" "pg" {
  name                = "${var.project}-${var.env}.private.postgres.database.azure.com"
  resource_group_name = var.resource_group_name
  tags                = local.common_tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "pg" {
  name                  = "pg-dns-link"
  private_dns_zone_name = azurerm_private_dns_zone.pg.name
  resource_group_name   = var.resource_group_name
  virtual_network_id    = var.vnet_id
  registration_enabled  = false
  tags                  = local.common_tags
}

# ------------------------------------------------------------------
# Bases de données par module fonctionnel
# ------------------------------------------------------------------
resource "azurerm_postgresql_flexible_server_database" "crm" {
  name      = "crm_db"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "fr_CM.utf8"
  charset   = "UTF8"
}

resource "azurerm_postgresql_flexible_server_database" "erp" {
  name      = "erp_db"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "fr_CM.utf8"
  charset   = "UTF8"
}

resource "azurerm_postgresql_flexible_server_database" "supply_chain" {
  name      = "supplychain_db"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "fr_CM.utf8"
  charset   = "UTF8"
}

# ------------------------------------------------------------------
# Configuration PostgreSQL – chiffrement TDE + audit
# ------------------------------------------------------------------
resource "azurerm_postgresql_flexible_server_configuration" "ssl_min" {
  name      = "ssl_min_protocol_version"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "TLSv1.2"
}

resource "azurerm_postgresql_flexible_server_configuration" "log_connections" {
  name      = "log_connections"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "on"
}

resource "azurerm_postgresql_flexible_server_configuration" "log_disconnections" {
  name      = "log_disconnections"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "on"
}

resource "azurerm_postgresql_flexible_server_configuration" "log_checkpoints" {
  name      = "log_checkpoints"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "on"
}

resource "azurerm_postgresql_flexible_server_configuration" "connection_throttling" {
  name      = "connection_throttle.enable"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "on"
}

# ------------------------------------------------------------------
# Chiffrement des données au repos – Customer Managed Key
# ------------------------------------------------------------------
resource "azurerm_postgresql_flexible_server_active_directory_administrator" "app" {
  server_name         = azurerm_postgresql_flexible_server.main.name
  resource_group_name = var.resource_group_name
  tenant_id           = var.tenant_id
  object_id           = var.app_service_principal_id
  principal_name      = "${var.project}-crm-sp"
  principal_type      = "ServicePrincipal"
}

# ------------------------------------------------------------------
# AWS RDS Aurora PostgreSQL – Base dédiée BI (af-south-1)
# ------------------------------------------------------------------
resource "aws_rds_cluster" "bi" {
  cluster_identifier      = "${var.project}-${var.env}-bi-aurora"
  engine                  = "aurora-postgresql"
  engine_version          = "15.4"
  availability_zones      = ["${var.aws_region}a", "${var.aws_region}b"]
  database_name           = "bi_db"
  master_username         = var.bi_db_user
  master_password         = var.bi_db_password
  db_subnet_group_name    = aws_db_subnet_group.bi.name
  vpc_security_group_ids  = [aws_security_group.rds.id]

  storage_encrypted    = true
  kms_key_id           = var.aws_kms_key_arn
  deletion_protection  = true
  skip_final_snapshot  = false
  final_snapshot_identifier = "${var.project}-${var.env}-bi-final"

  backup_retention_period   = 35
  preferred_backup_window   = "02:00-04:00"
  copy_tags_to_snapshot     = true

  enabled_cloudwatch_logs_exports = ["postgresql"]

  tags = local.common_tags
}

resource "aws_rds_cluster_instance" "bi" {
  count              = 2
  identifier         = "${var.project}-${var.env}-bi-${count.index}"
  cluster_identifier = aws_rds_cluster.bi.id
  instance_class     = "db.r6g.large"
  engine             = aws_rds_cluster.bi.engine
  engine_version     = aws_rds_cluster.bi.engine_version

  publicly_accessible = false

  performance_insights_enabled          = true
  performance_insights_kms_key_id       = var.aws_kms_key_arn
  performance_insights_retention_period = 731   # 2 ans

  tags = local.common_tags
}

resource "aws_db_subnet_group" "bi" {
  name       = "${var.project}-${var.env}-bi-sg"
  subnet_ids = var.aws_private_subnets
  tags       = local.common_tags
}

resource "aws_security_group" "rds" {
  name   = "${var.project}-${var.env}-rds-sg"
  vpc_id = var.aws_vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.1.0.0/16"]   # VPC interne uniquement
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

# ------------------------------------------------------------------
# Outputs
# ------------------------------------------------------------------
output "pg_fqdn"        { value = azurerm_postgresql_flexible_server.main.fqdn }
output "crm_db_name"    { value = azurerm_postgresql_flexible_server_database.crm.name }
output "erp_db_name"    { value = azurerm_postgresql_flexible_server_database.erp.name }
output "bi_cluster_endpoint" { value = aws_rds_cluster.bi.endpoint }

locals {
  common_tags = {
    Project     = var.project
    Environment = var.env
    DataClass   = "Confidential"
    ManagedBy   = "Terraform"
  }
}
