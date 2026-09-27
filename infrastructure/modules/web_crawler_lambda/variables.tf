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
  description = "Immutable ECR image URI deployed to the Lambda."
  type        = string
}

variable "crawl_queue_arn" {
  type        = string
  description = "ARN of the queue that triggers the crawler."
}

variable "parse_queue_arn" {
  type        = string
  description = "ARN of the parser queue."
}

variable "parse_queue_url" {
  type        = string
  description = "URL of the parser queue."
}

variable "crawl_pages_table_name" {
  type        = string
  description = "DynamoDB crawl-pages table name."
}

variable "crawl_pages_table_arn" {
  type        = string
  description = "DynamoDB crawl-pages table ARN."
}

variable "application_bucket_name" {
  type        = string
  description = "S3 bucket used for raw HTML."
}

variable "application_bucket_arn" {
  type        = string
  description = "ARN of the application S3 bucket."
}

variable "user_agent" {
  type        = string
  description = "User-Agent sent by the crawler."
  default     = "llms-txt-crawler/1.0"
}

variable "request_timeout_seconds" {
  type        = number
  description = "Timeout for each robots.txt or page request."
  default     = 10
}

variable "max_response_bytes" {
  type        = number
  description = "Maximum accepted HTML response size."
  default     = 5242880
}

variable "max_attempts" {
  type        = number
  description = "Number of deliveries before SQS moves a message to the dead-letter queue."
  default     = 5
}

variable "memory_size" {
  type        = number
  description = "Lambda memory allocation in MB."
  default     = 512
}

variable "timeout_seconds" {
  type        = number
  description = "Lambda invocation timeout."
  default     = 45
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch log retention period."
  default     = 14
}

variable "tags" {
  description = "Additional tags applied to Lambda resources."
  type        = map(string)
  default     = {}
}
