variable "project"                   {}
variable "env"                       {}
variable "resource_group_name"       {}
variable "resource_group_location"   {}
variable "db_subnet_id"              {}
variable "vnet_id"                   {}
variable "tenant_id"                 {}
variable "app_service_principal_id"  {}
variable "db_admin_user"             { sensitive = true }
variable "db_admin_password"         { sensitive = true }
variable "aws_region"                { default = "af-south-1" }
variable "aws_private_subnets"       { type = list(string) }
variable "aws_vpc_id"                {}
variable "aws_kms_key_arn"           {}
variable "bi_db_user"                { sensitive = true }
variable "bi_db_password"            { sensitive = true }
