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
