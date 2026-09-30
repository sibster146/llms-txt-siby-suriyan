output "cognito_user_pool_id" {
  description = "Production Cognito user pool ID."
  value       = module.cognito.user_pool_id
}

output "cognito_web_client_id" {
  description = "Production Cognito public web client ID."
  value       = module.cognito.web_client_id
}

output "cognito_issuer" {
  description = "Production Cognito OIDC issuer."
  value       = module.cognito.issuer
}

output "dynamodb_table_names" {
  description = "Production DynamoDB table names keyed by data model."
  value       = module.dynamodb.table_names
}

output "dynamodb_table_arns" {
  description = "Production DynamoDB table ARNs keyed by data model."
  value       = module.dynamodb.table_arns
}

output "sqs_queue_names" {
  description = "Production SQS queue names keyed by workflow stage."
  value       = module.sqs.queue_names
}

output "sqs_queue_urls" {
  description = "Production SQS queue URLs keyed by workflow stage."
  value       = module.sqs.queue_urls
}

output "sqs_queue_arns" {
  description = "Production SQS queue ARNs keyed by workflow stage."
  value       = module.sqs.queue_arns
}

output "application_s3_bucket_name" {
  description = "Production application storage bucket name."
  value       = module.s3.bucket_name
}

output "application_s3_bucket_arn" {
  description = "Production application storage bucket ARN."
  value       = module.s3.bucket_arn
}

output "web_crawler_ecr_repository_url" {
  description = "ECR repository used by the web crawler Lambda."
  value       = module.web_crawler_ecr.repository_url
}

output "web_crawler_lambda_name" {
  description = "Production web crawler Lambda function name."
  value       = module.web_crawler_lambda.function_name
}

output "web_crawler_lambda_arn" {
  description = "Production web crawler Lambda function ARN."
  value       = module.web_crawler_lambda.function_arn
}

output "html_parser_ecr_repository_url" {
  description = "Retained legacy parser repository; no active parser Lambda uses it."
  value       = module.html_parser_ecr.repository_url
}

output "llms_txt_generator_ecr_repository_url" {
  description = "ECR repository used by the llms.txt generator Lambda."
  value       = module.llms_txt_generator_ecr.repository_url
}

output "llms_txt_generator_lambda_name" {
  description = "Production llms.txt generator Lambda function name."
  value       = module.llms_txt_generator_lambda.function_name
}

output "llms_txt_generator_lambda_arn" {
  description = "Production llms.txt generator Lambda function ARN."
  value       = module.llms_txt_generator_lambda.function_arn
}

output "nightly_refresh_ecr_repository_url" {
  description = "ECR repository used by the nightly refresh Lambda."
  value       = module.nightly_refresh_ecr.repository_url
}

output "nightly_refresh_lambda_name" {
  description = "Production nightly refresh Lambda function name."
  value       = module.nightly_refresh_lambda.function_name
}

output "nightly_refresh_schedule_name" {
  description = "Production nightly refresh EventBridge schedule name."
  value       = module.nightly_refresh_lambda.schedule_name
}

output "backend_ecr_repository_url" {
  description = "ECR repository used by the production FastAPI backend."
  value       = module.backend_ecr.repository_url
}

output "backend_ecs_cluster_name" {
  description = "Production ECS cluster name."
  value       = module.backend_ecs.cluster_name
}

output "backend_ecs_service_name" {
  description = "Production ECS service name."
  value       = module.backend_ecs.service_name
}

output "backend_task_definition_arn" {
  description = "Task definition to roll out in the backend deployment job."
  value       = module.backend_ecs.task_definition_arn
}

output "frontend_bucket_name" {
  description = "S3 bucket containing the compiled production frontend."
  value       = module.frontend_cdn.bucket_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID for production cache invalidations."
  value       = module.frontend_cdn.distribution_id
}

output "application_url" {
  description = "AWS-provided HTTPS URL for the production application."
  value       = module.frontend_cdn.application_url
}

output "guest_credentials_secret_name" {
  description = "Secrets Manager secret populated by the production workflow."
  value       = module.guest_credentials.secret_name
}
