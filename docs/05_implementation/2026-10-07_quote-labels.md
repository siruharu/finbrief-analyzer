---
type: implementation
project: finbrief-analyzer
topic: data-sources
created: 2026-10-07
status: done
source_task: "[[2026-10-07_data-sources]]"
commits: [b9599a0]
blog_candidate: false
tags: [implementation]
---

# 🛠️ 구현: data-sources Task 13 — 시세의 표시 이름·시장·등락폭

Task 10 을 끝내며 남긴 이슈 두 개(표시 이름이 없다, 금리 등락이 `%` 로 계산된다)를 사용자 결정(2026-10-07)에 따라 닫았다.

## 한 일
- `Quote` 에 `name`, `market` 필드와 `change`(단위 그대로의 차이), `change_bp`(bp) 속성을 추가했다.
- `EcosSeries` 에 `name`, `market` 을 넣었다. ECOS 어댑터가 자기 시세에 직접 붙인다.
- `collect_snapshot` 이 시세 어댑터의 결과에 `Settings.quote_symbols` 의 이름·시장을 붙인다.
- 기본 표시 이름을 한국어로 맞췄다 (나스닥, 다우존스, 미 국채 10년).
- 테스트 8개 추가 (모델 5, 금리 2, 조립 1).
- `docs/04_tasks/2026-10-07_delivery-channels.md` 에 렌더러가 따라야 할 결정을 적었다.

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| 이름·시장을 **스냅샷 안의 `Quote`** 에 싣는다 | 렌더러가 `Settings` 에서 찾는다 | 발송 쪽이 수집 설정을 몰라도 된다. 스냅샷 하나만 넘기면 그릴 수 있다. Task 2 에서 "조립에서 붙인다"고 해 놓고 자리가 없던 것을 메운다 |
| 시세 어댑터는 여전히 심볼만 안다. 붙이는 것은 조립 | 어댑터가 이름을 채운다 | Task 2 의 결정 그대로다. 출처 세 곳이 같은 표를 들고 있지 않게 한다 |
| ECOS 는 어댑터가 직접 붙인다 | 조립이 붙인다 | ECOS 계열은 통계코드와 함께 `rates.py` 한 곳에 정의돼 있다. 이름만 다른 곳에 두면 계열을 추가할 때 두 군데를 고쳐야 한다 |
| 금리 등락은 **bp** | %p | 사용자 결정은 "%p 나 bp". 시장 금리는 "2.8bp 상승"으로 말하는 것이 관행이고, 기준금리 변경(25bp)도 같은 단위로 읽힌다. 단위를 하나로 통일했다 |
| `change_bp` 를 모델에 둔다 | 렌더러가 `change * 100` | "금리에는 `change_pct` 를 쓰면 안 된다"는 지식이 렌더러 코드에 흩어지지 않게 한다. 독스트링에 적었다 |
| 원/달러는 `Market.FX`, 등락은 `%` 와 원 | 금리와 같은 취급 | 값의 단위가 원이다. bp 가 아니다 |
| 휴장 판정이 `Quote.market` 을 읽는다 | 심볼 → 시장 표를 따로 만든다 | 이름을 붙이고 나니 같은 정보가 이미 시세에 있다. 함수 인자가 하나 줄었다 |

## 막혔던 부분 / 해결 과정
없음.

## 검증 결과
```
$ uv run pytest tests/collect   (구현 전)
ERROR tests/collect/test_rates.py - TypeError: EcosSeries.__init__() got an unexpected keyword...

$ uv run pytest
TOTAL                                                741      5    99%
176 passed, 1 warning in 2.43s
$ uv run ruff check . → All checks passed!
$ uv run mypy         → Success: no issues found in 36 source files
```
실제 출처로 국내 개장 슬롯을 돌렸다 (2026-10-07 저녁 KST):
```
S&P 500              us     7818.930  +0.58%
나스닥               us    27599.789  +0.45%
다우존스             us    51521.281  +0.49%
미 국채 10년         rate      5.269  -4.2bp
한국은행 기준금리    rate      3.000  +0.0bp
국고채 3년           rate      3.961  +2.8bp
국고채 10년          rate      4.376  +0.7bp
원/달러 매매기준율   fx     1343.400  -1.11%
missing ()  news 51
```

## 사용자 결정 중 코드가 아닌 것
- **국내 공휴일의 브리핑**: 보낸다. 전하려는 시장이 휴장이었으면 안내를 싣는다. 발송 쪽 규칙이라 `delivery-channels` 태스크 문서에 적었다.
- **뉴스를 몇 건으로 추릴지**: 수집은 출처당 15건·전체 80건까지만 한다. 고르는 일은 LLM 요약 단계이고 리서치부터 필요하다.

## 발견한 이슈 (이번 범위 밖)
- [ ] `APP_QUOTE_SYMBOLS` 로 심볼을 바꾸면 이름·시장도 같이 줘야 한다. ECOS 계열은 환경변수로 바꿀 수 없다(코드에 있다).
- [ ] LLM 요약 단계는 리서치·분석·플랜이 없다. `/research` 부터 시작해야 한다.

## 남은 것
- [ ] 없음.
