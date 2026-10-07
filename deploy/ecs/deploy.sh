#!/usr/bin/env bash
# ECR 에 있는 이미지 태그 하나를 ECS 서비스에 굴린다 (render task definition + update service).
#
#   ./deploy/ecs/deploy.sh 20260522-1a2b3c4     # 릴리스 워크플로가 부르는 방식
#   ./deploy/ecs/deploy.sh <예전 태그>           # 롤백 — 태그 목록은 make releases
#
# 태스크 정의의 모양(CPU·메모리·환경변수·역할)은 terraform 이 정한다. 여기서는
# 패밀리의 최신 리비전을 가져와 이미지 한 줄만 바꿔 새 리비전으로 등록한다.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

die() { printf 'error: %s\n' "$1" >&2; exit 1; }
info() { printf '==> %s\n' "$1"; }

# deploy.env 를 읽되, 이미 환경에 있는 값이 이긴다
while IFS='=' read -r key value; do
	[[ "$key" =~ ^[A-Z_]+$ ]] || continue
	value="${value%$'\r'}"
	[[ -n "${!key:-}" ]] || export "$key=$value"
done < "$HERE/deploy.env"

for tool in aws jq; do
	command -v "$tool" >/dev/null 2>&1 || die "$tool 이 필요하다"
done
: "${AWS_REGION:?}" "${ECS_CLUSTER:?}" "${ECS_SERVICE:?}"
export AWS_REGION AWS_DEFAULT_REGION="$AWS_REGION"

# latest 같은 움직이는 태그는 받지 않는다 — 태스크 정의에 무엇이 도는지 남지 않고,
# 이미지가 같은 이름이라 ECS 가 바뀐 줄 모른다.
TAG="${1:-}"
[[ -n "$TAG" && "$TAG" != "latest" ]] || die "사용법: deploy.sh <이미지 태그>  (latest 는 안 된다 — make releases 로 태그를 본다)"

if [[ -z "${ECR_REGISTRY:-}" ]]; then
	account="$(aws sts get-caller-identity --query Account --output text)"
	ECR_REGISTRY="$account.dkr.ecr.$AWS_REGION.amazonaws.com"
fi
IMAGE="$ECR_REGISTRY/$ECS_SERVICE:$TAG"

# 없는 이미지를 굴리면 서킷 브레이커가 터질 때까지 몇 분을 기다리게 된다
aws ecr describe-images --repository-name "$ECS_SERVICE" --image-ids "imageTag=$TAG" >/dev/null 2>&1 \
	|| die "ECR 에 이미지가 없다: $IMAGE"

latest="$(aws ecs describe-task-definition --task-definition "$ECS_SERVICE" \
	--query taskDefinition --output json)"
arn="$(jq -r .taskDefinitionArn <<<"$latest")"

if [[ "$(jq -r '.containerDefinitions[] | select(.name == "app") | .image' <<<"$latest")" == "$IMAGE" ]]; then
	info "최신 리비전이 이미 $TAG 다: ${arn##*/}"
else
	# 등록 API 가 받지 않는 읽기 전용 필드를 걷어낸다
	next="$(jq --arg image "$IMAGE" '
		.containerDefinitions |= map(if .name == "app" then .image = $image else . end)
		| del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities,
		      .registeredAt, .registeredBy, .deregisteredAt)
	' <<<"$latest")"
	arn="$(aws ecs register-task-definition --cli-input-json "$next" \
		--query taskDefinition.taskDefinitionArn --output text)"
	info "등록: ${arn##*/} ($IMAGE)"
fi

running() {
	aws ecs describe-services --cluster "$ECS_CLUSTER" --services "$ECS_SERVICE" \
		--query 'services[0].deployments[?status==`PRIMARY`] | [0].taskDefinition' --output text
}

if [[ "$(running)" != "$arn" ]]; then
	aws ecs update-service --cluster "$ECS_CLUSTER" --service "$ECS_SERVICE" \
		--task-definition "$arn" >/dev/null
	info "롤링 시작 — 새 태스크가 ALB 헬스체크를 통과하면 옛 태스크를 내린다"
fi

aws ecs wait services-stable --cluster "$ECS_CLUSTER" --services "$ECS_SERVICE" \
	|| die "서비스가 안정되지 않았다 — aws ecs describe-services 의 events 를 본다"

# 서킷 브레이커가 되돌린 경우에도 서비스는 "안정" 이다. 뭐가 돌고 있는지로 판정한다.
now="$(running)"
[[ "$now" == "$arn" ]] \
	|| die "새 버전이 뜨지 못해 되돌려졌다 (지금: ${now##*/}) — CloudWatch 로그 /ecs/$ECS_SERVICE"

info "배포 완료: $ECS_SERVICE → $TAG (${arn##*/})"
