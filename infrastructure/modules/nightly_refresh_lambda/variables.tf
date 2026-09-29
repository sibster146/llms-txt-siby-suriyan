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

variable "sites_table_name" {
  description = "DynamoDB Sites table name."
  type        = string
}

variable "sites_table_arn" {
  description = "DynamoDB Sites table ARN."
  type        = string
}

variable "crawl_runs_table_name" {
  description = "DynamoDB crawl-runs table name."
  type        = string
}

variable "crawl_runs_table_arn" {
  description = "DynamoDB crawl-runs table ARN."
  type        = string
}

variable "crawl_pages_table_name" {
  description = "DynamoDB crawl-pages table name."
  type        = string
}

variable "crawl_pages_table_arn" {
  description = "DynamoDB crawl-pages table ARN."
  type        = string
}

variable "crawl_queue_url" {
  description = "URL of the crawl queue."
  type        = string
}

variable "crawl_queue_arn" {
  description = "ARN of the crawl queue."
  type        = string
}

variable "schedule_expression" {
  description = "EventBridge Scheduler cron expression."
  type        = string
  default     = "cron(0 3 * * ? *)"
}

variable "schedule_timezone" {
  description = "IANA timezone used to evaluate the nightly schedule."
  type        = string
  default     = "America/New_York"
}

variable "memory_size" {
  description = "Lambda memory allocation in MB."
  type        = number
  default     = 256
}

variable "timeout_seconds" {
  description = "Lambda timeout in seconds."
  type        = number
  default     = 60
}

variable "log_retention_days" {
  description = "CloudWatch log retention period."
  type        = number
  default     = 14
}

variable "tags" {
  description = "Additional tags applied to resources."
  type        = map(string)
  default     = {}
}
