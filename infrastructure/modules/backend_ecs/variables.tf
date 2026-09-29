variable "environment" {
  description = "Deployment environment used in resource names."
  type        = string
}

variable "project_name" {
  description = "Project name used after the environment prefix."
  type        = string
}

variable "aws_region" {
  description = "AWS region containing the application resources."
  type        = string
}

variable "image_uri" {
  description = "Commit-tagged ECR image URI for the FastAPI backend."
  type        = string
}

variable "vpc_id" {
  description = "VPC containing the ECS service."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnets used by Fargate tasks."
  type        = list(string)
}

variable "load_balancer_security_group_id" {
  description = "Security group allowed to reach the FastAPI tasks."
  type        = string
}

variable "target_group_arn" {
  description = "Application load balancer target group ARN."
  type        = string
}

variable "application_origin" {
  description = "CloudFront origin allowed by FastAPI CORS middleware."
  type        = string
}

variable "application_bucket_name" {
  description = "Application S3 bucket name."
  type        = string
}

variable "application_bucket_arn" {
  description = "Application S3 bucket ARN."
  type        = string
}

variable "crawl_queue_url" {
  description = "URL of the crawl SQS queue."
  type        = string
}

variable "crawl_queue_arn" {
  description = "ARN of the crawl SQS queue."
  type        = string
}

variable "cognito_user_pool_id" {
  description = "Cognito user pool used by the backend."
  type        = string
}

variable "cognito_user_pool_arn" {
  description = "ARN of the Cognito user pool managed by the backend."
  type        = string
}

variable "cognito_app_client_id" {
  description = "Public Cognito app client used to validate access tokens."
  type        = string
}

variable "guest_credentials_secret_arn" {
  description = "Secrets Manager ARN containing GUEST_EMAIL and GUEST_PASSWORD."
  type        = string
}

variable "dynamodb_table_arns" {
  description = "DynamoDB table ARNs used by the backend."
  type        = map(string)
}

variable "container_port" {
  description = "Port exposed by the FastAPI container."
  type        = number
  default     = 8000
}

variable "cpu" {
  description = "Fargate task CPU units."
  type        = number
  default     = 512
}

variable "memory" {
  description = "Fargate task memory in MB."
  type        = number
  default     = 1024
}

variable "desired_count" {
  description = "Number of FastAPI tasks kept running."
  type        = number
  default     = 1
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the backend."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Additional tags applied to backend resources."
  type        = map(string)
  default     = {}
}
