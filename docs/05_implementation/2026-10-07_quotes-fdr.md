---
type: implementation
project: finbrief-analyzer
topic: data-sources
created: 2026-10-07
status: done
source_task: "[[2026-10-07_data-sources]]"
commits: []
blog_candidate: false
tags: [implementation]
---

# 🛠️ 구현: data-sources Task 4 — FinanceDataReader 시세 어댑터

## 한 일
- `collect/quotes_fdr.py`: `FdrQuoteProvider`, `_to_quote`, 기본 조회 함수 `_fdr_fetch`.
- `tests/collect/test_quotes_fdr.py`: 11개. 전부 가짜 조회 함수로 돌고 네트워크를 타지 않는다.
- 개발 의존성에 `pandas-stubs` 추가.

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| 심볼 하나가 실패하면 그 심볼만 빼고 나머지를 돌려준다. 전부 실패했을 때만 `CollectError` | 하나라도 실패하면 예외 | Task 5 의 폴백이 "1차가 실패한 심볼만 예비로" 넘겨야 한다. 요청한 심볼과 돌아온 심볼의 차이가 곧 실패 목록이다 |
| 마지막 유효 행이 조회 시작일보다 앞이면 `stale` 오류 | 돌아온 값을 그대로 신뢰 | PoC 의 `KS11` 처럼 예외 없이 멈춘 출처가 있다. 범위 밖 행을 돌려주는 경우도 봤다(`IXIC` 주말 조회). 3주 묵은 종가가 실리는 것을 막는다 |
| 조회 기간 10일 | 2~3일 | 추석 같은 연휴 주에도 전일 종가가 창 안에 남는다 |
| `Close` 열만 지원, 없으면 오류 | 첫 번째 숫자 열을 쓰기 | `FRED:` 심볼은 열 이름이 심볼명이다. 추측해서 맞추면 다른 값을 종가로 실을 수 있다 |
| NaN 종가 행은 버린 뒤 마지막 두 행 | 마지막 두 행을 그대로 | Yahoo 표에 미완성 행이 NaN 으로 들어온다 |
| `today` 를 생성자로 주입 | `date.today()` 를 직접 호출 | 조회 기간과 stale 판정이 날짜에 기대므로 테스트가 날짜를 고정해야 한다 |
| 라이브러리 import 를 기본 조회 함수 안에서 | 모듈 최상단 | 이 모듈을 import 하는 것만으로 pandas·plotly 가 로드되지 않게 한다. 앱 기동과 `/health` 가 무거워지지 않는다 |
| `frame` 은 `Any` 로 받고 `_to_quote` 안에서 `float`·`date` 로 바꾼다 | 어댑터에서 pandas 타입 표기 | pandas 는 타입 스텁을 싣지 않는다. 런타임 코드가 스텁 패키지에 기대지 않게 하고, `Any` 는 함수 하나에 가둔다 |
| 테스트용으로 `pandas-stubs` | mypy override 에 `pandas.*` 추가 | 테스트가 실제 DataFrame 을 만든다. override 로 끄면 테스트 코드의 타입 검사가 통째로 빠진다 |

`_fdr_fetch` 는 실제 네트워크 호출이라 `# pragma: no cover` 로 커버리지에서 뺐다. 대신 아래처럼 한 번 실제로 돌려 봤다.

## 막혔던 부분 / 해결 과정
없음.

## 검증 결과
```
$ uv run pytest tests/collect/test_quotes_fdr.py   (구현 전)
ERROR tests/collect/test_quotes_fdr.py
1 warning, 1 error in 1.49s

$ uv run pytest
src\finbrief_analyzer\collect\quotes_fdr.py      46      0   100%
TOTAL                                           169      4    98%
34 passed, 1 warning in 0.62s
$ uv run ruff check .
All checks passed!
$ uv run mypy
Success: no issues found in 16 source files
```
실제 조회 (2026-10-07 17시경 KST, 기본 심볼 6개 + 일부러 넣은 `KS11`):
```
quote skipped: fdr: KS11: no data
^KS11  2026-10-07  6803.90   전일 6941.39  -1.98%
^KQ11  2026-10-07   898.43   전일  919.92  -2.34%
US500  2026-10-06  7818.93   전일 7773.95  +0.58%
IXIC   2026-10-06 27599.79   전일 27477.31 +0.45%
DJI    2026-10-06 51521.28   전일 51267.90 +0.49%
US10YT 2026-10-06     5.269  전일    5.311 -0.79%
```

## 발견한 이슈 (이번 범위 밖)
- [ ] 금리(`US10YT`)의 등락을 `%` 로 보여 주면 5.311 → 5.269 가 "-0.79%" 가 된다. 금리는 보통 bp(-4.2bp)로 말한다. `Quote.change_pct` 와 별개로 표시 방식을 정해야 한다 — 렌더링(delivery-channels Task 2) 또는 Task 10 에서.
- [ ] 장중에 조회하면 당일 행이 미완성 값으로 들어오는지는 여전히 확인하지 못했다. 슬롯 시각이 장 마감 뒤라 지금은 해당 없다.

## 남은 것
- [ ] 없음. 다음은 Task 5(예비 어댑터와 폴백). 국내 지수의 예비는 네이버다.
