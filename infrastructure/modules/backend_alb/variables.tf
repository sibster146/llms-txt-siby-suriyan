variable "environment" {
  description = "Deployment environment used in resource names."
  type        = string
}

variable "project_name" {
  description = "Project name used after the environment prefix."
  type        = string
}

variable "vpc_id" {
  description = "VPC containing the load balancer."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnets for the load balancer."
  type        = list(string)
}

variable "container_port" {
  description = "Port exposed by the FastAPI container."
  type        = number
  default     = 8000
}

variable "deletion_protection" {
  description = "Whether deletion protection is enabled on the load balancer."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Additional tags applied to load balancer resources."
  type        = map(string)
  default     = {}
}
