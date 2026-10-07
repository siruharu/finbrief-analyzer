data "aws_iam_policy_document" "tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# ── 실행 역할: ECS 가 이미지를 받고, 로그를 쓰고, 비밀값을 주입할 때 쓴다 ──
resource "aws_iam_role" "execution" {
  name               = "${var.name}-exec"
  assume_role_policy = data.aws_iam_policy_document.tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

locals {
  # Secrets Manager ARN 뒤에 붙는 `:json-key::` 는 IAM 리소스가 아니므로 잘라낸다
  secret_arns = distinct([for arn in values(var.secrets) : join(":", slice(split(":", arn), 0, 7))])
}

data "aws_iam_policy_document" "read_secrets" {
  count = length(local.secret_arns) > 0 ? 1 : 0

  statement {
    actions   = ["ssm:GetParameters", "secretsmanager:GetSecretValue"]
    resources = local.secret_arns
  }
}

resource "aws_iam_role_policy" "read_secrets" {
  count = length(local.secret_arns) > 0 ? 1 : 0

  name   = "read-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.read_secrets[0].json
}

# ── 태스크 역할: 앱 코드가 AWS API 를 부를 때 쓴다. 필요한 권한만 여기에 붙인다 ──
resource "aws_iam_role" "task" {
  name               = "${var.name}-task"
  assume_role_policy = data.aws_iam_policy_document.tasks_assume.json
}

# ── 배포 정책: CI 가 이 서비스 하나만 배포할 수 있는 최소 권한 ──
# ci_role_name 을 주면 그 역할에 붙인다. 안 주면 출력된 ARN 을 직접 붙인다.
data "aws_iam_policy_document" "deploy" {
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "EcrPush"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:DescribeImages",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
    ]
    resources = [aws_ecr_repository.app.arn]
  }

  # 태스크 정의 API 는 리소스 단위 제한을 지원하지 않는다
  statement {
    sid       = "TaskDefinition"
    actions   = ["ecs:DescribeTaskDefinition", "ecs:RegisterTaskDefinition"]
    resources = ["*"]
  }

  statement {
    sid       = "Service"
    actions   = ["ecs:DescribeServices", "ecs:UpdateService"]
    resources = [aws_ecs_service.app.id]
  }

  statement {
    sid       = "PassRoles"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.execution.arn, aws_iam_role.task.arn]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_policy" "deploy" {
  name   = "${var.name}-deploy"
  policy = data.aws_iam_policy_document.deploy.json
}

resource "aws_iam_role_policy_attachment" "ci_deploy" {
  count = var.ci_role_name == "" ? 0 : 1

  role       = var.ci_role_name
  policy_arn = aws_iam_policy.deploy.arn
}
