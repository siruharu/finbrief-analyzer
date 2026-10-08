---
type: implementation
project: finbrief-analyzer
topic: stock-screening
created: 2026-10-08
status: done
source_task: "[[2026-10-08_stock-screening]]"
commits: [a985d99]
blog_candidate: false
tags: [implementation]
---

# 🛠️ 구현: stock-screening Task 3 — 일봉·종목군 스키마와 저장소

이력을 쌓을 자리를 만들었다. 아직 아무도 이 코드를 부르지 않는다.

## 한 일
- `screen/models.py`: `Bar`, `Member`, `Exchange`(KOSPI·KOSDAQ·SP500).
- `store/tables.py`: `price_bars`(유일 제약 종목·날짜), `universe_members`(유일 제약 거래소·종목).
- `store/price_bars.py`: `add_bars`, `history`, `last_days`, `delete_symbol`.
- `store/universe.py`: `replace_members`, `members`, `built_on`.
- 마이그레이션 `0002_price_bars_universe.py`.
- 테스트 17개 (일봉 11, 종목군 6). 기존 마이그레이션 왕복·열 비교 테스트가 새 테이블도 자동으로 본다.

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| `Bar` 의 시·고·저는 선택값 | 필수 | PoC 결정. 매일 덧붙이는 네이버 순위 조회에는 시·고·저가 없다. 규칙은 종가와 거래량만 쓴다 |
| 넣기는 **읽고 나서 없는 날만** 넣는다 | `ON CONFLICT DO NOTHING` | 방언 전용 구문을 쓰지 않는다(delivery PoC 6번). 이력을 쓰는 작업은 한 번에 하나만 돈다는 전제를 독스트링에 적었다 |
| 이미 있는 날은 **덮어쓰지 않는다** | 새 값으로 갱신 | 값이 달라졌다면 수정주가가 바뀐 것이다. 한 행만 고치면 앞뒤가 어긋난다. 그 종목을 통째로 다시 받는 것이 Task 6 의 일이다 |
| 한 묶음 안의 같은 (종목, 날짜)는 첫 번째만 | 오류 | 순위 조회가 장중에 같은 종목을 두 페이지에 줄 수 있다 (PoC) |
| 종목군에 `position` 열 | 순서 없음 | 시가총액 순위 순서를 보존한다. 테스트와 로그에서 순서가 일정하다 |
| 종목군은 거래소 단위로 **통째로 교체** | 차이만 반영 | 한 달에 한 번이고 수백 행이다. 교체가 단순하고 "이전 구성이 남는" 실수가 없다 |
| 거래량은 `BigInteger` | `Integer` | 미국 대형주의 하루 거래량이 32비트를 넘는다. 테스트로 고정했다 |
| 가격은 `Float` | `Numeric` | SQLite 에서 `Numeric` 은 경고가 나고, 규칙은 비율만 쓴다 |
| `Exchange` 를 `Market` 과 따로 둔다 | `Market` 재사용 | `Market` 은 메일의 묶음이고 `Exchange` 는 종목군의 조각이다. KOSPI 와 KOSDAQ 은 메일에서 한 묶음이지만 종목군에서는 따로 자른다 |

## 막혔던 부분 / 해결 과정
없음. 종목군 중복 제거를 "두 번 뒤집기"로 쓰다가 순서가 뒤집혀 테스트가 잡았다. `setdefault` 로 바꿨다.

## 검증 결과
```
uv run pytest tests/store   → 40 passed
uv run ruff check .         → All checks passed!
uv run mypy                 → Success: no issues found in 74 source files
uv run pytest               → exit 0, 커버리지 97%
```
수동 확인 (로컬 postgres 18.6): `alembic upgrade head` → `downgrade -1` → `upgrade head` → `0002 (head)`, 테이블 5개.

## 발견한 이슈 (이번 범위 밖)
- [ ] 스크리닝 때 850종목의 이력을 종목마다 한 번씩 읽으면 조회가 850번이다. 한 번에 읽는 함수가 Task 8 에서 필요할 수 있다.

## 남은 것
- [ ] 없음.
