locals {
  resource_prefix = "${var.environment}_${var.project_name}"
  common_tags = merge(var.tags, {
    Environment = var.environment
    ManagedBy   = "terraform"
    Project     = var.project_name
  })
}

resource "aws_sqs_queue" "crawl_dlq" {
  name                      = "${local.resource_prefix}_crawl_dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}_crawl_dlq"
  })
}

resource "aws_sqs_queue" "crawl" {
  name = "${local.resource_prefix}_crawl_sqs"

  message_retention_seconds  = var.message_retention_seconds
  receive_wait_time_seconds  = var.receive_wait_time_seconds
  visibility_timeout_seconds = var.crawl_visibility_timeout_seconds
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.crawl_dlq.arn
    maxReceiveCount     = var.crawl_max_receive_count
  })

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}_crawl_sqs"
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "crawl" {
  queue_url = aws_sqs_queue.crawl_dlq.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.crawl.arn]
  })
}

resource "aws_sqs_queue" "parse" {
  name = "${local.resource_prefix}_parse_sqs"

  message_retention_seconds  = var.message_retention_seconds
  receive_wait_time_seconds  = var.receive_wait_time_seconds
  visibility_timeout_seconds = var.visibility_timeout_seconds
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.parse_dlq.arn
    maxReceiveCount     = var.max_receive_count
  })

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}_parse_sqs"
  })
}

resource "aws_sqs_queue" "parse_dlq" {
  name                      = "${local.resource_prefix}_parse_dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}_parse_dlq"
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "parse" {
  queue_url = aws_sqs_queue.parse_dlq.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.parse.arn]
  })
}

resource "aws_sqs_queue" "llm_txt" {
  name = "${local.resource_prefix}_llm_txt_sqs"

  message_retention_seconds  = var.message_retention_seconds
  receive_wait_time_seconds  = var.receive_wait_time_seconds
  visibility_timeout_seconds = var.llm_txt_visibility_timeout_seconds
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.llm_txt_dlq.arn
    maxReceiveCount     = var.llm_txt_max_receive_count
  })

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}_llm_txt_sqs"
  })
}

resource "aws_sqs_queue" "llm_txt_dlq" {
  name                      = "${local.resource_prefix}_llm_txt_dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}_llm_txt_dlq"
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "llm_txt" {
  queue_url = aws_sqs_queue.llm_txt_dlq.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.llm_txt.arn]
  })
}
