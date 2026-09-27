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
