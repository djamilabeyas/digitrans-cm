variable "project"                  { default = "digitrans-cm" }
variable "env"                      { default = "prod" }
variable "resource_group_name"      {}
variable "resource_group_location"  {}
variable "public_subnet_id"         {}
variable "app_subnet_id"            {}
variable "aks_principal_id"         {}
variable "allowed_ip_ranges"        { type = list(string), default = [] }
