variable "aws_region" {
  description = "AWS region for development resources."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used in AWS resource names."
  type        = string
  default     = "llms_txt"
}
