variable "environment" {
  description = "Deployment environment used in resource names."
  type        = string
}

variable "project_name" {
  description = "Project name used after the environment prefix."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the application VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "tags" {
  description = "Additional tags applied to network resources."
  type        = map(string)
  default     = {}
}
