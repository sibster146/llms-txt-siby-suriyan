output "secret_arn" {
  description = "ARN of the guest credentials secret."
  value       = aws_secretsmanager_secret.this.arn
}

output "secret_name" {
  description = "Name of the guest credentials secret."
  value       = aws_secretsmanager_secret.this.name
}
