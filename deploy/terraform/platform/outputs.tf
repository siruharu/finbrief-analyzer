output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "vpc_id" {
  value = local.vpc_id
}

output "private_subnet_ids" {
  value = local.private_subnet_ids
}

output "alb_dns_name" {
  description = "도메인의 CNAME/ALIAS 대상"
  value       = aws_lb.this.dns_name
}

output "listener_port" {
  description = "서비스의 listener_port 에 넣을 값"
  value       = local.tls ? 443 : 80
}

output "host_security_group_id" {
  description = "DB 등 앱이 붙어야 하는 곳의 인바운드에 이 그룹을 허용한다"
  value       = aws_security_group.host.id
}
