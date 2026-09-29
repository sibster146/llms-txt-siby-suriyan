output "function_name" {
  description = "Web crawler Lambda function name."
  value       = aws_lambda_function.this.function_name
}

output "function_arn" {
  description = "Web crawler Lambda function ARN."
  value       = aws_lambda_function.this.arn
}

output "execution_role_arn" {
  description = "IAM role used by the web crawler Lambda."
  value       = aws_iam_role.this.arn
}
