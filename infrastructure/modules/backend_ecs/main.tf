locals {
  resource_prefix = "${var.environment}_${var.project_name}"
  table_resources = flatten([
    for arn in values(var.dynamodb_table_arns) : [arn, "${arn}/index/*"]
  ])
  common_tags = merge(var.tags, {
    Environment = var.environment
    ManagedBy   = "terraform"
    Project     = var.project_name
  })
}

data "aws_iam_policy_document" "ecs_tasks_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${local.resource_prefix}_backend_execution_role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    sid       = "ReadGuestCredentials"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.guest_credentials_secret_arn]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "${local.resource_prefix}_backend_secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

resource "aws_iam_role" "task" {
  name               = "${local.resource_prefix}_backend_task_role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "task" {
  statement {
    sid = "UseApplicationTables"
    actions = [
      "dynamodb:BatchGetItem",
      "dynamodb:BatchWriteItem",
      "dynamodb:DeleteItem",
      "dynamodb:DescribeTable",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:UpdateItem",
    ]
    resources = local.table_resources
  }

  statement {
    sid       = "ListApplicationBucket"
    actions   = ["s3:ListBucket"]
    resources = [var.application_bucket_arn]
  }

  statement {
    sid = "UseApplicationObjects"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = ["${var.application_bucket_arn}/*"]
  }

  statement {
    sid       = "QueueCrawls"
    actions   = ["sqs:SendMessage"]
    resources = [var.crawl_queue_arn]
  }

  statement {
    sid = "ManageApplicationUsers"
    actions = [
      "cognito-idp:AdminCreateUser",
      "cognito-idp:AdminDeleteUser",
      "cognito-idp:AdminInitiateAuth",
      "cognito-idp:AdminSetUserPassword",
    ]
    resources = [var.cognito_user_pool_arn]
  }
}

resource "aws_iam_role_policy" "task" {
  name   = "${local.resource_prefix}_backend_permissions"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${local.resource_prefix}_backend"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_ecs_cluster" "this" {
  name = "${local.resource_prefix}_cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.common_tags
}

resource "aws_security_group" "tasks" {
  name        = "${local.resource_prefix}_backend_tasks"
  description = "Allow the application load balancer to reach FastAPI"
  vpc_id      = var.vpc_id

  ingress {
    description     = "FastAPI from application load balancer"
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [var.load_balancer_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}_backend_tasks"
  })
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${local.resource_prefix}_backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name      = "backend"
      image     = var.image_uri
      essential = true
      portMappings = [
        {
          containerPort = var.container_port
          hostPort      = var.container_port
          protocol      = "tcp"
        }
      ]
      environment = [
        { name = "APPLICATION_S3_BUCKET", value = var.application_bucket_name },
        { name = "AWS_PROFILE_NAME", value = "" },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "COGNITO_APP_CLIENT_ID", value = var.cognito_app_client_id },
        { name = "COGNITO_USER_POOL_ID", value = var.cognito_user_pool_id },
        { name = "CORS_ORIGINS", value = var.application_origin },
        { name = "CRAWL_QUEUE_URL", value = var.crawl_queue_url },
        { name = "ENVIRONMENT", value = var.environment },
        { name = "PROJECT_NAME", value = var.project_name },
      ]
      secrets = [
        {
          name      = "GUEST_EMAIL"
          valueFrom = "${var.guest_credentials_secret_arn}:GUEST_EMAIL::"
        },
        {
          name      = "GUEST_PASSWORD"
          valueFrom = "${var.guest_credentials_secret_arn}:GUEST_PASSWORD::"
        },
      ]
      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:${var.container_port}/health')\""]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 15
      }
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.backend.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "backend"
        }
      }
    }
  ])

  tags = local.common_tags
}

resource "aws_ecs_service" "backend" {
  name            = "${local.resource_prefix}_backend"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  health_check_grace_period_seconds = 60

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    assign_public_ip = true
    security_groups  = [aws_security_group.tasks.id]
    subnets          = var.public_subnet_ids
  }

  load_balancer {
    target_group_arn = var.target_group_arn
    container_name   = "backend"
    container_port   = var.container_port
  }

  tags = local.common_tags
}
