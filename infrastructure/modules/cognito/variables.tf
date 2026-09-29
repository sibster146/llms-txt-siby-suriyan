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

variable "aws_region" {
  description = "AWS region containing the Cognito user pool."
  type        = string
}

variable "deletion_protection" {
  description = "Whether Cognito deletion protection is enabled."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Additional tags applied to Cognito resources."
  type        = map(string)
  default     = {}
}
