output "function_name" {
  description = "HTML parser Lambda function name."
  value       = aws_lambda_function.this.function_name
}

output "function_arn" {
  description = "HTML parser Lambda function ARN."
  value       = aws_lambda_function.this.arn
}

output "execution_role_arn" {
  description = "IAM role used by the HTML parser Lambda."
  value       = aws_iam_role.this.arn
}
