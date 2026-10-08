---
type: implementation
project: finbrief-analyzer
topic: stock-screening
created: 2026-10-08
status: done
source_task: "[[2026-10-08_stock-screening]]"
commits: [a5657e5]
blog_candidate: false
tags: [implementation]
---

# 🛠️ 구현: stock-screening Task 6 — 이력 갱신과 처음 받기 명령

일봉이 실제로 쌓인다. 처음 받기와 매일 갱신이 같은 함수다 — 시간 상한이 있느냐만 다르다.

```bash
uv run python -m finbrief_analyzer.jobs.backfill_prices
```

## 한 일
- `screen/history.py`: `update_history`, `HistorySources`, `UpdateReport`, `differs`.
- `jobs/backfill_prices.py`: `main`, `run`, `open_deps`, `ScreenDeps`.
- `store/price_bars.py`: `last_bars` (종목별 마지막 행을 한 번에).
- `screen/universe.py`: `pages_for` 를 밖으로 꺼냈다.
- `screen/ranking.py`: 요청에 브라우저 형태의 User-Agent.
- 테스트 23개 (이력 18, 명령 4, 저장소 1).

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| 처음 받기와 매일 갱신이 **같은 함수** | `backfill` 과 `update_recent` 를 따로 | 태스크 메모는 둘로 나눴다. 써 보니 "이력이 없으면 통째로, 있으면 덧붙이기"가 종목마다 갈릴 뿐이다. 종목군에 새로 들어온 종목도 같은 길로 처리된다 |
| **마감이 끝난 날만** 저장 (`expected_session`) | `marketStatus` 문자열로 판정 | 장 마감 뒤의 상태값을 아직 보지 못했다. 날짜 비교는 그 값에 기대지 않는다. 12:04 KST 실행에서 국내 최신 행이 10-07 로 들어갔다 |
| 국내 덧붙이기는 "전일 종가가 저장된 값과 같은가"로 이어 붙인다 | 겹쳐 받기 | PoC 결정. 순위 조회는 하루치뿐이라 겹칠 날이 없다. 대신 행이 전일 대비 값을 준다 |
| 4일 넘게 비었으면 통째로 다시 받는다 | 순위 조회의 하루치만 넣는다 | PC 가 꺼져 있던 날들을 건너뛰고 오늘만 넣으면 이력에 구멍이 나는데 전일 종가는 우연히 맞을 수 있다. 4일은 주말 + 공휴일 하루 |
| 미국은 **저장된 마지막 날부터** 다시 받아 그 날의 종가를 비교 | 최근 5일 고정 | 종목마다 마지막 날이 다르다. 가장 오래된 마지막 날부터 받으면 모든 종목의 겹치는 날이 응답에 있다 |
| 어긋나면 **받은 뒤에** 지우고 넣는다 (한 트랜잭션) | 지우고 받는다 | 받기가 실패했을 때 저장된 이력을 잃지 않는다. 테스트로 고정했다 |
| 종목 하나가 한 트랜잭션 | 전체가 한 트랜잭션 | 처음 받기가 중간에 끊겨도 받은 종목은 남는다. 다시 실행하면 이어서 받는다 |
| 순위 조회가 죽으면 종목별 조회로 대신한다 | 그날 국내 갱신을 건너뛴다 | 느리지만(350종목 약 2분) 구멍이 생기지 않는다. 시간 상한에 걸리면 남은 종목은 다음 실행으로 넘어간다 |
| 거래가 없던 종목은 다시 받지 않는다 | 매번 다시 받는다 | 거래정지 종목의 순위 행은 마지막 거래일을 그대로 가리킨다. 매 실행마다 통째로 다시 받게 되는 것을 막는다 |
| 허용 오차 상대 0.5% | 완전 일치 | 부동소수 비교이고, 미국은 배당락 때 과거 가격이 조금씩 조정된다. 넘으면 그 종목만 다시 받으면 되므로 낮게 잡아도 비용이 작다 |
| 실패한 종목이 있어도 종료 코드 0 | 1 | 다음 실행이 다시 시도한다. 0 이 아닌 코드는 "명령 자체가 죽었다"에만 쓴다 |
| 시각과 시계를 주입 | `datetime.now()` 직접 | 장중·마감 뒤·시간 초과를 테스트가 만든다 |

## 막혔던 부분 / 해결 과정
없음. 이번에는 구현을 먼저 쓰고 테스트를 뒤에 썼다 (갱신 규칙의 갈래를 코드로 적어 봐야 테스트할 경우가 정리됐다). 테스트 18개가 처음부터 전부 통과해서, 일부러 규칙 두 개를 망가뜨려 테스트가 잡는지 확인했다:
- 허용 오차를 10 으로 (어긋남을 못 봄) → 4개 실패.
- "마감된 날만" 조건을 항상 참으로 → 2개 실패.

## 검증 결과
```
uv run pytest tests/screen/test_history.py tests/jobs  → 통과 (history.py 100%)
uv run ruff check .                                    → All checks passed!
uv run mypy                                            → Success: no issues found in 86 source files
uv run pytest                                          → exit 0, 커버리지 97%
```
수동 확인 (2026-10-08 12:04 KST 장중, 로컬 postgres 18.6):
```
1회차: universe rebuilt: kospi, kosdaq, sp500
       price history: added=229879 loaded=853 reloaded=0 failed=0      (201초)
2회차: universe rebuilt: none
       price history: added=0 loaded=0 reloaded=0 failed=0             (3초)

universe_members: kospi 200, kosdaq 150, sp500 503
price_bars: 853종목, 229,879행, 2025-09-03 ~ 2026-10-07
```
- 장중에 실행했지만 국내 최신 행은 10-07 이다. 진행 중인 10-08 은 저장되지 않았다.
- 250행 미만인 종목이 13개 (최소 1행). 최근 상장·편입 종목이고, 52주 규칙에서 "이력 부족"으로 빠진다.

## 발견한 이슈 (이번 범위 밖)
- [ ] 미국 한 종목의 마지막 행이 10-05 다. 거래가 멈춘 종목으로 보이고, 실행마다 그 종목 하나를 다시 조회한다(값은 안 바뀐다). 비용은 요청 1회다.
- [ ] 순위 조회로 하루치를 덧붙이는 경로는 장 마감 뒤에 실행해야 실제로 탄다. 오늘 15:30 이후 실행에서 처음 확인된다.
- [ ] 미국 장중(한국 밤)에 실행하면 Yahoo 가 당일 행을 준다. 날짜 비교로 걸러 내지만 실제 실행으로는 아직 보지 못했다.

## 남은 것
- [ ] 장 마감 뒤 실행에서 `added` 가 국내 350 안팎으로 나오는지 확인.
