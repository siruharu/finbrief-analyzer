# ECS 클러스터와 그 아래 EC2 호스트 풀.
# 호스트는 ASG 가 여러 AZ 에 걸쳐 띄우고, 죽으면 ASG 가 다시 채운다.

data "aws_ssm_parameter" "ecs_ami" {
  name = "/aws/service/ecs/optimized-ami/amazon-linux-2023/recommended/image_id"
}

resource "aws_ecs_cluster" "this" {
  name = var.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# ── 호스트 IAM ──
data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "host" {
  name               = "${var.name}-ecs-host"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "host_ecs" {
  role       = aws_iam_role.host.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

# SSH 키 없이 Session Manager 로 들어간다
resource "aws_iam_role_policy_attachment" "host_ssm" {
  role       = aws_iam_role.host.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# 호스트 메모리·디스크 지표 (EC2 기본 지표에는 없다)
resource "aws_iam_role_policy_attachment" "host_cloudwatch" {
  role       = aws_iam_role.host.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

resource "aws_iam_instance_profile" "host" {
  name = "${var.name}-ecs-host"
  role = aws_iam_role.host.name
}

# ── 호스트 보안 그룹 ──
resource "aws_security_group" "host" {
  name        = "${var.name}-ecs-host"
  description = "ECS hosts"
  vpc_id      = local.vpc_id

  tags = { Name = "${var.name}-ecs-host" }
}

# bridge 모드의 동적 호스트 포트 범위. ALB 에서만 받는다.
resource "aws_vpc_security_group_ingress_rule" "host_from_alb" {
  security_group_id            = aws_security_group.host.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 32768
  to_port                      = 65535
  description                  = "ALB to dynamic host ports"
}

resource "aws_vpc_security_group_egress_rule" "host_all" {
  security_group_id = aws_security_group.host.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

# DB 는 이중화하지 않는 별도 EC2 다. 앱 호스트에서만 닿게 연다.
resource "aws_vpc_security_group_ingress_rule" "db_from_host" {
  count = var.db_security_group_id == "" ? 0 : 1

  security_group_id            = var.db_security_group_id
  referenced_security_group_id = aws_security_group.host.id
  ip_protocol                  = "tcp"
  from_port                    = var.db_port
  to_port                      = var.db_port
  description                  = "ECS hosts (${var.name})"
}

# ── 호스트 풀 ──
resource "aws_launch_template" "host" {
  name_prefix   = "${var.name}-ecs-"
  image_id      = data.aws_ssm_parameter.ecs_ami.value
  instance_type = var.instance_type

  vpc_security_group_ids = [aws_security_group.host.id]

  iam_instance_profile {
    arn = aws_iam_instance_profile.host.arn
  }

  # IMDSv2 강제, hop 1 — 컨테이너가 호스트의 인스턴스 역할을 훔쳐 쓰지 못한다.
  # 앱 권한은 태스크 역할로 준다.
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  user_data = base64encode(<<-EOT
    #!/bin/bash
    cat >> /etc/ecs/ecs.config <<'CFG'
    ECS_CLUSTER=${var.name}
    ECS_ENABLE_SPOT_INSTANCE_DRAINING=true
    ECS_CONTAINER_STOP_TIMEOUT=30s
    CFG

    # CloudWatch 에이전트 — 실패해도 호스트가 클러스터에 붙는 것을 막지 않는다
    dnf install -y amazon-cloudwatch-agent || exit 0
    cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<'CWA'
    {
      "metrics": {
        "namespace": "${var.name}/ecs-host",
        "append_dimensions": { "InstanceId": "$${aws:InstanceId}" },
        "metrics_collected": {
          "mem": { "measurement": ["mem_used_percent"] },
          "disk": { "measurement": ["used_percent"], "resources": ["/"] }
        }
      }
    }
    CWA
    /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -s \
      -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json || true
  EOT
  )

  tag_specifications {
    resource_type = "instance"
    tags          = { Name = "${var.name}-ecs-host" }
  }

  lifecycle {
    # 새 ECS 최적화 AMI 가 나올 때마다 plan 이 흔들리지 않게. 올릴 때는 taint 한다.
    ignore_changes = [image_id]
  }
}

resource "aws_autoscaling_group" "host" {
  name                = "${var.name}-ecs"
  vpc_zone_identifier = local.private_subnet_ids
  min_size            = var.min_size
  max_size            = var.max_size
  health_check_type   = "EC2"

  launch_template {
    id      = aws_launch_template.host.id
    version = "$Latest"
  }

  # 시작 템플릿이 바뀌면 호스트를 한 대씩 갈아 끼운다
  instance_refresh {
    strategy = "Rolling"

    preferences {
      min_healthy_percentage = 100
      max_healthy_percentage = 150
    }
  }

  tag {
    key                 = "AmazonECSManaged"
    value               = "true"
    propagate_at_launch = true
  }

  lifecycle {
    # 대수는 ECS 용량 공급자가 조절한다
    ignore_changes = [desired_capacity]
  }

  # 나가는 길이 열린 뒤에 호스트를 띄운다 — 아니면 ECS 에 등록하지 못한 채 뜬다
  depends_on = [aws_route_table_association.private]
}

resource "aws_ecs_capacity_provider" "this" {
  name = var.name

  auto_scaling_group_provider {
    auto_scaling_group_arn = aws_autoscaling_group.host.arn
    # 호스트를 내리기 전에 태스크를 먼저 다른 호스트로 옮긴다
    managed_draining = "ENABLED"

    managed_scaling {
      status          = "ENABLED"
      target_capacity = var.target_capacity
    }
  }
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name       = aws_ecs_cluster.this.name
  capacity_providers = [aws_ecs_capacity_provider.this.name]

  default_capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.this.name
    weight            = 1
  }
}
