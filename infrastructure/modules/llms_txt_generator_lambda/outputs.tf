output "function_name" {
  description = "llms.txt generator Lambda function name."
  value       = aws_lambda_function.this.function_name
}

output "function_arn" {
  description = "llms.txt generator Lambda function ARN."
  value       = aws_lambda_function.this.arn
}

output "execution_role_arn" {
  description = "IAM role used by the llms.txt generator Lambda."
  value       = aws_iam_role.this.arn
}
