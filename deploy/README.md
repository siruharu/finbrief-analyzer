# 배포

AWS ECS on EC2. 호스트 하나가 죽어도 서비스가 죽지 않게 하는 것이 이 구성의 목적이다.

```
compose.yml                     로컬 의존 서비스 (db/cache/mq/mqtt 프로파일)
deploy/ecs/deploy.env           배포 대상 (리전 · 클러스터 · 서비스 이름)
deploy/ecs/deploy.sh            이미지 태그 하나를 ECS 에 롤링
deploy/terraform/service/       이 서비스 — ECR · 태스크 정의 · 서비스 · ALB 규칙 · DNS · 알람 · IAM
deploy/terraform/platform/      공용 — VPC · 클러스터 · EC2 호스트 풀 · ALB (한 번만)
.github/workflows/release.yml   main push/merge → 빌드 → ECR → 롤링
```

## 구조

```
 Gitea ── push/merge ──▶ Actions ── 이미지 ──▶ ECR
                            │                    │ pull
                            └─ update service ─┐ │
                                               ▼ ▼
 Users ─▶ Route 53 ─▶ ALB (퍼블릭 서브넷, 80/443)
                       ├──▶ EC2 호스트 (프라이빗 AZ-a) ── finbrief-analyzer 태스크 #1 :8000
                       └──▶ EC2 호스트 (프라이빗 AZ-c) ── finbrief-analyzer 태스크 #2 :8000
                             └ ASG (min 2 · max 4) 가 호스트를 채운다
                                        │
                                   DB EC2 (단일)  ← 이중화하지 않는다. 아래 참고
```

- **서비스마다 태스크 2개 이상, 호스트·AZ 로 흩는다** (`spread`). 같은 호스트에 2개를
  올리는 것은 호스트 장애에 아무 도움이 안 된다 — 같이 죽는다.
- **호스트가 죽으면** ALB 가 그쪽 타깃을 빼고 남은 태스크가 받는다. ASG 가 호스트를
  다시 채우고 ECS 가 태스크를 다시 올린다. 사람이 할 일은 없다.
- **배포는 무중단이다.** 새 태스크가 ALB 헬스체크를 통과한 뒤에 옛 태스크를 내린다
  (`minimumHealthyPercent 100` / `maximumPercent 200`). 이때만 한 호스트에 신·구가 잠깐 겹친다.
- **새 버전이 못 뜨면** 서킷 브레이커가 직전 버전으로 되돌리고, `deploy.sh` 는 실패로 끝난다.
- **호스트는 프라이빗 서브넷에 있다.** 밖에서 닿는 것은 ALB 뿐이고, 호스트는 ALB 의 보안 그룹에서
  오는 동적 포트만 받는다. 접속은 SSH 가 아니라 Systems Manager(Session Manager)로 한다.

컨테이너는 어느 호스트에서든 `:8000` 로 뜨지만 **호스트 쪽 포트는 ECS 가 빈 번호를 잡는다**
(동적 포트). ALB 에는 ECS 가 알아서 등록한다. 고정하면 한 호스트에 같은 서비스가 하나만
뜰 수 있어 무중단 배포가 막힌다.

호스트 1대가 빠져도 나머지가 전체 부하를 받을 수 있어야 한다. 2대면 각 50%,
3대면 66% 이하로 쓰고 있어야 이중화가 실제로 동작한다.

## 배포 흐름

```
main 에 push / merge
        ↓
Actions ─ 1 checkout
        ─ 2 ECR 로그인
        ─ 3 이미지 빌드 → <계정>.dkr.ecr.ap-northeast-2.amazonaws.com/finbrief-analyzer:20260522-1a2b3c4 (+ :latest)
        ─ 4 태스크 정의 새 리비전 (이미지 한 줄만 바꾼다)
        ─ 5 서비스 롤링 → 새 태스크가 헬스체크를 통과할 때까지 대기
```

- **태그는 `날짜-커밋`** 이다. 날짜만 쓰면 하루에 두 번 배포할 때 겹친다. `latest` 도 같이 밀지만
  "가장 최근 빌드" 표시일 뿐, 배포는 항상 날짜 태그로 한다 — 무엇이 돌고 있는지가 태스크 정의에 남는다.
- **main 에 들어오면 곧바로 배포된다.** 테스트를 통과한 것만 들어오게 main 을 보호 브랜치로 두고
  CI 통과를 머지 조건으로 건다. 문서·`deploy/terraform/` 만 바뀐 커밋은 배포하지 않는다.
- 4·5 는 `deploy/ecs/deploy.sh` 가 한다. 손으로도 같은 것을 부른다 (`make deploy RELEASE=<태그>`).

Gitea Actions 와 GitHub Actions 양쪽에서 돈다. Gitea 는 `.gitea/workflows/` 가
없을 때 `.github/workflows/` 를 읽는다 — `.gitea/workflows/` 를 따로 만들면 이쪽이 무시된다.

### CI 의 AWS 권한

필요한 권한은 `terraform output deploy_policy_arn` 하나다 — 이 서비스의 ECR 푸시와 배포만 된다.

| 방법 | 어떻게 |
|---|---|
| **러너를 EC2 에 두고 인스턴스 역할** (권장) | `service/terraform.tfvars` 에 `ci_role_name = "<러너 역할>"`. 시크릿이 필요 없다 |
| 액세스 키 | 정책을 CI 용 IAM 사용자에 붙이고 저장소 시크릿 `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` |

**OIDC 역할 위임은 Gitea 에서 아직 안 된다.** Gitea Actions 가 OIDC 토큰(`id-token`)을 발급하지
않는다. 장기 키를 CI 에 두지 않으려면 지금은 러너의 인스턴스 역할이 같은 효과를 내는 방법이다.

## 처음 한 번

**1) 플랫폼** — VPC · 클러스터 · 호스트 풀 · ALB. 여러 서비스가 같이 쓰므로 **한 저장소에서 한 번만** 만든다.
이미 있으면 건너뛰고, 이 저장소에서 `deploy/terraform/platform/` 은 지워도 된다.

```bash
cd deploy/terraform/platform
cp terraform.tfvars.example terraform.tfvars    # 비워 두면 VPC 까지 새로 만든다
cd -
make platform-plan && make platform-apply
```

기본값은 VPC `10.0.0.0/16`, 퍼블릭 `10.0.0.0/24`·`10.0.3.0/24`, 프라이빗 `10.0.1.0/24`·`10.0.2.0/24`
(AZ a·c), NAT 1개다. 이미 있는 VPC 를 쓰려면 `vpc_id` 와 서브넷 ID 를 준다.

서비스는 플랫폼을 **이름으로** 찾는다 (클러스터 = ALB = 용량 공급자 = `apps`).
다른 방법으로 플랫폼을 만들었다면 이 이름 규칙만 맞추면 된다.

**2) 서비스**

```bash
cd deploy/terraform/service && cp terraform.tfvars.example terraform.tfvars && cd -
make tf-init

# 이미지가 있어야 서비스가 뜬다 — 저장소 먼저, 첫 이미지, 그다음 나머지
make tf-apply TF_ARGS=-target=aws_ecr_repository.app
make ecr-login
make image-push TAG=latest
make tf-apply
```

**3) CI 권한** — 위 표대로.

**4) 확인**

```bash
make ecs-status          # 태스크 2개가 서로 다른 AZ·호스트에 있는지
make ecs-logs
```

## 롤백

```bash
make releases                          # ECR 에 있는 태그, 최근 것부터
make deploy RELEASE=20260521-9f8e7d6   # 그 이미지로 다시 굴린다
```

Actions 화면에서 Release 를 수동 실행하고 `tag` 에 예전 태그를 넣어도 같다 (빌드를 건너뛴다).
옛 이미지는 ECR 에 최근 30개가 남는다. 원인이 된 커밋을 되돌리지 않으면 다음 push 가 다시 앞으로 굴린다.

## 데이터베이스 — 이중화하지 않는 별도 EC2

DB 는 이 구성 밖에 있다. 앱은 주소를 환경변수로, 비밀번호를 `secrets` 로 받아 붙는다.
앱 계층만 이중화했으므로 **DB 는 여전히 단일 장애점이다.** 복제 없이 가려면 아래는 필요하다.

| 무엇을 | 왜 |
|---|---|
| EBS 스냅샷 자동화 (DLM) + WAL 아카이브를 S3 로 (pgBackRest 등) | 복제가 없으면 백업이 유일한 복구 수단이다. 데이터가 많을수록 복구 시간을 재 본다 |
| EC2 자동 복구 (StatusCheckFailed_System 알람 → recover) | 하드웨어 장애 시 같은 볼륨·같은 IP 로 다시 뜬다 |
| 고정 주소 (Route 53 프라이빗 레코드 또는 고정 프라이빗 IP) | DB 호스트를 갈아도 앱 설정을 안 바꾼다 |
| `/health` 가 DB 를 보지 않게 | 본다면 DB 가 느려질 때 ALB 가 멀쩡한 태스크를 전부 뺀다 |
| 연결 수: `태스크 수 × 풀 크기 < max_connections` | 오토스케일·롤링 배포 중에는 태스크가 평소의 2배까지 뜬다. 넘치면 PgBouncer |
| 스키마 변경은 하위 호환으로 | 롤링 중에는 신·구 버전이 같은 DB 를 동시에 쓴다 |

보안 그룹은 플랫폼의 `db_security_group_id` 에 DB 의 그룹을 주면 ECS 호스트 → DB 포트
규칙이 자동으로 들어간다. 직접 넣으려면 `terraform output host_security_group_id` 를 쓴다.
DB 가 다른 VPC 에 있으면 피어링이 먼저다.

## 설정과 비밀값

`deploy/terraform/service/terraform.tfvars`:

```hcl
environment = {
  APP_DB_HOST = "db.internal.example.com"
}
secrets = {
  APP_DB_PASSWORD = "arn:aws:ssm:ap-northeast-2:<계정>:parameter/finbrief-analyzer/db-password"
}
```

**비밀값을 git 이나 `environment` 에 넣지 않는다.** Parameter Store(SecureString) 나
Secrets Manager 에 두고 ARN 만 적는다.

```bash
aws ssm put-parameter --type SecureString --name /finbrief-analyzer/db-password --value '...'
```

`make tf-apply` 로 바꾼 설정은 **다음 배포 때** 굴러간다 — terraform 은 새 태스크 정의
리비전만 만들고, 서비스를 갈아 끼우는 것은 `deploy.sh` 다. 바로 반영하려면 지금 도는 태그로
`make deploy RELEASE=<태그>` 를 한 번 부른다.

## 관측

| 무엇을 | 어디서 |
|---|---|
| 컨테이너 로그 | CloudWatch Logs `/ecs/finbrief-analyzer` — `make ecs-logs` |
| 태스크·서비스 지표 | Container Insights (클러스터에 켜져 있다) |
| 호스트 메모리·디스크 | CloudWatch 에이전트 → 네임스페이스 `apps/ecs-host` |
| 알람 | `finbrief-analyzer-tasks-below-desired` (이중화가 깨짐) · `-unhealthy-targets` · `-5xx` |

알람은 만들어지지만 **`alarm_topic_arn` 을 줘야 알림이 간다.** ALB 액세스 로그는 CloudWatch 가
아니라 S3 로 가는 것이라 여기서는 켜지 않았다.

## 손봐야 하는 곳

| 파일 | 고칠 것 |
|---|---|
| `service/terraform.tfvars` | `host_headers` (도메인) · `route53_zone_id` · `environment` · `secrets` · `ci_role_name` |
| `service/variables.tf` | `cpu` · `memory` — 부하 테스트 후 조정. 지금 값은 출발점일 뿐 |
| `service/variables.tf` | `desired_count` · `max_count` · `cpu_target` |
| `platform/terraform.tfvars` | `instance_type` · `min_size` · `certificate_arn` · `nat_per_az` |
| `*/versions.tf` | `backend "s3"` 주석 해제 — 상태를 로컬에 두지 않는다 |
| `.github/workflows/release.yml` | `PLATFORMS` — Graviton 호스트면 `linux/arm64` |

## 로컬 의존 서비스

```bash
make up                  # postgres (기본 PROFILES=db)
make up PROFILES=db,mq   # + rabbitmq, 관리 UI http://localhost:15672
make up PROFILES=all
make psql
make down                # make nuke 는 볼륨까지 삭제
```

| 프로파일 | 서비스 | 포트 |
|---|---|---|
| `db` | postgres 18 | 5432 |
| `cache` | redis 8 | 6379 |
| `mq` | rabbitmq 4 | 5672 / 15672 |
| `mqtt` | mosquitto 2 | 1883 / 9001 |
| `app` | 이 프로젝트 이미지 | 8000 |
