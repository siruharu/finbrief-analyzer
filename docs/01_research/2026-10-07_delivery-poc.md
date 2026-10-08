---
type: research
project: finbrief-analyzer
topic: delivery-poc
created: 2026-10-08
status: done
source_task: "[[2026-10-07_delivery-channels]]"
tags: [research, poc, delivery, email, gmail, smtp, scheduler]
next: implementation
---

# 🔍 발송 PoC (delivery-channels Task 1)

> **핵심 질문** — 개인 Gmail SMTP 로 실제 발송이 되는가. 스케줄·마이그레이션·테스트 DB 를 어디에 둘 것인가.

## 사용자 결정 (2026-10-08) — 아래 본문과 어긋나면 이 절이 우선한다
- **AWS 를 쓰지 않는다. 로컬에서 먼저 전부 구성한다.** 발송·DB·스케줄 모두 개발 PC 에서 돈다.
- 그래서 3번(AWS 호스트 로그인)은 **해당 없음**이 됐다. 발송 수단이 SES 로 바뀔 위험도 지금은 없다 — 로그인이 확인된 바로 그 PC 에서 보낸다.
- 4번(EventBridge Scheduler)과 5번(일회성 ECS 태스크)은 **AWS 로 옮길 때의 참고 자료**로만 남긴다. 지금 쓰지 않는다.
- 마이그레이션은 로컬에서 `uv run alembic upgrade head` 로 직접 돌린다. DB 는 `compose.yml` 의 postgres 18 이다.
- Task 8(인프라: 비밀값·스케줄·실패 알람)은 terraform 전제라 그대로는 하지 않는다. 로컬에서 정해진 시각에 작업을 띄우는 방법은 아직 정하지 않았다 → Task 7 뒤에 다시 정한다.
- 6번의 "테스트는 SQLite 메모리 DB" 결정은 그대로 둔다.

## 실행 조건
- 일시: 2026-10-08. 실행 위치는 개발 PC(가정/사무실 회선). AWS 호스트가 아니다.
- Python 3.12.10 표준 라이브러리 `smtplib` + `email.message.EmailMessage`. 추가 의존성 없음.
- 일회성 스크립트는 저장소 밖 scratch 폴더에서 실행했고 커밋하지 않았다.
- `.env` 의 `APP_SMTP_USER`·`APP_SMTP_PASSWORD` 는 스크립트가 읽어 로그인에만 썼다. 값은 출력·문서에 옮기지 않았다.
- 이 PC 의 도구: `uv`·`docker` 있음. `make`·`gh`·`aws`·`terraform` 없음.

## 요약
| # | 질문 | 결과 |
|---|---|---|
| 1 | 로컬에서 `smtp.gmail.com:587` 로그인·발송 | **됨.** 로그인 235, 거부된 수신자 없음. 네이버 **받은편지함 도착, 스팸 아님** (사용자 확인) |
| 2 | SPF·DKIM·DMARC | **헤더는 확인 못 함.** 다만 스팸으로 분류되지 않았다 |
| 3 | AWS 호스트에서 로그인 | **해당 없음.** AWS 를 쓰지 않는다 (사용자 결정) |
| 4 | EventBridge Scheduler 시간대·RunTask | **문서상 됨.** `America/New_York` 지정과 서머타임 자동 반영, EC2 launch type RunTask. 명령 덮어쓰기 방법은 확인 못 함 |
| 5 | 마이그레이션 실행 위치 | **지금은 로컬에서 직접 실행.** AWS 로 옮기면 일회성 ECS 태스크 |
| 6 | 운영 DB·테스트 DB | 로컬 PostgreSQL 18 (`compose.yml`). **결정: 테스트는 SQLite 메모리 DB** |

## 1. 로컬 SMTP 로그인과 발송
- 순서: `EHLO` 250 → `STARTTLS` 220 → `EHLO` → `LOGIN` 235 → `send_message` 가 돌려준 거부 목록 `{}`.
- 발신: `.env` 의 Gmail 계정. 수신: `ho***@naver.com` (사용자가 지정한 주소) 1통.
- 제목 `[finbrief] SMTP PoC 테스트 발송`, 본문은 한글 평문 2줄. `EmailMessage.set_content` 가 UTF-8 로 인코딩했다.
- 앱 비밀번호는 16자였다. 구글이 보여 주는 형식(4자씩 공백)으로 붙여 넣었을 수 있어 공백을 걷어 내고 로그인했다.
  → **Task 5 의 Notifier 도 비밀번호의 공백을 걷어 낸다.**
- 사용자 확인(2026-10-08): 네이버 받은편지함에 도착했고 스팸이 아니다. 본문 두 줄(한글, `%`, `+2.8bp`)이 깨지지 않고 그대로 보였다.

## 2. SPF·DKIM·DMARC
- 확인 못 함. 네이버 메일에서 받은 메일의 원문(헤더)을 열어 `Authentication-Results` 또는 `Received-SPF`·`DKIM-Signature` 줄을 봐야 한다.
- 볼 것: `spf=pass`, `dkim=pass header.d=gmail.com`, `dmarc=pass`. 스팸함에 들어갔는지 여부도 함께 적는다.

## 3. AWS 호스트에서의 로그인
- 확인 못 함. 이 PC 에 `aws` CLI 와 자격증명이 없어 ECS 호스트에서 스크립트를 돌릴 수 없다.
- 저장소에서 확인한 것: 호스트는 프라이빗 서브넷이고 NAT 게이트웨이의 고정 IP(`aws_eip.nat`)로 나간다. `nat_per_az = true` 면 고정 IP 가 AZ 수만큼 생긴다 → Gmail 이 보는 "위치"가 둘 이상일 수 있다.
- 리서치([gmail-smtp-sending](2026-10-07_gmail-smtp-sending.md))에서 확인한 것: 호스트 보안 그룹의 egress 는 전부 열려 있고, EC2 의 기본 제한 대상은 포트 25 뿐이다.
- **남은 위험**: 새 위치 로그인이 차단되면 "약 1주 뒤 재시도" 안내만 있다. 그 경우 기다리지 않고 분석으로 돌아가 도메인 + SES 를 다시 본다. 바뀌는 것은 Task 5·8 뿐이다.
- **Task 8 에 넣을 확인 순서**: 스케줄을 걸기 전에 일회성 태스크로 발송 작업을 한 번 실행해 로그인 결과를 본다.

## 4. EventBridge Scheduler 와 ECS RunTask
공식 문서에서 직접 확인(2026-10-08).

- **시간대**: cron·일회성 스케줄은 IANA 시간대를 지정할 수 있다. 문서의 예시가 `--schedule-expression-timezone "America/New_York"` 이다.
- **서머타임**: "EventBridge Scheduler automatically adjusts your schedule for daylight saving time." 봄에 사라지는 시각에 걸린 스케줄은 그날 건너뛰고, 가을에 겹치는 시각은 한 번만 실행한다.
  - 미국 개장 09:30 ET 와 국내 개장 09:00 KST 는 전환 구간(02:00~03:00)에 걸리지 않는다.
- **정밀도**: 60초. 1:00 에 건 스케줄은 1:00:00~1:00:59 사이에 대상을 부른다.
- **cron 식**: 필드 6개(분 시 일 월 요일 연). 일·요일 중 하나는 `?` 여야 한다. 월~금 09:30 은 `cron(30 9 ? * MON-FRI *)`.
- **RunTask 대상**: `EcsParameters` 가 ECS `RunTask` 의 templated target 이다.
  - `TaskDefinitionArn` 만 필수. `LaunchType` 은 `EC2 | FARGATE | EXTERNAL`, `CapacityProviderStrategy` 도 줄 수 있다.
  - `NetworkConfiguration` 은 선택 항목이다 → bridge 네트워크인 이 서비스의 태스크 정의는 주지 않아도 된다.
  - `TaskCount` 기본 1, 최대 10.
- **이 저장소에 맞추면**: 서비스가 `capacity_provider_strategy` 로 플랫폼의 용량 공급자를 쓴다(`service/main.tf:150`). 스케줄도 같은 용량 공급자를 쓰면 여유 용량이 없을 때 호스트가 늘어난다. `LaunchType = EC2` 로 두면 자리가 없을 때 그냥 실패한다.

### 확인 못 한 것
- [ ] 컨테이너 명령 덮어쓰기. 태스크 정의의 기본 명령은 웹 서버(`python -m finbrief_analyzer.main`)다. 발송 작업을 돌리려면 `containerOverrides.command` 를 줘야 하는데, `EcsParameters` 에는 그 항목이 없다. 대상의 `Input` 에 RunTask 의 overrides JSON 을 넣는 방식으로 알고 있으나 **이번에 문서에서 문구를 찾지 못했다.** 안 되면 발송 작업용 태스크 정의를 따로 두어야 하고, 그러면 `deploy.sh` 가 그 정의의 이미지도 함께 바꿔야 한다.
- [ ] `TaskDefinitionArn` 에 리비전 없는 ARN 을 주면 최신 리비전으로 실행되는지. Task 8 의 "리비전 번호를 고정하지 않는다"가 여기에 달려 있다.
- [ ] 스케줄러 실행 역할의 최소 권한(`ecs:RunTask`, 두 역할의 `iam:PassRole`) 예시 문구.

세 가지 모두 Task 8 을 시작할 때 `terraform validate` 전에 문서로 다시 확인한다.

## 5. 마이그레이션 실행 위치
읽은 것: `deploy/ecs/deploy.sh`, `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `deploy/terraform/service/*.tf`, `Dockerfile`.

| 후보 | 판단 | 근거 |
|---|---|---|
| CI 러너에서 실행 | 안 됨 | 러너가 `ubuntu-latest` 다. DB 는 프라이빗 EC2 라 닿지 않는다 |
| 앱 기동 시 실행 | 안 함 | 태스크가 2개 이상 동시에 뜬다 → 같은 마이그레이션을 동시에 돈다. `/health` 와 기동이 DB 에 기대게 된다 |
| `deploy.sh` 안에서 RunTask | 지금은 안 함 | 배포 정책(`iam.tf` 의 `deploy`)에 `ecs:RunTask` 가 없다. 넣으면 모든 배포가 DB 상태에 묶이고, 마이그레이션 실패가 배포 실패가 된다 |
| **일회성 ECS 태스크를 사람이 실행** | **채택** | 스키마 변경은 하위 호환이 규칙이라 "마이그레이션 먼저, 배포 나중" 순서가 항상 안전하다. 변경 빈도가 낮다 |

- 절차는 Task 8 에서 `deploy/README.md` 에 적는다: 새 이미지가 ECR 에 올라간 뒤 → `alembic upgrade head` 를 명령으로 덮어쓴 일회성 태스크 실행 → 로그 확인.
- 순서 문제: main 에 들어가면 바로 배포된다. 새 코드가 새 테이블을 쓰는 커밋은 **마이그레이션만 담은 커밋이 배포·적용된 뒤에** 넣는다. Task 3(빈 환경)·Task 4(테이블 추가)가 Task 6(테이블 사용)보다 앞에 있어 이 순서가 이미 맞다.
- **Task 3 에 추가할 일**: `Dockerfile` 이 `src` 만 복사한다(`COPY src ./src`). `alembic.ini` 와 `migrations/` 가 이미지에 들어가지 않으면 태스크에서 마이그레이션을 돌릴 수 없다 → 마이그레이션을 패키지 안(`src/finbrief_analyzer/migrations/`)에 두거나 `Dockerfile` 에 복사 줄을 추가한다.

## 6. 운영 DB 와 테스트 DB
- **운영 DB 종류**: 저장소 기준 PostgreSQL. `compose.yml` 이 `postgres:18-alpine`, 플랫폼 변수 `db_port` 기본값이 5432, tfvars 예시가 `APP_DB_PORT = "5432"` 다.
- **운영 DB 버전**: 확인 못 함. DB 는 terraform 밖의 별도 EC2 라 저장소에 버전이 없다. → 사용자 확인 필요.
- **CI**: `ci.yml` 에 서비스 컨테이너가 없다. `uv sync` → ruff → mypy → pytest 만 돈다.
- **결정: 테스트는 SQLite 메모리 DB.**
  - 종료 훅과 CI 가 `pytest` 를 매번 돌린다. Postgres 를 요구하면 docker 가 떠 있지 않은 순간마다 검증이 깨진다.
  - 대가: 방언 차이를 테스트가 잡지 못한다. 그래서 아래를 지킨다.
    - 발송 선점은 `INSERT ... ON CONFLICT`(방언 전용) 대신 **INSERT 후 유일 제약 위반(`IntegrityError`)을 잡는 방식**으로 쓴다. 두 DB 에서 같은 코드가 돈다.
    - 컬럼 타입은 SQLAlchemy 공통 타입만 쓴다(JSONB·ARRAY·서버 기본값 함수 금지). 시각은 timezone-aware `DateTime` 으로 두고 UTC 로 저장한다 — SQLite 는 시간대를 버리므로 읽을 때 UTC 를 붙인다.
    - SQLite 는 `ALTER` 가 제한적이다. 마이그레이션 테스트는 "빈 DB 에 끝까지 적용" 까지만 보장한다.
  - Postgres 확인은 수동으로 남긴다: `docker compose up` → `uv run alembic upgrade head` → `downgrade -1`. Task 3·4 를 끝낼 때 한 번씩 한다.

## 틀렸거나 바뀐 가정
- 태스크 문서의 "이 PC 에 `uv` 가 없다" → **지금은 있다.** `docker` 도 있다. `make`·`gh`·`aws`·`terraform` 은 여전히 없다.
- 플랜은 `alembic.ini`·`migrations/` 를 저장소 루트에 둔다고 적었다 → 이미지에 들어가지 않는다 (5번).

## 남은 것
- [ ] 받은 메일 원문의 SPF·DKIM·DMARC 결과 — 2번. 스팸으로 가지 않아 급하지 않다. 수신자가 늘거나 스팸으로 가기 시작하면 본다
- [ ] 로컬에서 정해진 시각에 발송 작업을 띄우는 방법 — Task 7 뒤
- [ ] AWS 로 옮길 때: 호스트에서의 Gmail 로그인(3번), 스케줄 대상의 명령 덮어쓰기·리비전 없는 ARN·실행 역할 권한(4번)

## 참고
- [Schedule types in EventBridge Scheduler](https://docs.aws.amazon.com/scheduler/latest/UserGuide/schedule-types.html) — 시간대, 서머타임, cron 식
- [EcsParameters](https://docs.aws.amazon.com/scheduler/latest/APIReference/API_EcsParameters.html) — RunTask templated target 의 항목
- [Using templated targets](https://docs.aws.amazon.com/scheduler/latest/UserGuide/managing-targets-templated.html) — ECS 예시는 없다
- [개인 Gmail 계정으로 직접 발송](2026-10-07_gmail-smtp-sending.md) — 앱 비밀번호, 한도, 새 위치 로그인
