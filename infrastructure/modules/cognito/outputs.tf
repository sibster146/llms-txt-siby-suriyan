output "user_pool_id" {
  description = "Cognito user pool ID."
  value       = aws_cognito_user_pool.this.id
}

output "user_pool_arn" {
  description = "Cognito user pool ARN."
  value       = aws_cognito_user_pool.this.arn
}

output "web_client_id" {
  description = "Public browser app client ID."
  value       = aws_cognito_user_pool_client.web.id
}

output "issuer" {
  description = "OIDC token issuer used by API authorizers."
  value       = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.this.id}"
}
