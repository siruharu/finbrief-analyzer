# VPC. vpc_id 를 주면 이미 있는 것을 쓰고, 비우면 여기서 만든다.
#
#   VPC 10.0.0.0/16
#   ├ 퍼블릭  10.0.0.0/24 (AZ-a) · 10.0.3.0/24 (AZ-c)   ALB · NAT
#   └ 프라이빗 10.0.1.0/24 (AZ-a) · 10.0.2.0/24 (AZ-c)   ECS 호스트
#
# ALB 는 AZ 2개가 필수라 퍼블릭 서브넷도 2개다.
# 프라이빗의 호스트가 ECR 에서 이미지를 받고 ECS 에 등록하려면 나가는 길(NAT)이 있어야 한다.

locals {
  create_vpc = var.vpc_id == ""

  vpc_id             = local.create_vpc ? aws_vpc.this[0].id : var.vpc_id
  private_subnet_ids = local.create_vpc ? aws_subnet.private[*].id : var.private_subnet_ids
  alb_subnet_ids     = local.create_vpc ? aws_subnet.public[*].id : var.alb_subnet_ids

  # NAT 를 AZ 마다 둘지(비용 2배, AZ 장애에도 아웃바운드 유지) 하나만 둘지
  nat_count = local.create_vpc ? (var.nat_per_az ? length(var.azs) : 1) : 0
}

resource "aws_vpc" "this" {
  count = local.create_vpc ? 1 : 0

  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = var.name }
}

resource "aws_internet_gateway" "this" {
  count = local.create_vpc ? 1 : 0

  vpc_id = aws_vpc.this[0].id

  tags = { Name = var.name }
}

resource "aws_subnet" "public" {
  count = local.create_vpc ? length(var.azs) : 0

  vpc_id                  = aws_vpc.this[0].id
  availability_zone       = var.azs[count.index]
  cidr_block              = var.public_subnet_cidrs[count.index]
  map_public_ip_on_launch = true

  tags = { Name = "${var.name}-public-${var.azs[count.index]}" }
}

resource "aws_subnet" "private" {
  count = local.create_vpc ? length(var.azs) : 0

  vpc_id            = aws_vpc.this[0].id
  availability_zone = var.azs[count.index]
  cidr_block        = var.private_subnet_cidrs[count.index]

  tags = { Name = "${var.name}-private-${var.azs[count.index]}" }
}

resource "aws_route_table" "public" {
  count = local.create_vpc ? 1 : 0

  vpc_id = aws_vpc.this[0].id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this[0].id
  }

  tags = { Name = "${var.name}-public" }
}

resource "aws_route_table_association" "public" {
  count = local.create_vpc ? length(var.azs) : 0

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public[0].id
}

resource "aws_eip" "nat" {
  count = local.nat_count

  domain = "vpc"

  tags = { Name = "${var.name}-nat-${count.index}" }
}

resource "aws_nat_gateway" "this" {
  count = local.nat_count

  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = { Name = "${var.name}-${var.azs[count.index]}" }

  depends_on = [aws_internet_gateway.this]
}

resource "aws_route_table" "private" {
  count = local.create_vpc ? length(var.azs) : 0

  vpc_id = aws_vpc.this[0].id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this[var.nat_per_az ? count.index : 0].id
  }

  tags = { Name = "${var.name}-private-${var.azs[count.index]}" }
}

resource "aws_route_table_association" "private" {
  count = local.create_vpc ? length(var.azs) : 0

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}
