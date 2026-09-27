output "cognito_user_pool_id" {
  description = "Development Cognito user pool ID."
  value       = module.cognito.user_pool_id
}

output "cognito_web_client_id" {
  description = "Development Cognito public web client ID."
  value       = module.cognito.web_client_id
}

output "cognito_issuer" {
  description = "Development Cognito OIDC issuer."
  value       = module.cognito.issuer
}

output "dynamodb_table_names" {
  description = "Development DynamoDB table names keyed by data model."
  value       = module.dynamodb.table_names
}

output "dynamodb_table_arns" {
  description = "Development DynamoDB table ARNs keyed by data model."
  value       = module.dynamodb.table_arns
}

output "sqs_queue_names" {
  description = "Development SQS queue names keyed by workflow stage."
  value       = module.sqs.queue_names
}

output "sqs_queue_urls" {
  description = "Development SQS queue URLs keyed by workflow stage."
  value       = module.sqs.queue_urls
}

output "sqs_queue_arns" {
  description = "Development SQS queue ARNs keyed by workflow stage."
  value       = module.sqs.queue_arns
}

output "application_s3_bucket_name" {
  description = "Development application storage bucket name."
  value       = module.s3.bucket_name
}

output "application_s3_bucket_arn" {
  description = "Development application storage bucket ARN."
  value       = module.s3.bucket_arn
}
