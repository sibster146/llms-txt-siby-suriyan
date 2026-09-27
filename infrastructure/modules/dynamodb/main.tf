locals {
  resource_prefix = "${var.environment}_${var.project_name}"
  common_tags = merge(var.tags, {
    Environment = var.environment
    ManagedBy   = "terraform"
    Project     = var.project_name
  })
}

resource "aws_dynamodb_table" "sites" {
  name         = "${local.resource_prefix}_sites"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "site_id"

  deletion_protection_enabled = var.deletion_protection

  attribute {
    name = "site_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.point_in_time_recovery
  }

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}_sites"
  })
}

resource "aws_dynamodb_table" "user_sites" {
  name         = "${local.resource_prefix}_user_sites"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "site_id"

  deletion_protection_enabled = var.deletion_protection

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "site_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.point_in_time_recovery
  }

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}_user_sites"
  })
}

resource "aws_dynamodb_table" "crawl_runs" {
  name         = "${local.resource_prefix}_crawl_runs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "site_id"
  range_key    = "crawl_run_id"

  deletion_protection_enabled = var.deletion_protection

  attribute {
    name = "site_id"
    type = "S"
  }

  attribute {
    name = "crawl_run_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.point_in_time_recovery
  }

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}_crawl_runs"
  })
}

resource "aws_dynamodb_table" "crawl_pages" {
  name         = "${local.resource_prefix}_crawl_pages"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "crawl_run_id"
  range_key    = "canonical_url_hash"

  deletion_protection_enabled = var.deletion_protection

  attribute {
    name = "crawl_run_id"
    type = "S"
  }

  attribute {
    name = "canonical_url_hash"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.point_in_time_recovery
  }

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}_crawl_pages"
  })
}

resource "aws_dynamodb_table" "llms_txt_versions" {
  name         = "${local.resource_prefix}_llms_txt_versions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "site_id"
  range_key    = "version_id"

  deletion_protection_enabled = var.deletion_protection

  attribute {
    name = "site_id"
    type = "S"
  }

  attribute {
    name = "version_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.point_in_time_recovery
  }

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}_llms_txt_versions"
  })
}
