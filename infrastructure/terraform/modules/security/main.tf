# ============================================================
# DIGITRANS-CM – Security Module
# WAF, Key Vault, RBAC, Defender for Cloud, AWS GuardDuty
# ============================================================

# ------------------------------------------------------------------
# AZURE KEY VAULT – stockage des secrets (clés API, certs TLS, DB)
# ------------------------------------------------------------------
resource "azurerm_key_vault" "digitrans" {
  name                        = "${var.project}-${var.env}-kv"
  resource_group_name         = var.resource_group_name
  location                    = var.resource_group_location
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  sku_name                    = "premium"       # HSM pour les clés sensibles
  purge_protection_enabled    = true
  soft_delete_retention_days  = 90
  enable_rbac_authorization   = true

  network_acls {
    bypass         = "AzureServices"
    default_action = "Deny"
    ip_rules       = var.allowed_ip_ranges
    virtual_network_subnet_ids = [var.app_subnet_id]
  }

  tags = local.common_tags
}

data "azurerm_client_config" "current" {}

# RBAC – seul le service principal AKS peut lire les secrets
resource "azurerm_role_assignment" "aks_keyvault" {
  scope                = azurerm_key_vault.digitrans.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = var.aks_principal_id
}

# ------------------------------------------------------------------
# AZURE WAF – Application Gateway avec politique WAF v2 OWASP 3.2
# ------------------------------------------------------------------
resource "azurerm_web_application_firewall_policy" "owasp" {
  name                = "${var.project}-${var.env}-waf-policy"
  resource_group_name = var.resource_group_name
  location            = var.resource_group_location

  policy_settings {
    enabled                     = true
    mode                        = "Prevention"
    request_body_check          = true
    file_upload_limit_in_mb     = 10
    max_request_body_size_in_kb = 128
  }

  managed_rules {
    managed_rule_set {
      type    = "OWASP"
      version = "3.2"

      # Désactiver règles créant des faux positifs sur l'API REST
      rule_group_override {
        rule_group_name = "REQUEST-942-APPLICATION-ATTACK-SQLI"
        rule {
          id      = "942440"
          enabled = false   # false positive sur les JSON payloads AGROCAM
          action  = "Log"
        }
      }
    }

    managed_rule_set {
      type    = "Microsoft_BotManagerRuleSet"
      version = "1.0"
    }
  }

  custom_rules {
    name      = "block-non-cm-countries"
    priority  = 5
    rule_type = "MatchRule"
    action    = "Block"

    match_conditions {
      match_variables { variable_name = "RemoteAddr" }
      operator           = "GeoMatch"
      negation_condition = true
      # Autoriser uniquement CM, FR, BE, CH (diaspora AGROCAM)
      match_values = ["CM", "FR", "BE", "CH", "CI", "SN", "GA"]
    }
  }

  tags = local.common_tags
}

resource "azurerm_public_ip" "agw" {
  name                = "${var.project}-${var.env}-agw-pip"
  resource_group_name = var.resource_group_name
  location            = var.resource_group_location
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.common_tags
}

resource "azurerm_application_gateway" "main" {
  name                = "${var.project}-${var.env}-agw"
  resource_group_name = var.resource_group_name
  location            = var.resource_group_location

  sku {
    name     = "WAF_v2"
    tier     = "WAF_v2"
    capacity = 2
  }

  gateway_ip_configuration {
    name      = "agw-ip-config"
    subnet_id = var.public_subnet_id
  }

  frontend_ip_configuration {
    name                 = "frontend-ip"
    public_ip_address_id = azurerm_public_ip.agw.id
  }

  frontend_port {
    name = "https-port"
    port = 443
  }

  ssl_certificate {
    name                = "tls-cert"
    key_vault_secret_id = azurerm_key_vault_certificate.tls.secret_id
  }

  backend_address_pool {
    name = "aks-backend-pool"
  }

  backend_http_settings {
    name                  = "aks-backend-settings"
    cookie_based_affinity = "Disabled"
    port                  = 80
    protocol              = "Http"
    request_timeout       = 30

    probe_name = "health-probe"
  }

  probe {
    name                = "health-probe"
    host                = "10.0.2.10"
    protocol            = "Http"
    path                = "/health"
    interval            = 30
    timeout             = 30
    unhealthy_threshold = 3
  }

  http_listener {
    name                           = "https-listener"
    frontend_ip_configuration_name = "frontend-ip"
    frontend_port_name             = "https-port"
    protocol                       = "Https"
    ssl_certificate_name           = "tls-cert"
  }

  request_routing_rule {
    name                       = "https-rule"
    rule_type                  = "Basic"
    http_listener_name         = "https-listener"
    backend_address_pool_name  = "aks-backend-pool"
    backend_http_settings_name = "aks-backend-settings"
    priority                   = 100
  }

  firewall_policy_id = azurerm_web_application_firewall_policy.owasp.id

  tags = local.common_tags
}

# Certificat TLS géré par Key Vault
resource "azurerm_key_vault_certificate" "tls" {
  name         = "digitrans-tls"
  key_vault_id = azurerm_key_vault.digitrans.id

  certificate_policy {
    issuer_parameters { name = "Self" }
    key_properties {
      exportable = true
      key_size   = 2048
      key_type   = "RSA"
      reuse_key  = true
    }
    lifetime_action {
      action { action_type = "AutoRenew" }
      trigger { days_before_expiry = 30 }
    }
    secret_properties { content_type = "application/x-pkcs12" }
    x509_certificate_properties {
      subject            = "CN=digitrans-cm.agrocam.cm"
      validity_in_months = 12
      key_usage = ["cRLSign", "dataEncipherment", "digitalSignature",
                   "keyAgreement", "keyCertSign", "keyEncipherment"]
    }
  }
}

# ------------------------------------------------------------------
# MICROSOFT DEFENDER FOR CLOUD
# ------------------------------------------------------------------
resource "azurerm_security_center_subscription_pricing" "defender_aks" {
  tier          = "Standard"
  resource_type = "KubernetesService"
}

resource "azurerm_security_center_subscription_pricing" "defender_storage" {
  tier          = "Standard"
  resource_type = "StorageAccounts"
}

resource "azurerm_security_center_subscription_pricing" "defender_keyvault" {
  tier          = "Standard"
  resource_type = "KeyVaults"
}

# ------------------------------------------------------------------
# AWS GuardDuty – Détection des menaces sur le cluster BI
# ------------------------------------------------------------------
resource "aws_guardduty_detector" "bi" {
  enable = true

  datasources {
    s3_logs            { enable = true }
    kubernetes { audit_logs { enable = true } }
    malware_protection {
      scan_ec2_instance_with_findings {
        ebs_volumes { enable = true }
      }
    }
  }

  tags = local.common_tags
}

resource "aws_guardduty_threat_intel_set" "camtech" {
  activate    = true
  detector_id = aws_guardduty_detector.bi.id
  format      = "TXT"
  location    = "s3://${aws_s3_bucket.threat_intel.bucket}/threat-ips.txt"
  name        = "camtech-threat-intel"
}

resource "aws_s3_bucket" "threat_intel" {
  bucket = "${var.project}-${var.env}-threat-intel"
  tags   = local.common_tags
}

resource "aws_s3_bucket_versioning" "threat_intel" {
  bucket = aws_s3_bucket.threat_intel.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "threat_intel" {
  bucket = aws_s3_bucket.threat_intel.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

# ------------------------------------------------------------------
# AWS CloudTrail – Audit log (conformité loi camerounaise 2010/012)
# ------------------------------------------------------------------
resource "aws_cloudtrail" "digitrans" {
  name                          = "${var.project}-${var.env}-trail"
  s3_bucket_name                = aws_s3_bucket.audit_logs.id
  include_global_service_events = true
  is_multi_region_trail         = false
  enable_log_file_validation    = true
  kms_key_id                    = aws_kms_key.audit.arn

  event_selector {
    read_write_type           = "All"
    include_management_events = true

    data_resource {
      type   = "AWS::S3::Object"
      values = ["arn:aws:s3:::"]
    }
  }

  tags = local.common_tags
}

resource "aws_s3_bucket" "audit_logs" {
  bucket        = "${var.project}-${var.env}-audit-logs"
  force_destroy = false
  tags          = local.common_tags
}

resource "aws_s3_bucket_lifecycle_configuration" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id
  rule {
    id     = "retain-7-years"   # conformité réglementaire
    status = "Enabled"
    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = 365
      storage_class = "GLACIER"
    }
    expiration { days = 2555 }  # 7 ans
  }
}

resource "aws_kms_key" "audit" {
  description             = "KMS key for audit log encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = local.common_tags
}

# ------------------------------------------------------------------
# Outputs
# ------------------------------------------------------------------
output "key_vault_id"       { value = azurerm_key_vault.digitrans.id }
output "agw_public_ip"      { value = azurerm_public_ip.agw.ip_address }
output "guardduty_id"       { value = aws_guardduty_detector.bi.id }
output "waf_policy_id"      { value = azurerm_web_application_firewall_policy.owasp.id }
output "audit_bucket"       { value = aws_s3_bucket.audit_logs.id }

locals {
  common_tags = {
    Project     = var.project
    Environment = var.env
    ManagedBy   = "Terraform"
    SecurityTier = "High"
  }
}
