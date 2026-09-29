locals {
  resource_prefix = "${var.environment}_${var.project_name}"
  function_name   = "${local.resource_prefix}_html_parser"
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
    sid = "ConsumeParseQueue"
    actions = [
      "sqs:ChangeMessageVisibility",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ReceiveMessage",
    ]
    resources = [var.parse_queue_arn]
  }

  statement {
    sid       = "PublishWorkflowMessages"
    actions   = ["sqs:SendMessage"]
    resources = [var.crawl_queue_arn, var.llm_txt_queue_arn]
  }

  statement {
    sid = "ManageCrawlPages"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:Query",
      "dynamodb:UpdateItem",
    ]
    resources = [var.crawl_pages_table_arn]
  }

  statement {
    sid       = "UpdateCrawlProgress"
    actions   = ["dynamodb:UpdateItem"]
    resources = [var.crawl_runs_table_arn]
  }

  statement {
    sid     = "ReadRawAndManageParsedContent"
    actions = ["s3:GetObject"]
    resources = [
      "${var.application_bucket_arn}/raw/*",
      "${var.application_bucket_arn}/parsed/*",
    ]
  }

  statement {
    sid       = "WriteParsedContent"
    actions   = ["s3:PutObject"]
    resources = ["${var.application_bucket_arn}/parsed/*"]
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
  description   = "Extracts page content and queues same-site links for crawling."
  package_type  = "Image"
  image_uri     = var.image_uri
  role          = aws_iam_role.this.arn
  architectures = ["x86_64"]
  memory_size   = var.memory_size
  timeout       = var.timeout_seconds

  environment {
    variables = {
      APPLICATION_S3_BUCKET       = var.application_bucket_name
      CRAWL_PAGES_TABLE           = var.crawl_pages_table_name
      CRAWL_RUNS_TABLE            = var.crawl_runs_table_name
      CRAWL_QUEUE_URL             = var.crawl_queue_url
      LLM_TXT_QUEUE_URL           = var.llm_txt_queue_url
      PARSER_MAX_ATTEMPTS         = tostring(var.max_attempts)
      PARSER_RETRY_DELAY_SECONDS  = tostring(var.retry_delay_seconds)
      PARSE_QUEUE_URL             = var.parse_queue_url
      PARSER_MAX_DEPTH            = tostring(var.max_depth)
      PARSER_MAX_DISCOVERED_PAGES = tostring(var.max_discovered_pages)
      PARSER_MAX_LINKS_PER_PAGE   = tostring(var.max_links_per_page)
      PARSER_VERSION              = var.parser_version
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

resource "aws_lambda_event_source_mapping" "parse_queue" {
  event_source_arn        = var.parse_queue_arn
  function_name           = aws_lambda_function.this.arn
  enabled                 = true
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = var.maximum_concurrency
  }
}
