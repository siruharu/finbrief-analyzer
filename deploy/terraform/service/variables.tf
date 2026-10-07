# region 과 platform 은 `make tf-*` 가 deploy/ecs/deploy.env 에서 읽어 넘긴다.
# 배포 스크립트와 같은 값을 보게 하기 위해서다 — 여기 기본값을 따로 고치지 않는다.
variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "platform" {
  description = "붙을 플랫폼 이름 (= ECS 클러스터 = ALB = 용량 공급자 이름)"
  type        = string
  default     = "apps"
}

variable "name" {
  description = "서비스 이름. ECR 저장소·태스크 패밀리·ECS 서비스가 전부 이 이름을 쓴다."
  type        = string
  default     = "finbrief-analyzer"

  validation {
    condition     = length(var.name) <= 32
    error_message = "ALB 대상 그룹 이름 제한 때문에 32자를 넘을 수 없다."
  }
}

# ── 이중화 ──
variable "desired_count" {
  description = "평소 태스크 수. 2 이상이어야 호스트 하나가 죽어도 서비스가 산다."
  type        = number
  default     = 2
}

variable "max_count" {
  description = "오토스케일 상한"
  type        = number
  default     = 4
}

variable "cpu_target" {
  description = "이 평균 CPU 사용률(%)을 넘으면 태스크를 늘린다"
  type        = number
  default     = 60
}

# ── 컨테이너 ──
variable "container_port" {
  type    = number
  default = 8000
}

# 출발점일 뿐이다. 부하 테스트 후 조정한다.
variable "cpu" {
  description = "CPU 단위 (1024 = 1 vCPU). 예약이지 상한이 아니다."
  type        = number
  default     = 64
}

variable "memory_reservation" {
  description = "배치할 때 호스트에서 잡아 두는 메모리 (MiB)"
  type        = number
  default     = 128
}

variable "memory" {
  description = "넘으면 컨테이너가 죽는 상한 (MiB)"
  type        = number
  default     = 512
}

variable "environment" {
  description = "평문 환경변수. 비밀값은 여기 넣지 않는다."
  type        = map(string)
  default     = {}
}

variable "secrets" {
  description = "환경변수 이름 → SSM Parameter 또는 Secrets Manager ARN"
  type        = map(string)
  default     = {}
}

# ── 라우팅 ──
variable "listener_port" {
  description = "플랫폼 ALB 의 리스너 포트 (platform 출력 listener_port)"
  type        = number
  default     = 443
}

variable "host_headers" {
  description = "이 서비스로 보낼 도메인. 비우면 경로 조건만 쓴다."
  type        = list(string)
  default     = []
}

variable "path_patterns" {
  type    = list(string)
  default = ["/*"]
}

variable "listener_rule_priority" {
  description = "비우면 AWS 가 다음 빈 번호를 준다. 넓은 규칙(/*)은 큰 번호로 뒤에 둔다."
  type        = number
  default     = null
}

variable "health_check_path" {
  type    = string
  default = "/health"
}

variable "health_check_grace_period" {
  description = "기동 직후 헬스체크 실패를 봐주는 시간(초). 기동이 느린 런타임일수록 길게."
  type        = number
  default     = 20
}

variable "route53_zone_id" {
  description = "주면 host_headers 의 각 도메인을 ALB 로 향하는 레코드로 만든다"
  type        = string
  default     = ""
}

# ── 릴리스 ──
variable "image_tag" {
  description = "terraform 이 태스크 정의를 만들 때 쓰는 태그. 이후 버전은 릴리스 워크플로가 갈아 끼운다."
  type        = string
  default     = "latest"
}

variable "ci_role_name" {
  description = "CI 가 쓰는 IAM 역할 이름 (예: Gitea 러너 EC2 의 인스턴스 역할). 주면 배포 정책을 붙인다."
  type        = string
  default     = ""
}

# ── 관측 ──
variable "alarm_topic_arn" {
  description = "알람을 보낼 SNS 토픽. 비우면 알람은 만들되 알림은 가지 않는다."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  type    = number
  default = 30
}
