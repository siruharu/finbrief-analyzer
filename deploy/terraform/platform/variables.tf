variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "name" {
  description = "클러스터·ALB·용량 공급자가 공유하는 이름. 서비스 쪽은 이 이름으로 플랫폼을 찾는다."
  type        = string
  default     = "apps"
}

# ── 네트워크: 이미 있는 VPC 를 쓸 때 (vpc_id 를 비우면 아래 "새로 만들 때" 값으로 만든다) ──
variable "vpc_id" {
  type    = string
  default = ""
}

variable "private_subnet_ids" {
  description = "ECS 호스트가 뜰 서브넷. AZ 가 서로 달라야 호스트 장애·AZ 장애를 견딘다."
  type        = list(string)
  default     = []

  validation {
    condition     = var.vpc_id == "" || length(var.private_subnet_ids) >= 2
    error_message = "서브넷이 2개 이상(서로 다른 AZ)이어야 이중화가 된다."
  }
}

variable "alb_subnet_ids" {
  description = "ALB 가 뜰 서브넷. 외부 공개면 퍼블릭, 내부 전용이면 프라이빗."
  type        = list(string)
  default     = []

  validation {
    condition     = var.vpc_id == "" || length(var.alb_subnet_ids) >= 2
    error_message = "ALB 는 서로 다른 AZ 의 서브넷 2개 이상이 필요하다."
  }
}

# ── 네트워크: 새로 만들 때 ──
variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "azs" {
  type    = list(string)
  default = ["ap-northeast-2a", "ap-northeast-2c"]

  validation {
    condition     = length(var.azs) >= 2
    error_message = "AZ 가 2개 이상이어야 이중화가 된다."
  }
}

variable "public_subnet_cidrs" {
  description = "azs 와 같은 순서·같은 개수"
  type        = list(string)
  default     = ["10.0.0.0/24", "10.0.3.0/24"]
}

variable "private_subnet_cidrs" {
  description = "azs 와 같은 순서·같은 개수"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "nat_per_az" {
  description = "false 면 NAT 하나를 같이 쓴다 (싸다). 그 AZ 가 죽으면 다른 AZ 호스트도 새 이미지를 못 받는다."
  type        = bool
  default     = false
}

# ── 호스트 ──
variable "instance_type" {
  type    = string
  default = "t3.medium"
}

variable "min_size" {
  description = "호스트 최소 대수. 2 미만이면 호스트 하나가 죽을 때 전부 죽는다."
  type        = number
  default     = 2

  validation {
    condition     = var.min_size >= 2
    error_message = "min_size 는 2 이상이어야 한다 — 이 구성의 목적이 호스트 이중화다."
  }
}

variable "max_size" {
  type    = number
  default = 4
}

variable "target_capacity" {
  description = "ECS 가 유지하려는 호스트 사용률(%). 100 미만이면 그만큼 여유 호스트를 미리 띄워 둔다."
  type        = number
  default     = 100
}

# ── ALB ──
variable "alb_internal" {
  type    = bool
  default = false
}

variable "alb_ingress_cidrs" {
  type    = list(string)
  default = ["0.0.0.0/0"]
}

variable "certificate_arn" {
  description = "ACM 인증서 ARN. 비우면 HTTP(80) 리스너만 만든다 — 서비스의 listener_port 도 80 으로 맞춘다."
  type        = string
  default     = ""
}

# ── DB (별도 EC2) ──
variable "db_security_group_id" {
  description = "DB EC2 의 보안 그룹. 주면 ECS 호스트 → DB 포트 인바운드 규칙을 추가한다."
  type        = string
  default     = ""
}

variable "db_port" {
  type    = number
  default = 5432
}
