data "aws_caller_identity" "current" {}

locals {
  generator_foundation_model_id = trimprefix(var.generator_model_id, "us.")
  generator_model_regions       = ["us-east-1", "us-east-2", "us-west-2"]
  generator_model_arns = concat(
    ["arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.generator_model_id}"],
    [for region in local.generator_model_regions : "arn:aws:bedrock:${region}::foundation-model/${local.generator_foundation_model_id}"]
  )
}

module "cognito" {
  source = "../modules/cognito"

  environment         = "dev"
  project_name        = var.project_name
  aws_region          = var.aws_region
  deletion_protection = false
}

module "dynamodb" {
  source = "../modules/dynamodb"

  environment            = "dev"
  project_name           = var.project_name
  deletion_protection    = false
  point_in_time_recovery = false
}

module "sqs" {
  source = "../modules/sqs"

  environment                        = "dev"
  project_name                       = var.project_name
  max_receive_count                  = var.parser_max_attempts
  crawl_visibility_timeout_seconds   = 30
  crawl_max_receive_count            = 4
  llm_txt_visibility_timeout_seconds = 1800
  llm_txt_max_receive_count          = 4
}

module "s3" {
  source = "../modules/s3"

  environment   = "dev"
  project_name  = var.project_name
  force_destroy = false
}

module "web_crawler_ecr" {
  source = "../modules/ecr"

  environment     = "dev"
  project_name    = var.project_name
  repository_name = "web_crawler"
}

module "html_parser_ecr" {
  source = "../modules/ecr"

  environment     = "dev"
  project_name    = var.project_name
  repository_name = "html_parser"
}

module "llms_txt_generator_ecr" {
  source = "../modules/ecr"

  environment     = "dev"
  project_name    = var.project_name
  repository_name = "generator"
}

module "nightly_refresh_ecr" {
  source = "../modules/ecr"

  environment     = "dev"
  project_name    = var.project_name
  repository_name = "nightly_refresh"
}

module "web_crawler_lambda" {
  source = "../modules/web_crawler_lambda"

  environment             = "dev"
  project_name            = var.project_name
  image_uri               = var.web_crawler_image_uri
  crawl_queue_arn         = module.sqs.queue_arns.crawl
  parse_queue_arn         = module.sqs.queue_arns.parse
  parse_queue_url         = module.sqs.queue_urls.parse
  llm_txt_queue_arn       = module.sqs.queue_arns.llm_txt
  llm_txt_queue_url       = module.sqs.queue_urls.llm_txt
  crawl_pages_table_name  = module.dynamodb.table_names.crawl_pages
  crawl_pages_table_arn   = module.dynamodb.table_arns.crawl_pages
  crawl_runs_table_name   = module.dynamodb.table_names.crawl_runs
  crawl_runs_table_arn    = module.dynamodb.table_arns.crawl_runs
  sites_table_name        = module.dynamodb.table_names.sites
  sites_table_arn         = module.dynamodb.table_arns.sites
  application_bucket_name = module.s3.bucket_name
  application_bucket_arn  = module.s3.bucket_arn
  max_attempts            = 4
  timeout_seconds         = 25
  request_timeout_seconds = 10
  max_response_bytes      = 5242880
  user_agent              = "llms-txt-crawler/1.0 (+https://github.com/tryBaskt/llms-txt-siby-suriyan)"
}

module "html_parser_lambda" {
  source = "../modules/html_parser_lambda"

  environment             = "dev"
  project_name            = var.project_name
  image_uri               = var.html_parser_image_uri
  parse_queue_arn         = module.sqs.queue_arns.parse
  crawl_queue_arn         = module.sqs.queue_arns.crawl
  crawl_queue_url         = module.sqs.queue_urls.crawl
  llm_txt_queue_arn       = module.sqs.queue_arns.llm_txt
  llm_txt_queue_url       = module.sqs.queue_urls.llm_txt
  crawl_pages_table_name  = module.dynamodb.table_names.crawl_pages
  crawl_pages_table_arn   = module.dynamodb.table_arns.crawl_pages
  crawl_runs_table_name   = module.dynamodb.table_names.crawl_runs
  crawl_runs_table_arn    = module.dynamodb.table_arns.crawl_runs
  application_bucket_name = module.s3.bucket_name
  application_bucket_arn  = module.s3.bucket_arn
  parser_version          = "v1"
  max_attempts            = var.parser_max_attempts
  retry_delay_seconds     = var.parser_retry_delay_seconds
  parse_queue_url         = module.sqs.queue_urls.parse
  max_depth               = var.parser_max_depth
  max_discovered_pages    = var.parser_max_discovered_pages
  max_links_per_page      = var.parser_max_links_per_page
  maximum_concurrency     = var.parser_maximum_concurrency
  memory_size             = var.parser_memory_size
}

module "llms_txt_generator_lambda" {
  source = "../modules/llms_txt_generator_lambda"

  environment                 = "dev"
  project_name                = var.project_name
  image_uri                   = var.llms_txt_generator_image_uri
  llm_txt_queue_arn           = module.sqs.queue_arns.llm_txt
  llm_txt_queue_url           = module.sqs.queue_urls.llm_txt
  llm_txt_dlq_arn             = module.sqs.dead_letter_queue_arns.llm_txt
  llm_txt_dlq_url             = module.sqs.dead_letter_queue_urls.llm_txt
  sites_table_name            = module.dynamodb.table_names.sites
  sites_table_arn             = module.dynamodb.table_arns.sites
  crawl_pages_table_name      = module.dynamodb.table_names.crawl_pages
  crawl_pages_table_arn       = module.dynamodb.table_arns.crawl_pages
  crawl_runs_table_name       = module.dynamodb.table_names.crawl_runs
  crawl_runs_table_arn        = module.dynamodb.table_arns.crawl_runs
  llm_txt_versions_table_name = module.dynamodb.table_names.llms_txt_versions
  llm_txt_versions_table_arn  = module.dynamodb.table_arns.llms_txt_versions
  application_bucket_name     = module.s3.bucket_name
  application_bucket_arn      = module.s3.bucket_arn
  bedrock_model_id            = var.generator_model_id
  bedrock_model_arns          = local.generator_model_arns
  max_input_pages             = var.generator_max_input_pages
  max_output_links            = var.generator_max_output_links
  max_excerpt_chars           = var.generator_max_excerpt_chars
  max_model_tokens            = var.generator_max_model_tokens
  maximum_concurrency         = var.generator_maximum_concurrency
  memory_size                 = var.generator_memory_size
  timeout_seconds             = var.generator_timeout_seconds
}

module "nightly_refresh_lambda" {
  source = "../modules/nightly_refresh_lambda"

  environment            = "dev"
  project_name           = var.project_name
  image_uri              = var.nightly_refresh_image_uri
  sites_table_name       = module.dynamodb.table_names.sites
  sites_table_arn        = module.dynamodb.table_arns.sites
  crawl_runs_table_name  = module.dynamodb.table_names.crawl_runs
  crawl_runs_table_arn   = module.dynamodb.table_arns.crawl_runs
  crawl_pages_table_name = module.dynamodb.table_names.crawl_pages
  crawl_pages_table_arn  = module.dynamodb.table_arns.crawl_pages
  crawl_queue_url        = module.sqs.queue_urls.crawl
  crawl_queue_arn        = module.sqs.queue_arns.crawl
  schedule_expression    = var.nightly_refresh_schedule_expression
  schedule_timezone      = var.nightly_refresh_schedule_timezone
}
