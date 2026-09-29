locals {
  resource_prefix = "${var.environment}_${var.project_name}"
  function_name   = "${local.resource_prefix}_generator"
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
    sid = "ConsumeGenerationQueue"
    actions = [
      "sqs:ChangeMessageVisibility",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ReceiveMessage",
    ]
    resources = [var.llm_txt_queue_arn]
  }

  statement {
    sid       = "ScheduleGenerationRetry"
    actions   = ["sqs:SendMessage"]
    resources = [var.llm_txt_queue_arn, var.llm_txt_dlq_arn]
  }

  statement {
    sid       = "ReadCrawlPages"
    actions   = ["dynamodb:Query"]
    resources = [var.crawl_pages_table_arn]
  }

  statement {
    sid = "ReadAndUpdateGenerationState"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
    ]
    resources = [
      var.sites_table_arn,
      var.crawl_runs_table_arn,
    ]
  }

  statement {
    sid = "ManageLlmsTxtVersions"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
    ]
    resources = [var.llm_txt_versions_table_arn]
  }

  statement {
    sid       = "ReadParsedContent"
    actions   = ["s3:GetObject"]
    resources = ["${var.application_bucket_arn}/parsed/*"]
  }

  statement {
    sid = "ManageGeneratedLlmsTxt"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = ["${var.application_bucket_arn}/llms-txt/*"]
  }

  statement {
    sid       = "InvokeConfiguredBedrockModel"
    actions   = ["bedrock:InvokeModel"]
    resources = var.bedrock_model_arns
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
  description   = "Generates, validates, and versions llms.txt files from parsed crawl content."
  package_type  = "Image"
  image_uri     = var.image_uri
  role          = aws_iam_role.this.arn
  architectures = ["x86_64"]
  memory_size   = var.memory_size
  timeout       = var.timeout_seconds

  environment {
    variables = {
      APPLICATION_S3_BUCKET         = var.application_bucket_name
      BEDROCK_MODEL_ID              = var.bedrock_model_id
      BEDROCK_READ_TIMEOUT_SECONDS  = tostring(var.timeout_seconds - 10)
      CRAWL_PAGES_TABLE             = var.crawl_pages_table_name
      CRAWL_RUNS_TABLE              = var.crawl_runs_table_name
      GENERATOR_MAX_EXCERPT_CHARS   = tostring(var.max_excerpt_chars)
      GENERATOR_MAX_INPUT_PAGES     = tostring(var.max_input_pages)
      GENERATOR_MAX_MODEL_TOKENS    = tostring(var.max_model_tokens)
      GENERATOR_MAX_OUTPUT_LINKS    = tostring(var.max_output_links)
      GENERATOR_MAX_ATTEMPTS        = tostring(var.max_attempts)
      GENERATOR_RETRY_DELAY_SECONDS = tostring(var.retry_delay_seconds)
      LLM_TXT_DLQ_URL               = var.llm_txt_dlq_url
      LLM_TXT_QUEUE_URL             = var.llm_txt_queue_url
      LLM_TXT_VERSIONS_TABLE        = var.llm_txt_versions_table_name
      SITES_TABLE                   = var.sites_table_name
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

resource "aws_lambda_event_source_mapping" "llm_txt_queue" {
  event_source_arn        = var.llm_txt_queue_arn
  function_name           = aws_lambda_function.this.arn
  enabled                 = true
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = var.maximum_concurrency
  }
}
