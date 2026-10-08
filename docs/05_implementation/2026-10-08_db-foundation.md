---
type: implementation
project: finbrief-analyzer
topic: delivery-channels
created: 2026-10-08
status: done
source_task: "[[2026-10-07_delivery-channels]]"
commits: [0e18946]
blog_candidate: true
tags: [implementation]
---

# 🛠️ 구현: delivery-channels Task 3 — DB 기반 (엔진·세션·마이그레이션 환경)

테이블은 아직 0개다. DB 에 붙는 길과 마이그레이션을 돌리는 길만 냈다. 기존 동작은 바뀌지 않는다.

## 한 일
- 의존성 추가와 버전 고정: `sqlalchemy==2.1.4`, `psycopg[binary]==3.3.6`, `alembic==1.20.0`.
- `Settings` 에 `db_host/db_port/db_name/db_user/db_password` 와 `database_url()`.
- `core/db.py`: `make_engine(settings)`, `session_scope(engine)`.
- `alembic.ini`, `src/finbrief_analyzer/migrations/` (`env.py`, `script.py.mako`, `versions/`).
- `.env.example` 에 `APP_DB_*` 예시.
- `compose.yml` 의 postgres 볼륨 마운트 경로 수정 (아래 "막혔던 부분").
- 테스트 9개 (`tests/store/test_db.py`), `engine` 픽스처 (`tests/store/conftest.py`).

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| 마이그레이션을 **패키지 안**(`src/finbrief_analyzer/migrations/`)에 둔다 | 플랜대로 저장소 루트의 `migrations/` | PoC 5번에서 확인한 대로 `Dockerfile` 이 `src` 만 복사한다. 지금은 로컬에서만 돌리지만, 코드와 같이 다니게 해 두면 나중에 옮길 때 고칠 것이 없다 |
| DB 설정 5개는 전부 선택값. 빠진 것은 `database_url()` 을 부를 때 드러난다 | 필수값 | 웹 앱과 `/health` 는 DB 없이 떠야 한다. DB 가 필요한 것은 발송 작업뿐이다 |
| 오류 메시지에 **빠진 변수 이름**을 적는다 | "DB 설정 없음" | 일부만 넣었을 때 무엇을 더 넣어야 하는지 바로 보인다 |
| URL 은 `URL.create(...)` 로 조립 | f-string | 비밀번호의 `@`·`/`·`:` 가 호스트 구분자로 읽히지 않는다. `str(url)` 은 비밀번호를 `***` 로 가린다 |
| 드라이버는 psycopg 3 (`postgresql+psycopg`), 동기 | asyncpg | 발송은 하루 2회 배치다. 동기로 충분하고 `smtplib` 도 동기다 |
| `env.py` 는 `Config` 에 `sqlalchemy.url` 이 있으면 그것을, 없으면 `Settings` 를 쓴다 | `Settings` 만 | 테스트가 임시 DB 를 가리킬 수 있어야 한다. `os.getenv` 는 쓰지 않는다 |
| `env.py` 는 온라인 모드만 | 오프라인(SQL 출력) 모드도 | 쓸 일이 없다. 필요해지면 추가한다 |
| 테스트 DB 는 SQLite | Postgres 컨테이너 | PoC 6번의 결정. 종료 훅과 CI 가 docker 없이 돈다 |
| `session_scope` 는 `Session(engine)` + `session.begin()` | 직접 try/commit/rollback | SQLAlchemy 가 같은 일을 한다. 함수가 두 줄이 된다 |

## 막혔던 부분 / 해결 과정
> 💡 블로그 소재.

**증상**
`docker compose --profile db up -d --wait` 가 끝나지 않았다. 컨테이너는 `Exited (1)` 이고, `alembic upgrade head` 는 `localhost:5432 connection timeout expired` 로 실패했다.

**가설과 검증**
- 가설 1: 예전 버전 데이터가 볼륨에 남아 있다. 로그에 "there appears to be PostgreSQL data in /var/lib/postgresql/data (unused mount/volume)" 와 "upgrading the Docker image without pg_upgrade" 가 찍혀 있었다.
  → `docker volume inspect` 로 보니 볼륨은 방금(이번 `up` 에서) 만들어졌고, alpine 컨테이너로 열어 보니 비어 있었다(4.0K). 기각.
- 가설 2: 마운트 경로가 틀렸다. 같은 로그의 뒷부분이 답이었다 — "The suggested container configuration for 18+ is to place a single mount at /var/lib/postgresql".

**원인**
`compose.yml` 이 `postgres:18-alpine` 인데 볼륨을 `/var/lib/postgresql/data` 에 걸고 있었다. postgres 18 이미지는 데이터를 버전별 하위 디렉터리에 두고, 옛 경로에 마운트가 걸려 있으면 기동을 거부한다. 템플릿에서 온 설정이고 이 저장소에서 postgres 를 띄운 것은 이번이 처음이라 지금까지 드러나지 않았다.

**해결**
마운트를 `pgdata:/var/lib/postgresql` 로 바꿨다. 볼륨이 비어 있어 옮길 데이터는 없었다. 컨테이너를 지우고 다시 띄우니 5초 만에 healthy.

곁가지: 처음에 `sed` 로 고치려다 구분자 `#` 가 치환 문자열 안의 주석 `#` 과 겹쳐 명령이 실패했는데, 뒤 명령이 이어서 돌아 "고쳤는데도 안 뜬다"로 잘못 읽었다. 실패한 명령의 출력을 먼저 읽었어야 했다.

## 검증 결과
```
uv run pytest tests/store/test_db.py  → 9 passed
uv run ruff check .                   → All checks passed!
uv run mypy                           → Success: no issues found in 48 source files
uv run pytest                         → exit 0, 커버리지 97%
```
수동 확인 (로컬 postgres 18.6):
```
docker compose --profile db up -d --wait   → Healthy
uv run alembic upgrade head                → exit 0
\dt                                        → public | alembic_version
```
커버리지가 99% → 97% 로 내려간 것은 `migrations/env.py` 때문이다. Alembic 이 이 파일을 import 가 아니라 직접 실행해서 측정에 잡히지 않는다. 마이그레이션 적용 테스트가 실제로는 이 파일을 지난다.

## 발견한 이슈 (이번 범위 밖)
- [ ] 이 PC 에 `make` 가 없어 `make up` 을 쓸 수 없다. `docker compose --profile db up -d --wait` 로 대신한다.
- [ ] `finbrief-analyzer-app-1` 컨테이너가 19시간째 떠 있다(8000 포트). 이번 작업과 무관해 건드리지 않았다.
- [ ] `.env` 에 `APP_DB_*` 가 아직 없다. Task 7 의 수동 발송 전에 `.env.example` 의 다섯 줄을 옮겨 넣어야 한다.

## 남은 것
- [ ] Task 4 에서 `migrations/env.py` 의 `target_metadata` 를 테이블 메타데이터로 바꾼다.
