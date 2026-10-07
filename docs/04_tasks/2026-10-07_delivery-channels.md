---
type: task
project: finbrief-analyzer
topic: delivery-channels
created: 2026-10-07
source_plan: "[[2026-10-07_delivery-channels]]"
branch: feat/delivery-email-smtp
issue: #
tags: [task]
next: implementation
---

# ✅ 작업: 발송 채널 (메일 1차 발송)

> **작업 상태의 정본은 이 문서가 아니라 `delivery-channels.tasks.json` 이다.**
> 체크박스를 여기에 다시 적지 않는다 — 두 곳을 손으로 맞추면 반드시 어긋난다.
>
> ```bash
> .claude/hooks/harness.py stage task delivery-channels
> .claude/hooks/harness.py task list
> .claude/hooks/harness.py task next
> ```
>
> 이 문서는 **왜 이렇게 쪼갰는지**를 적는 곳이다.

## 쪼갠 기준
- **PoC 를 맨 앞에 뒀다.** AWS 호스트에서 Gmail 로그인이 차단되면 발송 수단 자체가 바뀐다(도메인 + SES). 그때 바뀌는 것은 Task 5·8 뿐이도록 나머지를 수단과 무관하게 쪼갰다.
- **두 갈래로 나눴다.** "무엇을 보낼지"(Task 2 → 5)와 "누구에게, 이미 보냈는지"(Task 3 → 4)는 서로 import 하지 않는다. Task 6 에서 처음 만난다.
- **DB 기반(Task 3)과 스키마(Task 4)를 나눴다.** Task 3 은 테이블이 0개여도 배포할 수 있고 기존 동작을 바꾸지 않는다. 마이그레이션 도구 도입과 첫 테이블을 한 커밋에 섞으면 되돌릴 단위가 커진다.
- **Notifier(Task 5)와 조율(Task 6)을 나눴다.** Task 5 는 "한 통을 보내는 방법", Task 6 은 "누구에게 몇 번 보낼지"다. 카카오톡을 붙일 때 Task 6 은 그대로 쓴다.
- **인프라(Task 8)를 맨 뒤에 뒀다.** 로컬에서 한 명령으로 메일이 나가는 것(Task 7)을 확인한 뒤에 스케줄을 건다. main 에 들어가면 배포되므로 동작하지 않는 작업을 스케줄에 걸지 않는다.

## 공통 규칙
- 완료 판정의 `uv run ruff check . && uv run mypy && uv run pytest` 는 `make check` 와 같은 내용이다. 이 PC 에 `make` 가 없어 풀어서 적었다.
- 테스트는 실제 SMTP 서버·AWS 에 접속하지 않는다. DB 테스트의 대상 DB 는 Task 1-6 의 결정을 따른다.
- 테스트는 Given/When/Then 주석 구조, 이름은 보장하는 성질을 말한다.
- 함수 30줄 이하. 주석·식별자는 영어.
- 앱 비밀번호·DB 비밀번호는 `SecretStr`. 로그·예외·문서·커밋에 값이 남지 않게 한다.
- 수신자 주소는 로그에 전체를 찍지 않는다 (앞 두 글자와 도메인만).

## Task 간 의존 중 하네스에 못 건 것
- **Task 7 은 `data-sources` 주제의 Task 10(`collect_snapshot`)이 끝나야 시작할 수 있다.** 하네스의 `--after` 는 같은 주제 안에서만 걸린다. Task 7 을 시작하기 전에 `stage task data-sources` 로 바꿔 Task 10 이 done 인지 확인한다.

## Task 별 설계 메모

### Task 1 — PoC: Gmail SMTP 발송·AWS 로그인·스케줄러·마이그레이션 위치 확인

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `docs/01_research/2026-10-07_delivery-poc.md` | — | 신규. 6개 항목의 결과와 결정 |
| (scratch) 일회성 스크립트 | — | 커밋하지 않는다 |
| `deploy/ecs/deploy.sh`, `.github/workflows/*.yml`, `deploy/terraform/service/*.tf` | — | 읽기만 (마이그레이션 위치·스케줄 대상 판단) |

**먼저 쓸 테스트**
- 없음 (탐색 Task). 대신 아래에 답한다.
  1. 로컬에서 `smtp.gmail.com:587` 로그인 → 본인 주소로 발송 → 받은편지함 도착 여부.
  2. 받은 메일 원본의 SPF·DKIM·DMARC 결과.
  3. AWS 호스트(NAT 고정 IP)에서 같은 로그인이 되는가. 차단 시 오류 코드와 해제 방법.
  4. EventBridge Scheduler 의 `America/New_York` 시간대 지정과 ECS RunTask 대상. EC2 launch type·bridge 네트워크에서 일회성 태스크 실행 가능 여부.
  5. 마이그레이션 실행 위치 결정.
  6. 운영 DB 종류·버전, CI 테스트 DB 방식(서비스 컨테이너 또는 SQLite).

**엣지 케이스**
- 2단계 인증이 보안 키 전용이면 앱 비밀번호 메뉴가 보이지 않는다.
- 3번에서 차단되면 "약 1주 뒤 재시도" 안내만 있다 → 기다리지 않고 분석으로 돌아가 도메인 + SES 를 다시 본다.
- 이 PC 에 `aws`·`terraform` CLI 가 없다 → 3·4번은 문서 확인까지만 하고 "실환경 확인 필요"로 남길 수 있다. 그 경우 Task 8 전에 다시 확인한다.
- 앱 비밀번호 값은 문서·스크립트·터미널 출력에 남기지 않는다.

**완료 판정**
```bash
python -c "import pathlib;t=pathlib.Path('docs/01_research/2026-10-07_delivery-poc.md').read_text(encoding='utf-8');assert all(k in t for k in ['smtp.gmail.com', 'DKIM', 'EventBridge', 'RunTask'])"
```

### Task 2 — 브리핑 모델, Notifier 인터페이스, 렌더러

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/deliver/__init__.py` | — | 신규 |
| `src/finbrief_analyzer/deliver/models.py` | `Briefing`, `Section`, `LinkItem`, `Channel`(StrEnum), `DeliveryStatus`(StrEnum), `RenderedEmail`, `DeliveryError(retryable)` | 신규. frozen dataclass |
| `src/finbrief_analyzer/deliver/ports.py` | `Notifier.send(recipient, email)` (`Protocol`) | 신규 |
| `src/finbrief_analyzer/deliver/render.py` | `render_email(briefing)`, `_subject(briefing)`, `_text_body(briefing)`, `_html_body(briefing)` | 신규 |
| `tests/deliver/__init__.py`, `tests/deliver/test_render.py` | — | 신규 |

**먼저 쓸 테스트**
- `Briefing 은 필수 섹션이 하나라도 비면 발송 불가로 판정한다`
- `제목은 슬롯 이름과 브리핑 날짜를 포함한다`
- `본문의 뉴스 항목마다 원문 링크가 들어간다`
- `HTML 본문은 기사 제목의 꺾쇠와 앰퍼샌드를 이스케이프한다`
- `text 본문과 HTML 본문은 같은 수의 항목을 가진다`
- `누락·휴장 안내가 있으면 본문 상단에 표시한다`

**엣지 케이스**
- 기사 제목에 스크립트 태그·따옴표가 든 경우 (외부 입력이다).
- 링크가 `http(s)` 가 아닌 항목 → 링크 없이 제목만 싣는다.
- 뉴스 0건이지만 시세는 있는 브리핑 → 발송 가능으로 본다. 필수 섹션은 시세다.
- 슬롯 enum 은 `collect.models.Slot` 을 재사용한다. 그 Task 가 아직 없으면 이 Task 에서 임시로 만들지 말고 data-sources Task 2 를 먼저 한다.

**완료 판정**
```bash
uv run pytest tests/deliver/test_render.py && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 3 — DB 기반 (엔진·세션·마이그레이션 환경)

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `pyproject.toml` | `dependencies` | sqlalchemy, DB 드라이버, alembic 추가와 버전 고정 |
| `src/finbrief_analyzer/core/config.py` | `Settings.db_host/db_port/db_name/db_user/db_password`, `Settings.database_url()` | 수정. 비밀번호는 `SecretStr | None` |
| `src/finbrief_analyzer/core/db.py` | `make_engine(settings)`, `session_scope(engine)` | 신규 |
| `alembic.ini`, `migrations/env.py` | — | 신규. URL 은 `Settings` 에서만 읽는다 |
| `.env.example` | — | `APP_DB_*` 예시 |
| `tests/store/__init__.py`, `tests/store/test_db.py`, `tests/store/conftest.py` | `engine` 픽스처 | 신규 |

**먼저 쓸 테스트**
- `APP_DB_* 가 모두 있으면 접속 URL 을 조립한다`
- `DB 비밀번호는 Settings 의 repr 에 나오지 않는다`
- `session_scope 는 정상 종료 시 커밋한다`
- `session_scope 는 예외가 나면 롤백하고 예외를 다시 던진다`
- `DB 설정이 없어도 create_app 과 /health 는 동작한다`
- `마이그레이션이 빈 DB 에 끝까지 적용된다`

**엣지 케이스**
- 비밀번호에 `@`·`/` 같은 URL 예약 문자가 든 경우 → URL 객체로 조립하고 문자열 연결을 쓰지 않는다.
- DB 설정이 일부만 있는 경우 → 어떤 변수가 빠졌는지 알려 주는 오류.
- `migrations/env.py` 에서 `os.getenv` 를 쓰지 않는다 (설정 규칙).
- 엔진은 import 시점에 만들지 않는다. `/health` 와 앱 기동이 DB 에 기대지 않게 한다.
- 로컬 postgres 확인(`make up` → `alembic upgrade head`)은 수동 확인으로 남긴다. 완료 판정은 테스트 안의 마이그레이션 적용으로 한다.

**완료 판정**
```bash
uv run pytest tests/store/test_db.py && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 4 — 수신자·발송 기록 스키마와 저장소

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/store/__init__.py` | — | 신규 |
| `src/finbrief_analyzer/store/tables.py` | `recipients`(id, email, name, active, created_at), `delivery_log`(id, brief_date, slot, recipient_id, channel, status, reason, updated_at, 유일 제약 4열) | 신규 |
| `src/finbrief_analyzer/store/recipients.py` | `list_active(session)` , `Recipient` | 신규 |
| `src/finbrief_analyzer/store/delivery_log.py` | `claim(session, key)`, `mark_sent(session, key)`, `mark_failed(session, key, reason)`, `DeliveryKey` | 신규 |
| `migrations/versions/0001_recipients_delivery_log.py` | `upgrade`, `downgrade` | 신규 |
| `tests/store/test_recipients.py`, `tests/store/test_delivery_log.py` | — | 신규 |

**먼저 쓸 테스트**
- `비활성 수신자는 list_active 결과에 없다`
- `처음 claim 하면 True 를 돌려주고 pending 행이 생긴다`
- `같은 키로 다시 claim 하면 False 를 돌려준다`
- `슬롯이 다르면 같은 날 같은 수신자도 각각 claim 된다`
- `실패로 기록된 키는 다시 claim 할 수 있다`
- `발송 완료로 기록된 키는 다시 claim 할 수 없다`
- `mark_failed 는 사유를 저장한다`
- `마이그레이션을 내렸다 올려도 스키마가 같다`

**엣지 케이스**
- 두 프로세스가 동시에 같은 키를 `claim` → 유일 제약 위반을 `False` 로 바꾼다. 조회 후 삽입이 아니라 삽입 후 충돌 판정이다.
- pending 인 채로 프로세스가 죽은 행 → 다음 실행에서 보내지 않는다(중복보다 누락을 택한다). 오래된 pending 을 다시 열지는 열어둔 질문으로 남긴다.
- 이메일 중복 등록 → `recipients.email` 유일 제약.
- 사유 문자열 길이 상한. 비밀값이 사유에 섞이지 않게 예외 메시지를 그대로 넣지 않는다.
- 스키마는 테이블 추가만 한다 (롤링 중 구버전이 같은 DB 를 쓴다).

**완료 판정**
```bash
uv run pytest tests/store && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 5 — SMTP Notifier

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/core/config.py` | `Settings.smtp_host`(기본 `smtp.gmail.com`), `smtp_port`(587), `smtp_user`, `smtp_password`(`SecretStr | None`), `mail_from_name`, `operator_email` | 수정 |
| `src/finbrief_analyzer/deliver/smtp.py` | `SmtpNotifier.__init__(settings, connect)`, `.send(recipient, email)`, `.close()`, `_build_message(recipient, email)`, `_classify(exc)` | 신규. `connect` 기본값만 `smtplib.SMTP` 를 연다 |
| `.env.example` | — | `APP_SMTP_*` 예시 (값은 비움) |
| `tests/deliver/test_smtp.py` | `FakeSmtp` | 신규 |

**먼저 쓸 테스트**
- `메시지는 text 와 HTML 두 파트를 가진 multipart 다`
- `From 은 표시 이름과 설정된 계정 주소다`
- `To 는 수신자 한 명뿐이다`
- `로그인 전에 STARTTLS 를 건다`
- `인증 실패는 재시도 불가 DeliveryError 로 바뀐다`
- `일시적 오류 응답은 재시도 가능 DeliveryError 로 바뀐다`
- `수신자 거절은 그 수신자의 실패로만 보고된다`
- `연결이 끊긴 뒤 다음 발송은 다시 연결한다`
- `앱 비밀번호는 예외 메시지에 들어 있지 않다`
- `SMTP 설정이 없으면 생성 시점에 알기 쉬운 오류를 낸다`

**엣지 케이스**
- 제목·표시 이름의 한글 → `EmailMessage` 가 인코딩하게 두고 직접 헤더 문자열을 만들지 않는다.
- 수신자 주소에 줄바꿈이 든 경우(헤더 주입) → 거부한다.
- 연결 타임아웃을 설정값으로 둔다. 기본 무한 대기를 쓰지 않는다.
- 연결 1개를 수신자 전원에게 재사용하되, 끝나면 반드시 닫는다.
- `smtplib` 의 디버그 출력은 켜지 않는다 (인증 문자열이 찍힌다).

**완료 판정**
```bash
uv run pytest tests/deliver/test_smtp.py && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 6 — 발송 조율 (선점 → 발송 → 기록)

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/deliver/dispatch.py` | `dispatch(briefing, recipients, notifier, log)`, `DispatchResult`(sent, skipped, failed, aborted), `_deliver_one(...)`, `_notify_operator(...)` | 신규 |
| `tests/deliver/test_dispatch.py` | `FakeNotifier` | 신규. 저장소는 테스트 DB |

**먼저 쓸 테스트**
- `claim 에 성공한 수신자에게만 보낸다`
- `이미 claim 된 수신자는 건너뛰고 skipped 로 센다`
- `한 수신자의 발송이 실패해도 나머지 수신자에게 보낸다`
- `실패한 발송은 사유와 함께 failed 로 기록된다`
- `재시도 불가 인증 오류가 나면 남은 수신자를 시도하지 않고 aborted 로 끝낸다`
- `aborted 로 끝난 실행에서 시도하지 않은 수신자는 claim 되지 않는다`
- `발송 불가로 판정된 브리핑은 아무에게도 보내지 않고 운영자에게만 알린다`
- `같은 입력으로 두 번 실행하면 두 번째 실행의 sent 는 0 이다`
- `수신자가 0명이면 아무것도 하지 않고 정상 종료한다`

**엣지 케이스**
- 발송은 성공했는데 `mark_sent` 가 실패(DB 끊김) → pending 으로 남아 다음 실행에서 재발송되지 않는다. 로그에 남긴다.
- 운영자 알림 자체가 실패 → 삼키고 로그만 남긴다. 알림 실패로 작업이 죽지 않게 한다.
- 재시도 가능 오류 → 이 Task 에서는 즉시 1회만 재시도하고, 그래도 실패하면 failed 로 기록한다 (다음 실행에서 다시 claim 된다).
- 운영자 알림도 같은 SMTP 경로다. 인증 실패 때는 보낼 수 없으므로 시도하지 않는다.

**완료 판정**
```bash
uv run pytest tests/deliver/test_dispatch.py && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 7 — 단순 작성기 v0 와 작업 엔트리포인트

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/compose/__init__.py`, `compose/simple.py` | `compose_simple(snapshot)`, `_quote_section(quotes)`, `_news_section(items)`, `_notice(snapshot)` | 신규 |
| `src/finbrief_analyzer/jobs/__init__.py`, `jobs/run_briefing.py` | `main(argv)`, `run(slot, now, deps)`, `JobDeps`, `_parse_args(argv)`, `_exit_code(result)` | 신규 |
| `Dockerfile` | — | 확인만. 같은 이미지에서 `python -m finbrief_analyzer.jobs.run_briefing` 이 실행되는지 |
| `tests/compose/test_simple.py`, `tests/jobs/test_run_briefing.py` | — | 신규 |

**먼저 쓸 테스트**
- `작성기는 지수·환율·금리를 등락률과 함께 한 섹션으로 만든다`
- `등락률이 없는 시세는 값만 싣는다`
- `누락된 출처와 휴장 시장은 안내 문구로 들어간다`
- `뉴스는 제목과 링크만 나열하고 요약 본문을 싣지 않는다`
- `알 수 없는 슬롯 인자는 0 이 아닌 종료 코드로 끝난다`
- `수집·작성·발송이 모두 성공하면 종료 코드 0 과 결과 요약 로그를 낸다`
- `대상 시장이 휴장이면 발송하지 않고 종료 코드 0 으로 끝난다`
- `발송이 aborted 로 끝나면 0 이 아닌 종료 코드로 끝난다`
- `일부 수신자만 실패하면 종료 코드 0 이고 실패 수가 로그에 남는다`
- `로그에 수신자 주소 전체와 비밀값이 없다`

**엣지 케이스**
- "대상 시장"의 정의: 국내 개장 슬롯은 국내 시장, 미국 개장 슬롯은 미국 시장의 개장 여부다. 스냅샷의 휴장 표시는 "직전 장" 기준이라 다를 수 있다 → 구현 전에 data-sources Task 10 의 휴장 표시가 무엇을 뜻하는지 맞춘다.
- 뉴스 건수가 많을 때 상한 (메일 길이).
- 처리되지 않은 예외 → 스택은 로그로, 종료 코드는 0 이 아니게.
- 작업 종료 시 SMTP 연결과 DB 엔진을 닫는다.
- `python -m ...main` (서비스)과 `python -m ...jobs.run_briefing` (작업)이 같은 `Settings` 를 쓴다.

**완료 판정**
```bash
uv run pytest tests/jobs && uv run ruff check . && uv run mypy && uv run pytest
```
수동 확인: `uv run python -m finbrief_analyzer.jobs.run_briefing --slot kr_open` 으로 본인 주소에 메일 1통.

### Task 8 — 인프라: 비밀값, 스케줄, 실패 알람

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `deploy/terraform/service/schedule.tf` | `aws_scheduler_schedule.kr_open`, `.us_open`, `aws_iam_role.scheduler`(RunTask·PassRole 한정), 실패 알람 | 신규 |
| `deploy/terraform/service/variables.tf` | `briefing_schedules`(식·시간대), `briefing_enabled` | 수정 |
| `deploy/terraform/service/terraform.tfvars.example` | `secrets` 에 `APP_SMTP_PASSWORD`, `environment` 에 `APP_SMTP_USER` 예시 | 수정 |
| `deploy/README.md` | "브리핑 발송" 절 | 수정. 마이그레이션, 수신자 등록 SQL, 앱 비밀번호 교체, 스케줄 끄는 법 |

**먼저 쓸 테스트**
- 없음 (terraform). 대신 plan 출력에서 아래를 확인한다.
  - 추가만 있고 기존 리소스의 교체·삭제가 없다.
  - 스케줄러 역할의 권한이 이 서비스의 태스크 정의 RunTask 와 두 역할의 PassRole 로 한정된다.
  - 스케줄 2개가 각각 `Asia/Seoul`·`America/New_York` 시간대와 월~금 식을 가진다.
  - 앱 비밀번호가 plan 출력에 평문으로 나오지 않는다.

**엣지 케이스**
- 태스크 정의의 모양은 terraform 이, 이미지 태그는 릴리스가 바꾼다 → 스케줄이 "최신 리비전"을 가리키도록 리비전 번호를 고정하지 않는다.
- 클러스터에 여유 용량이 없으면 RunTask 가 실패한다 → 실패 알람이 이것도 잡는지 확인한다.
- `briefing_enabled = false` 로 스케줄만 끌 수 있어야 한다 (롤백 경로).
- 스케줄러의 재시도 설정 → 중복 호출은 발송 기록이 막지만, 재시도 횟수는 낮게 둔다.
- 미국 휴장일에도 스케줄은 뜬다. 작업이 휴장을 판정해 조용히 끝난다.
- `terraform apply`, SSM 비밀값 등록, 운영 DB 마이그레이션은 **사용자 확인 후** 진행한다.

**완료 판정**
```bash
terraform -chdir=deploy/terraform/service init -backend=false && terraform -chdir=deploy/terraform/service validate
```
수동 확인: `make tf-plan` 검토 → 적용 → 스케줄 수동 실행 → 메일 1통 수신.

## 열어둔 질문
- **이 PC 에 `uv`, `make`, `gh`, `aws`, `terraform` 이 없다.** Task 2~7 은 `uv` 만 있으면 되고, Task 1-3·1-4 와 Task 8 은 AWS 접근이 필요하다.
- 발송 전용 Gmail 계정과 앱 비밀번호가 준비됐는지. `.env` 의 변수 이름은 `APP_SMTP_USER`, `APP_SMTP_PASSWORD` 로 맞춘다.
- pending 으로 남은 발송 기록을 얼마 뒤에 다시 열 것인가 (지금은 열지 않는다).
- 발송 시각을 개장 정각으로 둘지, 몇 분 앞당길지.
- 이슈는 만들지 않았다. 브랜치명은 이슈 번호 없이 `feat/delivery-email-smtp` 로 제안한다.
