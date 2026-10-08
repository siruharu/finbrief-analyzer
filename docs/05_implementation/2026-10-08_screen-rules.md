---
type: implementation
project: finbrief-analyzer
topic: stock-screening
created: 2026-10-08
status: done
source_task: "[[2026-10-08_stock-screening]]"
commits: [629287a]
blog_candidate: false
tags: [implementation]
---

# 🛠️ 구현: stock-screening Task 7 — 규칙 (52주 고가 근접·거래량 급증)

일봉 목록을 받아 점수를 내는 순수 함수들이다. DB·네트워크·pandas 를 모른다. 나중의 백테스트가 같은 함수를 쓴다.

## 한 일
- `screen/rules.py`: `high_ratio`, `volume_ratio`, `trading_value`, `change_pct`, `rank`, `Score`.
- `screen/models.py`: `Rule`, `ScreenHit`, `ScreenResult` (Task 8 이 채운다).
- 테스트 18개 (`tests/screen/test_rules.py`).

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| 52주를 **달력 기간**(마지막 날로부터 52주)으로 센다 | 252거래일 | 태스크 메모는 "252거래일"이라고 적었지만, PoC 에서 국내 종목의 1년치가 246행이었다. 거래일 수로 세면 국내 종목 대부분이 "이력 부족"으로 빠진다. 휴장일 수가 나라마다 다르다 |
| 이력이 52주에 못 미치면 점수 없음 (시작이 10일까지 늦는 것은 허용) | 있는 만큼으로 계산 | 상장 6개월 된 종목의 상장 후 최고가를 "52주 신고가"라고 부르지 않는다. 10일의 여유는 연휴·주말로 첫 행이 늦게 시작하는 경우를 위한 것이다 |
| 종가 기준 | 장중 고가 | George·Hwang 의 정의. 매일 덧붙이는 행에는 고가가 없기도 하다 |
| 거래량 평균에서 **당일을 뺀다** | 당일 포함 21일 평균 | 급증한 날이 자기 평균을 끌어올려 비율이 낮아진다. 테스트로 고정했다 |
| 평균이 0 이면 점수 없음 | 무한대 | 거래정지에서 풀린 종목이 항상 1위가 된다 |
| 점수가 없으면 `None` | 0 | 0 은 "가장 나쁨"이라는 뜻이 된다. 판단할 수 없는 종목은 순위에서 빠져야 한다 |
| 동점은 당일 등락률 → 종목코드 순 | 종목코드만 | PoC 에서 52주 최고가인 종목이 하루에 9개 나왔다. 종목코드만으로 5개를 고르면 임의의 선택이 된다 |
| 함수가 스스로 날짜순으로 정렬 | 정렬됐다고 가정 | 입력 순서에 결과가 달리면 찾기 어려운 버그가 된다. 850종목 × 250행의 정렬은 비용이 작다 |
| `trading_value` 도 당일 제외 | 당일 포함 | 거래량 평균과 같은 창을 쓴다. "평소에 거래가 되는 종목인가"를 묻는 값이다 |

## 막혔던 부분 / 해결 과정
없음. 테스트와 구현을 이어서 작성해 실패하는 모습을 따로 보지 않았다. 대신 기대값은 구현을 보지 않고 손으로 계산해 적었다 (예: 조용한 20일 1,000주 뒤 5,000주 → 5배).

## 검증 결과
```
uv run pytest tests/screen/test_rules.py  → 18 passed
uv run ruff check .                       → All checks passed!
uv run mypy                               → Success: no issues found in 76 source files
uv run pytest                             → exit 0, 커버리지 98%
```

## 발견한 이슈 (이번 범위 밖)
- [ ] 처음 받기는 52주 + 여유(10일)보다 길게 받아야 한다. Task 6 의 `screen_history_days` 기본값을 400일로 둔 이유다. 365일만 받으면 전 종목이 "이력 부족"이 된다.
- [ ] 52주 고가 비율의 상한은 1 이다. 동점이 흔하므로 등락률 기준이 사실상 순위를 정한다.

## 남은 것
- [ ] 없음.
