variable "project"                      {}
variable "env"                          {}
variable "resource_group_name"          {}
variable "resource_group_location"      {}
variable "app_subnet_id"                {}
variable "aws_private_subnets"          { type = list(string) }
variable "aws_kms_key_arn"              {}
variable "redis_backup_storage_connection" { sensitive = true }
