output "cluster_name" {
  description = "ECS cluster running the backend."
  value       = aws_ecs_cluster.this.name
}

output "service_name" {
  description = "ECS service running the FastAPI backend."
  value       = aws_ecs_service.backend.name
}

output "task_definition_arn" {
  description = "Active backend task definition ARN."
  value       = aws_ecs_task_definition.backend.arn
}
