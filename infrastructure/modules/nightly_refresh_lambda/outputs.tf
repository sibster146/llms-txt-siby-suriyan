output "function_name" {
  description = "Nightly refresh Lambda function name."
  value       = aws_lambda_function.this.function_name
}

output "function_arn" {
  description = "Nightly refresh Lambda function ARN."
  value       = aws_lambda_function.this.arn
}

output "schedule_name" {
  description = "EventBridge Scheduler schedule name."
  value       = aws_scheduler_schedule.this.name
}

output "schedule_arn" {
  description = "EventBridge Scheduler schedule ARN."
  value       = aws_scheduler_schedule.this.arn
}
