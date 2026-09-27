variable "environment" {
  description = "Deployment environment. This becomes the prefix for named AWS resources."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be either dev or prod."
  }
}

variable "project_name" {
  description = "Project name used after the environment resource prefix."
  type        = string
  default     = "llms_txt"

  validation {
    condition     = can(regex("^[a-z0-9_]+$", var.project_name))
    error_message = "project_name may contain only lowercase letters, numbers, and underscores."
  }
}

variable "message_retention_seconds" {
  description = "How long SQS retains unprocessed messages."
  type        = number
  default     = 345600
}

variable "receive_wait_time_seconds" {
  description = "Long-polling duration for queue consumers."
  type        = number
  default     = 20
}

variable "visibility_timeout_seconds" {
  description = "How long a received message remains hidden from other consumers."
  type        = number
  default     = 300
}

variable "max_receive_count" {
  description = "Number of failed receives before a message moves to its dead-letter queue."
  type        = number
  default     = 5
}

variable "tags" {
  description = "Additional tags applied to SQS queues."
  type        = map(string)
  default     = {}
}
