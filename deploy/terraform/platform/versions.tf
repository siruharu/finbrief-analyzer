terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # 상태는 원격에 둔다. 버킷은 미리 만들어 두고 주석을 푼다.
  # backend "s3" {
  #   bucket       = "<tfstate 버킷>"
  #   key          = "ecs/platform/apps.tfstate"
  #   region       = "ap-northeast-2"
  #   use_lockfile = true
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      ManagedBy = "terraform"
      Platform  = var.name
    }
  }
}
