variable "aws_region" {
  description = "AWS region for production resources."
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


variable "llms_txt_generator_image_uri" {
  description = "Commit-tagged ECR image URI for the llms.txt generator Lambda."
  type        = string
}

variable "nightly_refresh_image_uri" {
  description = "Commit-tagged ECR image URI for the nightly refresh Lambda."
  type        = string
}

variable "backend_image_uri" {
  description = "Commit-tagged ECR image URI for the FastAPI backend."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the production application VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "backend_cpu" {
  description = "CPU units assigned to the production FastAPI task."
  type        = number
  default     = 512
}

variable "backend_memory" {
  description = "Memory in MB assigned to the production FastAPI task."
  type        = number
  default     = 1024
}

variable "backend_desired_count" {
  description = "Number of production FastAPI tasks kept running."
  type        = number
  default     = 1
}

variable "nightly_refresh_schedule_expression" {
  description = "EventBridge Scheduler expression for nightly website refreshes."
  type        = string
  default     = "cron(0 2 * * ? *)"
}

variable "nightly_refresh_schedule_timezone" {
  description = "IANA timezone used to evaluate the nightly refresh schedule."
  type        = string
  default     = "America/New_York"
}

variable "crawler_max_attempts" {
  description = "Maximum actual crawl-and-parse attempts per page."
  type        = number
  default     = 2
}

variable "crawler_retry_delay_seconds" {
  description = "Delay before a failed combined-worker message is delivered again."
  type        = number
  default     = 30
}

variable "crawler_max_depth" {
  description = "Maximum child-link depth for a crawl run."
  type        = number
  default     = 2
}

variable "crawler_max_discovered_pages" {
  description = "Maximum pages discovered in a crawl run, including the root page."
  type        = number
  default     = 500
}

variable "crawler_max_links_per_page" {
  description = "Maximum child links accepted from one parsed page."
  type        = number
  default     = 100
}

variable "crawler_maximum_concurrency" {
  description = "Maximum concurrent crawl-and-parse invocations started by SQS."
  type        = number
  default     = 3
}

variable "crawler_memory_size" {
  description = "Combined worker memory allocation in MB."
  type        = number
  default     = 2048
}

variable "crawler_timeout_seconds" {
  description = "Combined crawl-and-parse worker timeout."
  type        = number
  default     = 120
}

variable "generator_model_id" {
  description = "Amazon Bedrock model used to create the llms.txt plan."
  type        = string
  default     = "us.moonshotai.kimi-k3"
}

variable "generator_max_input_pages" {
  description = "Maximum parsed pages supplied to the generator."
  type        = number
  default     = 500
}

variable "generator_max_output_links" {
  description = "Maximum curated links allowed in the generated llms.txt."
  type        = number
  default     = 16
}

variable "generator_max_excerpt_chars" {
  description = "Maximum parsed-content characters supplied per page."
  type        = number
  default     = 1000
}

variable "generator_max_model_tokens" {
  description = "Maximum tokens returned by Amazon Bedrock."
  type        = number
  default     = 4000
}

variable "generator_maximum_concurrency" {
  description = "Maximum concurrent generator invocations started by SQS."
  type        = number
  default     = 2
}

variable "generator_memory_size" {
  description = "Generator Lambda memory allocation in MB."
  type        = number
  default     = 1024
}

variable "generator_timeout_seconds" {
  description = "Generator Lambda timeout in seconds."
  type        = number
  default     = 300
}
