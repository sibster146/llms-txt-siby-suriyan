module "cognito" {
  source = "../modules/cognito"

  environment         = "dev"
  project_name        = var.project_name
  aws_region          = var.aws_region
  deletion_protection = false
}
