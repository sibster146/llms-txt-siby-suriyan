locals {
  resource_prefix = "${var.environment}_${var.project_name}"
  common_tags = merge(var.tags, {
    Environment = var.environment
    ManagedBy   = "terraform"
    Project     = var.project_name
  })
}

resource "aws_sqs_queue" "crawl" {
  name = "${local.resource_prefix}_crawl_sqs"

  message_retention_seconds  = var.message_retention_seconds
  receive_wait_time_seconds  = var.receive_wait_time_seconds
  visibility_timeout_seconds = var.visibility_timeout_seconds
  sqs_managed_sse_enabled    = true

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}_crawl_sqs"
  })
}

resource "aws_sqs_queue" "parse" {
  name = "${local.resource_prefix}_parse_sqs"

  message_retention_seconds  = var.message_retention_seconds
  receive_wait_time_seconds  = var.receive_wait_time_seconds
  visibility_timeout_seconds = var.visibility_timeout_seconds
  sqs_managed_sse_enabled    = true

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}_parse_sqs"
  })
}

resource "aws_sqs_queue" "llm_txt" {
  name = "${local.resource_prefix}_llm_txt_sqs"

  message_retention_seconds  = var.message_retention_seconds
  receive_wait_time_seconds  = var.receive_wait_time_seconds
  visibility_timeout_seconds = var.visibility_timeout_seconds
  sqs_managed_sse_enabled    = true

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}_llm_txt_sqs"
  })
}
