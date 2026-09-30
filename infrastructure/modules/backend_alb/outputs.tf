output "dns_name" {
  description = "Public DNS name of the backend load balancer."
  value       = aws_lb.this.dns_name
}

output "security_group_id" {
  description = "Security group attached to the backend load balancer."
  value       = aws_security_group.alb.id
}

output "target_group_arn" {
  description = "Target group used by the backend ECS service."
  value       = aws_lb_target_group.backend.arn
}

output "listener_arn" {
  description = "HTTP listener ARN."
  value       = aws_lb_listener.http.arn
}
