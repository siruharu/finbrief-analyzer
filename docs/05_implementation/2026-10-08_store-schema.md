---
type: implementation
project: finbrief-analyzer
topic: delivery-channels
created: 2026-10-08
status: done
source_task: "[[2026-10-07_delivery-channels]]"
commits: [e72ea6b]
blog_candidate: false
tags: [implementation]
---

# 🛠️ 구현: delivery-channels Task 4 — 수신자·발송 기록 스키마와 저장소

"누구에게, 이미 보냈는지"를 DB 가 답하게 했다. 아직 아무도 이 코드를 부르지 않는다 (Task 6 에서 만난다).

## 한 일
- `store/tables.py`: `recipients`, `delivery_log` 와 유일 제약 `(brief_date, slot, recipient_id, channel)`.
- `store/recipients.py`: `Recipient`, `list_active(session)`.
- `store/delivery_log.py`: `DeliveryKey`, `claim`, `mark_sent`, `mark_failed`.
- 첫 마이그레이션 `migrations/versions/0001_recipients_delivery_log.py`. `env.py` 의 `target_metadata` 를 테이블 메타데이터로 연결.
- 테스트 14개 (수신자 3, 발송 기록 11).

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| `claim` 은 **넣고 나서 충돌을 본다** (`IntegrityError` → `False`) | 조회 후 삽입 | 조회와 삽입 사이에 다른 프로세스가 끼어들 수 있다. 판정을 유일 제약에 맡기면 틈이 없다 |
| `INSERT` 를 세이브포인트(`begin_nested`) 안에서 한다 | 그냥 실행 | Postgres 는 제약 위반이 나면 그 트랜잭션 전체가 못 쓰게 된다. 세이브포인트만 되돌리면 호출자가 같은 트랜잭션에서 다음 수신자를 계속 처리할 수 있다 |
| `ON CONFLICT DO NOTHING` 을 쓰지 않는다 | 방언 전용 구문 | PoC 6번의 결정. SQLite(테스트)와 Postgres(실제)에서 같은 코드가 돈다 |
| 실패한 키는 `UPDATE ... WHERE status='failed'` **한 문장**으로 다시 연다 | 상태를 읽고 나서 갱신 | 두 프로세스가 동시에 재시도해도 한쪽만 `rowcount == 1` 을 받는다 |
| pending 으로 남은 키는 다시 열지 않는다 | 일정 시간 뒤 다시 연다 | 태스크 설계 그대로다. 중복 발송보다 누락을 택한다. 다시 여는 기준은 열어둔 질문으로 남아 있다 |
| Core `Table` + 함수 | ORM 매핑 클래스 | 테이블 2개, 쿼리 5개다. 도메인 타입(`Recipient`, `DeliveryKey`)은 frozen dataclass 로 따로 둬서 DB 행이 밖으로 새지 않는다 |
| `slot`·`channel`·`status` 는 `String` 열 | DB enum 타입 | Postgres enum 은 값 추가가 마이그레이션이고 SQLite 에는 없다. 값의 범위는 파이썬 `StrEnum` 이 지킨다 |
| 기본값은 파이썬 쪽(`default=`) | 서버 기본값 | `now()` 같은 서버 함수는 방언마다 다르다. 마이그레이션에는 기본값이 없다 → 수신자를 SQL 로 직접 넣을 때는 `active`, `created_at` 을 적어야 한다 (아래 "남은 것") |
| 사유는 500자에서 자른다 | 길이 초과 시 오류 | 기록 실패 때문에 발송 결과를 잃지 않게 한다 |
| 마이그레이션은 손으로 썼다 | `alembic revision --autogenerate` | 자동 생성은 살아 있는 DB 와 비교해야 한다. 테이블 2개라 손으로 쓰고, "마이그레이션 결과의 열 = 테이블 정의의 열" 테스트로 어긋남을 잡는다 |

## 막혔던 부분 / 해결 과정
작은 것 둘.

- **테스트끼리 헬퍼를 import 할 수 없었다.** `from tests.store.conftest import add_recipient` 가 `No module named 'tests'` 로 실패했다. `tests/` 에 `__init__.py` 가 없어 패키지가 아니다. 헬퍼를 픽스처(`add_recipient`)로 바꿨다.
- **`session.execute(update(...))` 의 결과에 `rowcount` 가 없다고 mypy 가 막았다.** SQLAlchemy 2.1 의 타입은 `Session.execute` 가 `Result` 를 돌려준다고 적혀 있고, `rowcount` 는 `CursorResult` 에 있다. `session.connection().execute(...)` 로 바꾸면 `CursorResult` 가 온다. 같은 트랜잭션이다.

## 검증 결과
```
uv run pytest tests/store   → 23 passed
uv run ruff check .         → All checks passed!
uv run mypy                 → Success: no issues found in 55 source files
uv run pytest               → exit 0, 커버리지 97%
```
수동 확인 (로컬 postgres 18.6). SQLite 테스트가 못 보는 방언 차이를 여기서 확인했다.
```
alembic upgrade head → downgrade -1 → upgrade head   → 0001 (head)
claim / 같은 키 재시도 / 같은 트랜잭션에서 다른 키 / 실패 뒤 재시도 / 발송 뒤 재시도
  → [True, False, True, True, False]  (기대값과 같음)
```
확인에 쓴 행은 지웠다. `recipients` 는 0건이다.

## 발견한 이슈 (이번 범위 밖)
- [ ] SQLite 는 외래 키를 기본으로 검사하지 않는다. 없는 `recipient_id` 로 `claim` 하면 테스트에서는 통과하고 Postgres 에서는 실패한다. 수신자는 항상 `list_active` 에서 오므로 지금은 문제가 되지 않는다.

## 남은 것
- [ ] 수신자 등록 방법. 지금은 SQL 로 직접 넣는다:
  `insert into recipients (email, name, active, created_at) values ('...', '...', true, now());`
  Task 7 의 수동 발송 전에 한 명을 넣어야 한다. 등록 명령을 따로 만들지는 플랜에 없다.
- [ ] 오래된 pending 을 다시 여는 기준 (열어둔 질문).
