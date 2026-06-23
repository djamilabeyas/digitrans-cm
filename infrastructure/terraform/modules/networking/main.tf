# ============================================================
# DIGITRANS-CM – Networking Module
# Hybrid: Azure Egypt (az) + AWS South Africa (aws)
# Data sovereignty: sensitive data stays on-premise (Douala)
# ============================================================

terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 3.90" }
    aws     = { source = "hashicorp/aws",     version = "~> 5.40" }
  }
}

# ------------------------------------------------------------------
# AZURE – Virtual Network (Egypt region – faible latence Afrique)
# ------------------------------------------------------------------
resource "azurerm_resource_group" "digitrans" {
  name     = "${var.project}-${var.env}-rg"
  location = var.azure_region   # "egyptcentral"
  tags     = local.common_tags
}

resource "azurerm_virtual_network" "main" {
  name                = "${var.project}-${var.env}-vnet"
  resource_group_name = azurerm_resource_group.digitrans.name
  location            = azurerm_resource_group.digitrans.location
  address_space       = ["10.0.0.0/16"]
  tags                = local.common_tags
}

resource "azurerm_subnet" "public" {
  name                 = "public-subnet"
  resource_group_name  = azurerm_resource_group.digitrans.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.1.0/24"]
}

resource "azurerm_subnet" "private_app" {
  name                 = "private-app-subnet"
  resource_group_name  = azurerm_resource_group.digitrans.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.2.0/24"]
}

resource "azurerm_subnet" "private_db" {
  name                 = "private-db-subnet"
  resource_group_name  = azurerm_resource_group.digitrans.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.3.0/24"]
}

# Network Security Group – API Gateway public
resource "azurerm_network_security_group" "public" {
  name                = "${var.project}-${var.env}-public-nsg"
  resource_group_name = azurerm_resource_group.digitrans.name
  location            = azurerm_resource_group.digitrans.location

  security_rule {
    name                       = "allow-https"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "deny-http"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  tags = local.common_tags
}

# Network Security Group – App layer (private)
resource "azurerm_network_security_group" "private_app" {
  name                = "${var.project}-${var.env}-app-nsg"
  resource_group_name = azurerm_resource_group.digitrans.name
  location            = azurerm_resource_group.digitrans.location

  security_rule {
    name                       = "allow-from-public"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "8000-8999"
    source_address_prefix      = "10.0.1.0/24"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "deny-internet"
    priority                   = 200
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }

  tags = local.common_tags
}

resource "azurerm_subnet_network_security_group_association" "public" {
  subnet_id                 = azurerm_subnet.public.id
  network_security_group_id = azurerm_network_security_group.public.id
}

resource "azurerm_subnet_network_security_group_association" "private_app" {
  subnet_id                 = azurerm_subnet.private_app.id
  network_security_group_id = azurerm_network_security_group.private_app.id
}

# ------------------------------------------------------------------
# AWS – VPC (South Africa – za-south-1)
# Utilisé pour le module BI & APIs CRM à forte charge
# ------------------------------------------------------------------
resource "aws_vpc" "bi_vpc" {
  cidr_block           = "10.1.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = merge(local.common_tags, { Name = "${var.project}-${var.env}-bi-vpc" })
}

resource "aws_subnet" "bi_private_a" {
  vpc_id            = aws_vpc.bi_vpc.id
  cidr_block        = "10.1.1.0/24"
  availability_zone = "${var.aws_region}a"
  tags = merge(local.common_tags, { Name = "bi-private-a" })
}

resource "aws_subnet" "bi_private_b" {
  vpc_id            = aws_vpc.bi_vpc.id
  cidr_block        = "10.1.2.0/24"
  availability_zone = "${var.aws_region}b"
  tags = merge(local.common_tags, { Name = "bi-private-b" })
}

resource "aws_subnet" "bi_public" {
  vpc_id                  = aws_vpc.bi_vpc.id
  cidr_block              = "10.1.10.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = false
  tags = merge(local.common_tags, { Name = "bi-public" })
}

resource "aws_internet_gateway" "bi" {
  vpc_id = aws_vpc.bi_vpc.id
  tags   = merge(local.common_tags, { Name = "${var.project}-bi-igw" })
}

resource "aws_eip" "nat" { domain = "vpc" }

resource "aws_nat_gateway" "bi" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.bi_public.id
  tags          = merge(local.common_tags, { Name = "${var.project}-bi-nat" })
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.bi_vpc.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.bi.id
  }
  tags = merge(local.common_tags, { Name = "private-rt" })
}

resource "aws_route_table_association" "a" {
  subnet_id      = aws_subnet.bi_private_a.id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "b" {
  subnet_id      = aws_subnet.bi_private_b.id
  route_table_id = aws_route_table.private.id
}

# ------------------------------------------------------------------
# Outputs
# ------------------------------------------------------------------
output "azure_vnet_id"         { value = azurerm_virtual_network.main.id }
output "azure_public_subnet"   { value = azurerm_subnet.public.id }
output "azure_app_subnet"      { value = azurerm_subnet.private_app.id }
output "azure_db_subnet"       { value = azurerm_subnet.private_db.id }
output "aws_vpc_id"            { value = aws_vpc.bi_vpc.id }
output "aws_private_subnets"   { value = [aws_subnet.bi_private_a.id, aws_subnet.bi_private_b.id] }
output "resource_group_name"   { value = azurerm_resource_group.digitrans.name }
output "resource_group_location" { value = azurerm_resource_group.digitrans.location }

locals {
  common_tags = {
    Project     = var.project
    Environment = var.env
    ManagedBy   = "Terraform"
    Owner       = "CAMTECH-SOLUTIONS"
    Client      = "AGROCAM"
  }
}
