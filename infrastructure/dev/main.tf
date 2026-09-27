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

  environment  = "dev"
  project_name = var.project_name
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

module "web_crawler_lambda" {
  source = "../modules/web_crawler_lambda"

  environment             = "dev"
  project_name            = var.project_name
  image_uri               = var.web_crawler_image_uri
  crawl_queue_arn         = module.sqs.queue_arns.crawl
  parse_queue_arn         = module.sqs.queue_arns.parse
  parse_queue_url         = module.sqs.queue_urls.parse
  crawl_pages_table_name  = module.dynamodb.table_names.crawl_pages
  crawl_pages_table_arn   = module.dynamodb.table_arns.crawl_pages
  crawl_runs_table_name   = module.dynamodb.table_names.crawl_runs
  crawl_runs_table_arn    = module.dynamodb.table_arns.crawl_runs
  application_bucket_name = module.s3.bucket_name
  application_bucket_arn  = module.s3.bucket_arn
  max_attempts            = 5
  request_timeout_seconds = 10
  max_response_bytes      = 5242880
  user_agent              = "llms-txt-crawler/1.0 (+https://github.com/tryBaskt/llms-txt-siby-suriyan)"
}
