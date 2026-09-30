resource "aws_iam_role" "recovery_scheduler" {
  name = "${local.function_name}_recovery_scheduler"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "scheduler.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "recovery_scheduler" {
  name = "${local.function_name}_recovery"
  role = aws_iam_role.recovery_scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.this.arn
    }]
  })
}

resource "aws_scheduler_schedule" "recovery" {
  name                = "${local.function_name}_recovery"
  schedule_expression = "rate(2 minutes)"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_lambda_function.this.arn
    role_arn = aws_iam_role.recovery_scheduler.arn
    input    = jsonencode({ action = "recover_crawls" })
    retry_policy {
      maximum_event_age_in_seconds = 300
      maximum_retry_attempts       = 2
    }
  }
  depends_on = [aws_iam_role_policy.recovery_scheduler]
}
