variable "environment" {
  description = "Deployment environment used in resource names."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be either dev or prod."
  }
}

variable "project_name" {
  description = "Project name used after the environment prefix."
  type        = string
  default     = "llms_txt"
}

variable "image_uri" {
  type        = string
  description = "Immutable ECR image URI deployed to the Lambda."
}

variable "parse_queue_arn" {
  type        = string
  description = "ARN of the queue that triggers the parser."
}

variable "crawl_queue_arn" {
  type        = string
  description = "ARN of the crawler queue."
}

variable "crawl_queue_url" {
  type        = string
  description = "URL of the crawler queue."
}

variable "llm_txt_queue_arn" {
  type        = string
  description = "ARN of the llms.txt generator queue."
}

variable "llm_txt_queue_url" {
  type        = string
  description = "URL of the llms.txt generator queue."
}

variable "crawl_pages_table_name" {
  type        = string
  description = "DynamoDB crawl-pages table name."
}

variable "crawl_pages_table_arn" {
  type        = string
  description = "DynamoDB crawl-pages table ARN."
}

variable "crawl_runs_table_name" {
  type        = string
  description = "DynamoDB crawl-runs table name."
}

variable "crawl_runs_table_arn" {
  type        = string
  description = "DynamoDB crawl-runs table ARN."
}

variable "application_bucket_name" {
  type        = string
  description = "S3 bucket containing raw and parsed page content."
}

variable "application_bucket_arn" {
  type        = string
  description = "ARN of the application S3 bucket."
}

variable "parser_version" {
  type        = string
  description = "Version included in parsed-content S3 keys."
  default     = "v1"
}

variable "max_depth" {
  type        = number
  description = "Maximum same-site link depth."
  default     = 3
}

variable "max_links_per_page" {
  type        = number
  description = "Maximum child links accepted from one page."
  default     = 100
}

variable "max_attempts" {
  type        = number
  description = "Number of parser deliveries before the message reaches its DLQ."
  default     = 5
}

variable "memory_size" {
  type        = number
  description = "Lambda memory allocation in MB."
  default     = 1024
}

variable "timeout_seconds" {
  type        = number
  description = "Lambda invocation timeout."
  default     = 60
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch log retention."
  default     = 14
}

variable "tags" {
  type        = map(string)
  description = "Additional resource tags."
  default     = {}
}
