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

variable "sites_table_name" {
  type        = string
  description = "DynamoDB sites table name."
}

variable "sites_table_arn" {
  type        = string
  description = "DynamoDB sites table ARN."
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
  description = "Maximum actual page processing attempts, independent of SQS delivery count."
  default     = 2
}

variable "memory_size" {
  type        = number
  description = "Lambda memory allocation in MB."
  default     = 512
}

variable "timeout_seconds" {
  type        = number
  description = "Lambda invocation timeout."
  default     = 120
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
variable "crawl_dlq_arn" {
  type        = string
  description = "Crawl dead-letter queue consumed to finalize abandoned pages."
}

variable "maximum_concurrency" {
  type        = number
  default     = 3
  description = "Maximum concurrent invocations from the crawl queue."
}

variable "crawl_queue_url" {
  type        = string
  description = "Crawl queue URL."
}

variable "crawl_dlq_url" {
  type        = string
  description = "Crawl DLQ URL."
}

variable "retry_delay_seconds" {
  type        = number
  description = "Delay after a caught retryable failure."
  default     = 30
}

variable "max_depth" {
  type        = number
  description = "Maximum link depth."
  default     = 2
}

variable "max_discovered_pages" {
  type        = number
  description = "Maximum pages per run including root."
  default     = 500
}

variable "max_links_per_page" {
  type        = number
  description = "Maximum links extracted per page."
  default     = 1000
}

variable "parser_version" {
  type        = string
  description = "Parsed content schema version."
  default     = "v2"
}
