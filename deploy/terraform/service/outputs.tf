output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "deploy_policy_arn" {
  description = "CI 가 쓰는 IAM 주체에 이 정책을 붙인다"
  value       = aws_iam_policy.deploy.arn
}

output "task_role_name" {
  description = "앱이 AWS API 를 써야 하면 이 역할에 권한을 붙인다"
  value       = aws_iam_role.task.name
}

output "alb_dns_name" {
  value = data.aws_lb.platform.dns_name
}
