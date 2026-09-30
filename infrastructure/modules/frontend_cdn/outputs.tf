output "bucket_name" {
  description = "Private S3 bucket containing the compiled frontend."
  value       = aws_s3_bucket.frontend.id
}

output "distribution_id" {
  description = "CloudFront distribution ID used for cache invalidations."
  value       = aws_cloudfront_distribution.this.id
}

output "distribution_domain_name" {
  description = "AWS-provided hostname for the production application."
  value       = aws_cloudfront_distribution.this.domain_name
}

output "application_url" {
  description = "HTTPS URL for the production application."
  value       = "https://${aws_cloudfront_distribution.this.domain_name}"
}
