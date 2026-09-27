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

variable "web_crawler_image_uri" {
  description = "Commit-tagged ECR image URI for the web crawler Lambda."
  type        = string
}

variable "html_parser_image_uri" {
  description = "Commit-tagged ECR image URI for the HTML parser Lambda."
  type        = string
}
