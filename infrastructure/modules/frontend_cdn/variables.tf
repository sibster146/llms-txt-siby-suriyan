variable "environment" {
  description = "Deployment environment used in resource names."
  type        = string
}

variable "project_name" {
  description = "Project name used after the environment prefix."
  type        = string
}

variable "account_id" {
  description = "AWS account ID used to make the frontend bucket globally unique."
  type        = string
}

variable "backend_dns_name" {
  description = "DNS name of the backend application load balancer."
  type        = string
}

variable "force_destroy" {
  description = "Whether Terraform may delete a non-empty frontend bucket."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Additional tags applied to frontend resources."
  type        = map(string)
  default     = {}
}
