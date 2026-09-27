locals {
  resource_prefix = "${var.environment}_${var.project_name}"
  function_name   = "${local.resource_prefix}_web_crawler"
  common_tags = merge(var.tags, {
    Environment = var.environment
    ManagedBy   = "terraform"
    Project     = var.project_name
  })
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = "${local.function_name}_role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "permissions" {
  statement {
    sid = "ConsumeCrawlQueue"
    actions = [
      "sqs:ChangeMessageVisibility",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ReceiveMessage",
    ]
    resources = [var.crawl_queue_arn]
  }

  statement {
    sid       = "PublishParseMessages"
    actions   = ["sqs:SendMessage"]
    resources = [var.parse_queue_arn]
  }

  statement {
    sid = "UpdateCrawlPages"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
    ]
    resources = [var.crawl_pages_table_arn]
  }

  statement {
    sid       = "StoreRawHtml"
    actions   = ["s3:PutObject"]
    resources = ["${var.application_bucket_arn}/raw/*"]
  }
}

resource "aws_iam_role_policy" "permissions" {
  name   = "${local.function_name}_permissions"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.permissions.json
}

resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_lambda_function" "this" {
  function_name = local.function_name
  description   = "Safely downloads queued website pages and stores their raw HTML."
  package_type  = "Image"
  image_uri     = var.image_uri
  role          = aws_iam_role.this.arn
  architectures = ["x86_64"]
  memory_size   = var.memory_size
  timeout       = var.timeout_seconds

  environment {
    variables = {
      APPLICATION_S3_BUCKET           = var.application_bucket_name
      CRAWLER_MAX_ATTEMPTS            = tostring(var.max_attempts)
      CRAWLER_MAX_RESPONSE_BYTES      = tostring(var.max_response_bytes)
      CRAWLER_REQUEST_TIMEOUT_SECONDS = tostring(var.request_timeout_seconds)
      CRAWLER_USER_AGENT              = var.user_agent
      CRAWL_PAGES_TABLE               = var.crawl_pages_table_name
      PARSE_QUEUE_URL                 = var.parse_queue_url
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.this,
    aws_iam_role_policy.permissions,
    aws_iam_role_policy_attachment.logs,
  ]

  tags = merge(local.common_tags, {
    Name = local.function_name
  })
}

resource "aws_lambda_event_source_mapping" "crawl_queue" {
  event_source_arn        = var.crawl_queue_arn
  function_name           = aws_lambda_function.this.arn
  enabled                 = true
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]
}
