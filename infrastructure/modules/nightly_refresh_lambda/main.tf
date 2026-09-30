locals {
  resource_prefix = "${var.environment}_${var.project_name}"
  function_name   = "${local.resource_prefix}_nightly_refresh"
  schedule_name   = "${local.resource_prefix}_nightly_refresh"
  common_tags = merge(var.tags, {
    Environment = var.environment
    ManagedBy   = "terraform"
    Project     = var.project_name
  })
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.function_name}_role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    sid       = "ReadAndUpdateSites"
    actions   = ["dynamodb:Scan", "dynamodb:UpdateItem"]
    resources = [var.sites_table_arn]
  }

  statement {
    sid = "CreateCrawlRunsAndPages"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
    ]
    resources = [
      var.crawl_runs_table_arn,
      var.crawl_pages_table_arn,
    ]
  }

  statement {
    sid       = "QueueRootCrawls"
    actions   = ["sqs:SendMessage"]
    resources = [var.crawl_queue_arn]
  }
}

resource "aws_iam_role_policy" "lambda_permissions" {
  name   = "${local.function_name}_permissions"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_lambda_function" "this" {
  function_name = local.function_name
  description   = "Queues nightly crawl runs for every registered site."
  package_type  = "Image"
  image_uri     = var.image_uri
  role          = aws_iam_role.lambda.arn
  architectures = ["x86_64"]
  memory_size   = var.memory_size
  timeout       = var.timeout_seconds

  environment {
    variables = {
      CRAWL_PAGES_TABLE = var.crawl_pages_table_name
      CRAWL_QUEUE_URL   = var.crawl_queue_url
      CRAWL_RUNS_TABLE  = var.crawl_runs_table_name
      SITES_TABLE       = var.sites_table_name
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.this,
    aws_iam_role_policy.lambda_permissions,
    aws_iam_role_policy_attachment.logs,
  ]

  tags = merge(local.common_tags, {
    Name = local.function_name
  })
}

data "aws_iam_policy_document" "scheduler_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.schedule_name}_scheduler_role"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "scheduler_permissions" {
  statement {
    sid       = "InvokeNightlyRefresh"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.this.arn]
  }
}

resource "aws_iam_role_policy" "scheduler_permissions" {
  name   = "${local.schedule_name}_scheduler_permissions"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler_permissions.json
}

resource "aws_scheduler_schedule" "this" {
  name                         = local.schedule_name
  description                  = "Refresh every registered website on the configured daily schedule."
  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = var.schedule_timezone
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.this.arn
    role_arn = aws_iam_role.scheduler.arn
    input = replace(replace(jsonencode({
      action         = "nightly_refresh"
      attempt_number = "<aws.scheduler.attempt-number>"
      execution_id   = "<aws.scheduler.execution-id>"
      scheduled_time = "<aws.scheduler.scheduled-time>"
    }), "\\u003c", "<"), "\\u003e", ">")

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 3
    }
  }
}
