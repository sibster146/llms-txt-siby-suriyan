locals {
  resource_prefix = "${var.environment}_${var.project_name}"
  common_tags = merge(var.tags, {
    Environment = var.environment
    ManagedBy   = "terraform"
    Project     = var.project_name
  })
}

resource "aws_secretsmanager_secret" "this" {
  name                    = "${local.resource_prefix}_guest_credentials"
  description             = "Guest account credentials injected into the backend"
  recovery_window_in_days = var.recovery_window_in_days

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}_guest_credentials"
  })
}
