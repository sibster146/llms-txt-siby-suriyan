locals {
  resource_prefix = "${var.environment}_${var.project_name}"
  common_tags = merge(var.tags, {
    Environment = var.environment
    ManagedBy   = "terraform"
    Project     = var.project_name
  })
}

resource "aws_cognito_user_pool" "this" {
  name                = "${local.resource_prefix}_user_pool"
  deletion_protection = var.deletion_protection ? "ACTIVE" : "INACTIVE"

  username_attributes = ["email"]
  mfa_configuration   = "OPTIONAL"

  username_configuration {
    case_sensitive = false
  }

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  software_token_mfa_configuration {
    enabled = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}_user_pool"
  })

}

resource "aws_cognito_user_pool_client" "web" {
  name         = "${local.resource_prefix}_web_client"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret               = false
  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true
  auth_session_validity         = 3

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  explicit_auth_flows = [
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]

  read_attributes  = ["email", "email_verified"]
  write_attributes = ["email"]
}
