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

  validation {
    condition     = can(regex("^[a-z0-9_]+$", var.project_name))
    error_message = "project_name may contain only lowercase letters, numbers, and underscores."
  }
}

variable "repository_name" {
  description = "Repository-specific suffix."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9_]+$", var.repository_name))
    error_message = "repository_name may contain only lowercase letters, numbers, and underscores."
  }
}

variable "retained_image_count" {
  description = "Maximum number of tagged and untagged images retained."
  type        = number
  default     = 30
}

variable "image_tag_mutability" {
  description = "Whether an existing image tag can be overwritten."
  type        = string
  default     = "MUTABLE"

  validation {
    condition     = contains(["IMMUTABLE", "MUTABLE"], var.image_tag_mutability)
    error_message = "image_tag_mutability must be IMMUTABLE or MUTABLE."
  }
}

variable "tags" {
  description = "Additional tags applied to the repository."
  type        = map(string)
  default     = {}
}
