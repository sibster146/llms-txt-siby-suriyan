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

variable "parser_max_attempts" {
  description = "Maximum parser deliveries before a message reaches the DLQ."
  type        = number
  default     = 5
}

variable "parser_max_depth" {
  description = "Maximum child-link depth for a crawl run."
  type        = number
  default     = 2
}

variable "parser_max_discovered_pages" {
  description = "Maximum pages discovered in a crawl run, including the root page."
  type        = number
  default     = 1000
}

variable "parser_max_links_per_page" {
  description = "Maximum child links accepted from one parsed page."
  type        = number
  default     = 100
}

variable "parser_maximum_concurrency" {
  description = "Maximum concurrent parser invocations started by SQS."
  type        = number
  default     = 25
}

variable "parser_memory_size" {
  description = "Parser Lambda memory allocation in MB."
  type        = number
  default     = 2048
}
