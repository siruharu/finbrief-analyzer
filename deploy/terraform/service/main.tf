# ECS 서비스 하나. 플랫폼(클러스터·ALB)은 이름으로 찾아 붙는다.

data "aws_caller_identity" "current" {}

data "aws_ecs_cluster" "platform" {
  cluster_name = var.platform
}

data "aws_lb" "platform" {
  name = var.platform
}

data "aws_lb_listener" "platform" {
  load_balancer_arn = data.aws_lb.platform.arn
  port              = var.listener_port
}

locals {
  container_name = "app"

  image = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
}

# ── 이미지 저장소 ──
resource "aws_ecr_repository" "app" {
  name = var.name

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep the last 30 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 30
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.name}"
  retention_in_days = var.log_retention_days
}

# ── 태스크 정의 ──
resource "aws_ecs_task_definition" "app" {
  family                   = var.name
  requires_compatibilities = ["EC2"]
  # bridge + 동적 호스트 포트 — 롤링 배포 중 같은 호스트에 신·구 태스크가 잠깐 공존할 수 있다
  network_mode       = "bridge"
  execution_role_arn = aws_iam_role.execution.arn
  task_role_arn      = aws_iam_role.task.arn

  # 예전 리비전을 지우지 않는다 — 롤백 대상이다
  skip_destroy = true

  container_definitions = jsonencode([{
    name              = local.container_name
    image             = local.image
    essential         = true
    cpu               = var.cpu
    memory            = var.memory
    memoryReservation = var.memory_reservation
    stopTimeout       = 30

    portMappings = [{
      containerPort = var.container_port
      hostPort      = 0
      protocol      = "tcp"
    }]

    environment = [for k, v in var.environment : { name = k, value = v }]
    secrets     = [for k, v in var.secrets : { name = k, valueFrom = v }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app.name
        awslogs-region        = var.region
        awslogs-stream-prefix = local.container_name
      }
    }
  }])
}

# ── 라우팅 ──
resource "aws_lb_target_group" "app" {
  name        = var.name
  vpc_id      = data.aws_lb.platform.vpc_id
  port        = var.container_port
  protocol    = "HTTP"
  target_type = "instance"

  # 태스크의 stopTimeout(30s) 과 맞춘다 — 빼는 중인 태스크가 처리 중인 요청을 마치게
  deregistration_delay = 30

  health_check {
    path                = var.health_check_path
    matcher             = "200"
    interval            = 10
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener_rule" "app" {
  listener_arn = data.aws_lb_listener.platform.arn
  priority     = var.listener_rule_priority

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }

  dynamic "condition" {
    for_each = length(var.host_headers) > 0 ? [1] : []

    content {
      host_header {
        values = var.host_headers
      }
    }
  }

  condition {
    path_pattern {
      values = var.path_patterns
    }
  }
}

# ── 서비스 ──
resource "aws_ecs_service" "app" {
  name            = var.name
  cluster         = data.aws_ecs_cluster.platform.arn
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.desired_count

  capacity_provider_strategy {
    capacity_provider = var.platform
    weight            = 1
  }

  # 호스트 하나, AZ 하나가 죽어도 살아남게 흩는다.
  # distinctInstance(강제)가 아니라 spread(선호)다 — 강제하면 호스트 수 == 태스크 수일 때
  # 새 태스크를 놓을 자리가 없어 롤링 배포가 멈춘다.
  ordered_placement_strategy {
    type  = "spread"
    field = "attribute:ecs.availability-zone"
  }

  ordered_placement_strategy {
    type  = "spread"
    field = "instanceId"
  }

  # 새 태스크가 ALB 헬스체크를 통과한 뒤에 옛 태스크를 내린다
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = var.health_check_grace_period

  # 새 버전이 못 뜨면 직전 버전으로 되돌린다
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = local.container_name
    container_port   = var.container_port
  }

  lifecycle {
    # task_definition — 릴리스가 새 리비전을 등록해 갈아 끼운다 (deploy/ecs/deploy.sh)
    # desired_count   — 오토스케일이 조절한다
    ignore_changes = [task_definition, desired_count]
  }

  depends_on = [aws_lb_listener_rule.app]
}

# ── 오토스케일 ──
resource "aws_appautoscaling_target" "app" {
  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/${var.platform}/${aws_ecs_service.app.name}"
  min_capacity       = var.desired_count
  max_capacity       = var.max_count
}

resource "aws_appautoscaling_policy" "cpu" {
  name               = "${var.name}-cpu"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.app.service_namespace
  scalable_dimension = aws_appautoscaling_target.app.scalable_dimension
  resource_id        = aws_appautoscaling_target.app.resource_id

  target_tracking_scaling_policy_configuration {
    target_value = var.cpu_target

    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}
