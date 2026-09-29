output "vpc_id" {
  description = "Application VPC ID."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs used by the load balancer and ECS tasks."
  value       = aws_subnet.public[*].id
}
