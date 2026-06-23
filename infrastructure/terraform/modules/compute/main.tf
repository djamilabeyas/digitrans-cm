# ============================================================
# DIGITRANS-CM – Compute Module
# AKS (Azure) + EKS (AWS) + Azure Cache for Redis
# ============================================================

# ------------------------------------------------------------------
# AZURE KUBERNETES SERVICE (AKS) – Services CRM, Auth, Supply-Chain
# ------------------------------------------------------------------
resource "azurerm_kubernetes_cluster" "main" {
  name                = "${var.project}-${var.env}-aks"
  resource_group_name = var.resource_group_name
  location            = var.resource_group_location
  dns_prefix          = "${var.project}-${var.env}"
  kubernetes_version  = "1.28"

  # System node pool
  default_node_pool {
    name                = "system"
    node_count          = 2
    vm_size             = "Standard_D2s_v3"
    vnet_subnet_id      = var.app_subnet_id
    os_disk_size_gb     = 50
    type                = "VirtualMachineScaleSets"
    enable_auto_scaling = true
    min_count           = 2
    max_count           = 5

    node_labels = { "role" = "system" }
  }

  # Identité managée – intégration Key Vault sans credentials
  identity { type = "SystemAssigned" }

  # RBAC Azure AD
  azure_active_directory_role_based_access_control {
    managed            = true
    azure_rbac_enabled = true
  }

  # Réseau – Azure CNI pour intégration VNet
  network_profile {
    network_plugin = "azure"
    network_policy = "calico"      # micro-segmentation entre pods
    service_cidr   = "172.16.0.0/16"
    dns_service_ip = "172.16.0.10"
  }

  # Monitoring intégré
  oms_agent {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  }

  # Azure Key Vault Secrets Provider (CSI driver)
  key_vault_secrets_provider {
    secret_rotation_enabled  = true
    secret_rotation_interval = "2m"
  }

  tags = local.common_tags
}

# Node pool applicatif (CRM, Supply Chain)
resource "azurerm_kubernetes_cluster_node_pool" "app" {
  name                  = "app"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size               = "Standard_D4s_v3"
  vnet_subnet_id        = var.app_subnet_id
  enable_auto_scaling   = true
  min_count             = 2
  max_count             = 10
  os_disk_size_gb       = 100

  node_labels = { "role" = "app" }
  node_taints = []

  tags = local.common_tags
}

# ------------------------------------------------------------------
# AZURE CACHE FOR REDIS – Cache distribué (offline-first support)
# ------------------------------------------------------------------
resource "azurerm_redis_cache" "digitrans" {
  name                = "${var.project}-${var.env}-redis"
  resource_group_name = var.resource_group_name
  location            = var.resource_group_location
  capacity            = 1
  family              = "P"          # Premium = persistence activée
  sku_name            = "Premium"
  enable_non_ssl_port = false
  minimum_tls_version = "1.2"

  redis_configuration {
    rdb_backup_enabled            = true
    rdb_backup_frequency          = 60
    rdb_backup_max_snapshot_count = 1
    rdb_storage_connection_string = var.redis_backup_storage_connection

    # AOF pour durabilité maximale des données offline-first
    aof_backup_enabled = true
    aof_storage_connection_string_0 = var.redis_backup_storage_connection
  }

  patch_schedule {
    day_of_week    = "Sunday"
    start_hour_utc = 2
  }

  tags = local.common_tags
}

# Private endpoint pour Redis (pas d'accès Internet)
resource "azurerm_private_endpoint" "redis" {
  name                = "${var.project}-${var.env}-redis-pe"
  resource_group_name = var.resource_group_name
  location            = var.resource_group_location
  subnet_id           = var.app_subnet_id

  private_service_connection {
    name                           = "redis-psc"
    private_connection_resource_id = azurerm_redis_cache.digitrans.id
    is_manual_connection           = false
    subresource_names              = ["redisCache"]
  }

  tags = local.common_tags
}

# ------------------------------------------------------------------
# LOG ANALYTICS WORKSPACE – Monitoring centralisé
# ------------------------------------------------------------------
resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.project}-${var.env}-law"
  resource_group_name = var.resource_group_name
  location            = var.resource_group_location
  sku                 = "PerGB2018"
  retention_in_days   = 90

  tags = local.common_tags
}

# ------------------------------------------------------------------
# AWS EKS – Cluster BI (Business Intelligence)
# Région: af-south-1 (Afrique du Sud)
# ------------------------------------------------------------------
resource "aws_eks_cluster" "bi" {
  name     = "${var.project}-${var.env}-bi-eks"
  role_arn = aws_iam_role.eks_cluster.arn
  version  = "1.28"

  vpc_config {
    subnet_ids              = var.aws_private_subnets
    endpoint_private_access = true
    endpoint_public_access  = false    # cluster entièrement privé
  }

  encryption_config {
    provider { key_arn = var.aws_kms_key_arn }
    resources = ["secrets"]
  }

  enabled_cluster_log_types = ["api", "audit", "authenticator",
                                "controllerManager", "scheduler"]

  tags = local.common_tags
}

resource "aws_eks_node_group" "bi" {
  cluster_name    = aws_eks_cluster.bi.name
  node_group_name = "bi-workers"
  node_role_arn   = aws_iam_role.eks_node.arn
  subnet_ids      = var.aws_private_subnets
  instance_types  = ["r5.xlarge"]    # mémoire importante pour BI

  scaling_config {
    desired_size = 2
    min_size     = 1
    max_size     = 6
  }

  update_config { max_unavailable = 1 }

  labels = { role = "bi-worker" }
  tags   = local.common_tags
}

# IAM roles EKS
resource "aws_iam_role" "eks_cluster" {
  name = "${var.project}-${var.env}-eks-cluster-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "eks_cluster" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.eks_cluster.name
}

resource "aws_iam_role" "eks_node" {
  name = "${var.project}-${var.env}-eks-node-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "eks_node_worker" {
  for_each = toset([
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  ])
  policy_arn = each.value
  role       = aws_iam_role.eks_node.name
}

# ------------------------------------------------------------------
# Outputs
# ------------------------------------------------------------------
output "aks_cluster_name"        { value = azurerm_kubernetes_cluster.main.name }
output "aks_principal_id"        { value = azurerm_kubernetes_cluster.main.identity[0].principal_id }
output "redis_hostname"          { value = azurerm_redis_cache.digitrans.hostname }
output "redis_primary_key"       { value = azurerm_redis_cache.digitrans.primary_access_key, sensitive = true }
output "eks_cluster_name"        { value = aws_eks_cluster.bi.name }
output "log_analytics_id"        { value = azurerm_log_analytics_workspace.main.id }

locals {
  common_tags = {
    Project     = var.project
    Environment = var.env
    ManagedBy   = "Terraform"
  }
}
