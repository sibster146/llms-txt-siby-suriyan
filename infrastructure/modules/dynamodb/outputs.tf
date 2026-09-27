output "table_names" {
  description = "DynamoDB table names keyed by data model."
  value = {
    sites             = aws_dynamodb_table.sites.name
    user_sites        = aws_dynamodb_table.user_sites.name
    crawl_runs        = aws_dynamodb_table.crawl_runs.name
    crawl_pages       = aws_dynamodb_table.crawl_pages.name
    llms_txt_versions = aws_dynamodb_table.llms_txt_versions.name
  }
}

output "table_arns" {
  description = "DynamoDB table ARNs keyed by data model."
  value = {
    sites             = aws_dynamodb_table.sites.arn
    user_sites        = aws_dynamodb_table.user_sites.arn
    crawl_runs        = aws_dynamodb_table.crawl_runs.arn
    crawl_pages       = aws_dynamodb_table.crawl_pages.arn
    llms_txt_versions = aws_dynamodb_table.llms_txt_versions.arn
  }
}
