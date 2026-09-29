variable "environment" {
  description = "Deployment environment. This becomes the prefix for named AWS resources."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be either dev or prod."
  }
}

variable "project_name" {
  description = "Project name used after the environment resource prefix."
  type        = string
  default     = "llms_txt"

  validation {
    condition     = can(regex("^[a-z0-9_]+$", var.project_name))
    error_message = "project_name may contain only lowercase letters, numbers, and underscores."
  }
}

variable "deletion_protection" {
  description = "Whether deletion protection is enabled for all DynamoDB tables."
  type        = bool
  default     = true
}

variable "point_in_time_recovery" {
  description = "Whether point-in-time recovery is enabled for all DynamoDB tables."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Additional tags applied to DynamoDB tables."
  type        = map(string)
  default     = {}
}
