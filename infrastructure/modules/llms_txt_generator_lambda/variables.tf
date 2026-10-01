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

variable "llm_txt_queue_arn" {
  description = "ARN of the queue that triggers generation."
  type        = string
}

variable "llm_txt_queue_url" {
  description = "URL of the queue used to schedule generator retries."
  type        = string
}

variable "llm_txt_dlq_arn" {
  description = "ARN of the generator dead-letter queue."
  type        = string
}

variable "llm_txt_dlq_url" {
  description = "URL of the generator dead-letter queue."
  type        = string
}

variable "max_attempts" {
  description = "Total generator attempts before a message is sent to the dead-letter queue."
  type        = number
  default     = 4

  validation {
    condition     = var.max_attempts >= 1
    error_message = "max_attempts must be at least 1."
  }
}

variable "retry_delay_seconds" {
  description = "Delay before a failed generator message is retried."
  type        = number
  default     = 30

  validation {
    condition     = var.retry_delay_seconds >= 0 && var.retry_delay_seconds <= 900
    error_message = "retry_delay_seconds must be between 0 and 900."
  }
}

variable "sites_table_name" {
  description = "DynamoDB sites table name."
  type        = string
}

variable "sites_table_arn" {
  description = "DynamoDB sites table ARN."
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

variable "crawl_runs_table_name" {
  description = "DynamoDB crawl-runs table name."
  type        = string
}

variable "crawl_runs_table_arn" {
  description = "DynamoDB crawl-runs table ARN."
  type        = string
}

variable "llm_txt_versions_table_name" {
  description = "DynamoDB llms.txt versions table name."
  type        = string
}

variable "llm_txt_versions_table_arn" {
  description = "DynamoDB llms.txt versions table ARN."
  type        = string
}

variable "application_bucket_name" {
  description = "S3 bucket containing parsed content and generated files."
  type        = string
}

variable "application_bucket_arn" {
  description = "ARN of the application S3 bucket."
  type        = string
}

variable "bedrock_model_id" {
  description = "Bedrock model ID used to create the llms.txt plan."
  type        = string
  default     = "us.moonshotai.kimi-k3"
}

variable "bedrock_model_arns" {
  description = "Bedrock inference profile and routed model ARNs the Lambda may invoke."
  type        = list(string)
}

variable "max_input_pages" {
  description = "Maximum parsed pages supplied to the generator."
  type        = number
  default     = 500

  validation {
    condition     = var.max_input_pages >= 1
    error_message = "max_input_pages must be at least 1."
  }
}

variable "max_output_links" {
  description = "Maximum curated links allowed in the generated llms.txt."
  type        = number
  default     = 16

  validation {
    condition     = var.max_output_links >= 1
    error_message = "max_output_links must be at least 1."
  }
}

variable "max_excerpt_chars" {
  description = "Maximum parsed-content characters included per page."
  type        = number
  default     = 1000

  validation {
    condition     = var.max_excerpt_chars >= 1
    error_message = "max_excerpt_chars must be at least 1."
  }
}

variable "max_model_tokens" {
  description = "Maximum tokens Bedrock may return."
  type        = number
  default     = 4000

  validation {
    condition     = var.max_model_tokens >= 1
    error_message = "max_model_tokens must be at least 1."
  }
}

variable "memory_size" {
  description = "Lambda memory allocation in MB."
  type        = number
  default     = 1024
}

variable "maximum_concurrency" {
  description = "Maximum concurrent generator invocations started by SQS."
  type        = number
  default     = 2

  validation {
    condition     = var.maximum_concurrency >= 2 && var.maximum_concurrency <= 1000
    error_message = "maximum_concurrency must be between 2 and 1000."
  }
}

variable "timeout_seconds" {
  description = "Lambda invocation timeout."
  type        = number
  default     = 300

  validation {
    condition     = var.timeout_seconds >= 30 && var.timeout_seconds <= 900
    error_message = "timeout_seconds must be between 30 and 900."
  }
}

variable "log_retention_days" {
  description = "CloudWatch log retention."
  type        = number
  default     = 14
}

variable "tags" {
  description = "Additional resource tags."
  type        = map(string)
  default     = {}
}
