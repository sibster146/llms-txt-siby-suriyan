output "queue_names" {
  description = "SQS queue names keyed by workflow stage."
  value = {
    crawl   = aws_sqs_queue.crawl.name
    parse   = aws_sqs_queue.parse.name
    llm_txt = aws_sqs_queue.llm_txt.name
  }
}

output "queue_urls" {
  description = "SQS queue URLs keyed by workflow stage."
  value = {
    crawl   = aws_sqs_queue.crawl.url
    parse   = aws_sqs_queue.parse.url
    llm_txt = aws_sqs_queue.llm_txt.url
  }
}

output "queue_arns" {
  description = "SQS queue ARNs keyed by workflow stage."
  value = {
    crawl   = aws_sqs_queue.crawl.arn
    parse   = aws_sqs_queue.parse.arn
    llm_txt = aws_sqs_queue.llm_txt.arn
  }
}

output "dead_letter_queue_names" {
  description = "Dead-letter queue names keyed by workflow stage."
  value = {
    crawl = aws_sqs_queue.crawl_dlq.name
  }
}

output "dead_letter_queue_arns" {
  description = "Dead-letter queue ARNs keyed by workflow stage."
  value = {
    crawl = aws_sqs_queue.crawl_dlq.arn
  }
}
