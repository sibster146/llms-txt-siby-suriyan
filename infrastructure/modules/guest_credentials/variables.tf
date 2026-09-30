variable "environment" {
  description = "Deployment environment used in resource names."
  type        = string
}

variable "project_name" {
  description = "Project name used after the environment prefix."
  type        = string
}

variable "recovery_window_in_days" {
  description = "Number of days Secrets Manager retains a deleted secret."
  type        = number
  default     = 7
}

variable "tags" {
  description = "Additional tags applied to the secret."
  type        = map(string)
  default     = {}
}
