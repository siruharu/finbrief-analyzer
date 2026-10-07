# DNS 와 알람.

resource "aws_route53_record" "app" {
  for_each = var.route53_zone_id == "" ? toset([]) : toset(var.host_headers)

  zone_id = var.route53_zone_id
  name    = each.value
  type    = "A"

  alias {
    name                   = data.aws_lb.platform.dns_name
    zone_id                = data.aws_lb.platform.zone_id
    evaluate_target_health = true
  }
}

locals {
  alarm_actions = var.alarm_topic_arn == "" ? [] : [var.alarm_topic_arn]

  alb_dimensions = {
    LoadBalancer = data.aws_lb.platform.arn_suffix
    TargetGroup  = aws_lb_target_group.app.arn_suffix
  }
}

# 이중화가 깨진 상태 — 서비스는 살아 있지만 한 대만 더 죽으면 끝이다
resource "aws_cloudwatch_metric_alarm" "tasks_below_desired" {
  alarm_name          = "${var.name}-tasks-below-desired"
  alarm_description   = "Running tasks below desired count: redundancy is degraded"
  namespace           = "ECS/ContainerInsights"
  metric_name         = "RunningTaskCount"
  statistic           = "Minimum"
  period              = 60
  evaluation_periods  = 5
  comparison_operator = "LessThanThreshold"
  threshold           = var.desired_count
  treat_missing_data  = "breaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    ClusterName = var.platform
    ServiceName = aws_ecs_service.app.name
  }
}

resource "aws_cloudwatch_metric_alarm" "unhealthy_targets" {
  alarm_name          = "${var.name}-unhealthy-targets"
  alarm_description   = "ALB sees unhealthy targets"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 3
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
  dimensions          = local.alb_dimensions
}

resource "aws_cloudwatch_metric_alarm" "target_5xx" {
  alarm_name          = "${var.name}-5xx"
  alarm_description   = "Application is returning 5xx"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 5
  datapoints_to_alarm = 3
  comparison_operator = "GreaterThanThreshold"
  threshold           = 10
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  dimensions          = local.alb_dimensions
}
