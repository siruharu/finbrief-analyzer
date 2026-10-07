---
type: implementation
project: finbrief-analyzer
topic: data-sources
created: 2026-10-07
status: done
source_task: "[[2026-10-07_data-sources]]"
commits: [4d3babc]
blog_candidate: false
tags: [implementation]
---

# 🛠️ 구현: data-sources Task 10 — 수집 조립과 휴장 판정

이 주제의 마지막 Task 다. `collect_snapshot(slot, now, providers, symbols)` 가 `MarketSnapshot` 하나를 돌려준다.

## 한 일
- `collect/service.py`: `collect_snapshot`, `Providers`, `expected_session`, 내부 함수들.
- `collect/factory.py`: `build_providers(settings, client)`, `make_client(settings)`.
- `tests/collect/test_service.py`: 25개. 조립 테스트는 가짜 제공자만 쓴다.
- 의존성에 `tzdata` 를 명시했다.

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| 국내 개장 슬롯은 미국 지수 + 금리, 미국 개장 슬롯은 국내 지수 + 금리 | 두 슬롯 모두 전체 | 각 브리핑은 "직전에 끝난 시장"을 전한다. `Settings.quote_symbols` 의 `market` 으로 고른다 |
| 뉴스 기준 시각은 슬롯별 고정 폭 (국내 개장 11시간, 미국 개장 14시간) | "직전 슬롯의 실제 실행 시각"을 저장해 두고 읽기 | 상태를 컨테이너 안에 두지 않는다는 규칙이 있고, 수집 계층에는 DB 가 아직 없다. 두 슬롯(약 09:00·22:30 KST) 간격에 여유를 더한 값이다. 연휴 뒤에도 폭이 늘지 않아 입력이 폭주하지 않는다 |
| 휴장 판정: 지수의 기준일이 "지금 시점에 마감이 지난 가장 최근 평일"보다 앞이면 그 시장은 휴장 | 공휴일 달력 | 달력은 해마다 손봐야 하고 임시 휴장을 모른다. 시세 자체가 답을 갖고 있다. 주말은 평일로 되감아 월요일 아침에 금요일 종가를 정상으로 본다 |
| 휴장 판정은 `Market.KR`·`Market.US` 에만 | 모든 심볼 | 기준금리는 이틀 늦게 나온다(Task 6 에서 확인). 금리·환율에 같은 규칙을 걸면 매번 휴장이 된다 |
| 뉴스는 출처당 15건, 전체 80건, 최신순 | 전체 상한만 | 실제로 12시간에 339건이고 연합뉴스가 과반이었다. 전체 상한만 두면 한 언론사가 다 차지한다 |
| 조립은 뉴스를 시각으로 다시 거르지 않는다 | `since` 로 한 번 더 | DART 는 발행 시각이 00:00 이라 다시 거르면 전부 빠진다. 기준 시각 적용은 각 제공자의 일이다 |
| 누락 목록에는 **시세는 심볼**, 그 밖은 **출처 이름** | 전부 출처 이름 | 시세는 폴백을 거치므로 "어느 출처가 실패했나"보다 "어느 지수가 없나"가 브리핑에 필요한 정보다 |
| `CollectError` 외의 예외도 잡고 스택을 로그에 남긴다 | 도메인 예외만 | 출처 하나의 라이브러리 버그로 브리핑 전체가 죽지 않게 한다. 폴백(Task 5)과 같은 규칙 |
| `now` 에 시간대가 없으면 `ValueError` | 그냥 진행 | 이건 출처 장애가 아니라 호출자의 버그다. 조용히 9시간 어긋난 휴장 판정을 하는 것보다 낫다 |
| `build_providers` 는 클라이언트를 **받는다** | 안에서 만든다 | 닫을 책임이 호출자에게 있어야 한다. `make_client` 를 따로 뒀다 |
| `tzdata` 를 의존성에 명시 | pandas 가 끌고 오는 것에 기대기 | `service.py` 가 `zoneinfo` 를 직접 쓴다. 슬림 컨테이너 이미지에 시스템 시간대 자료가 없을 수 있다 |

## 막혔던 부분 / 해결 과정
없음.

## 검증 결과
```
$ uv run pytest tests/collect/test_service.py   (구현 전)
ERROR tests/collect/test_service.py
1 warning, 1 error in 0.13s

$ uv run pytest
src\finbrief_analyzer\collect\factory.py              30      1    97%   20
src\finbrief_analyzer\collect\service.py              88      0   100%
TOTAL                                                723      5    99%
166 passed, 1 warning in 1.73s
$ uv run ruff check .
All checks passed!
$ uv run mypy
Success: no issues found in 36 source files
```
`factory.py` 의 20행은 `make_client` 다 (실제 클라이언트 생성).

실제 출처 전체로 두 슬롯을 돌렸다 (2026-10-07 17:16 KST, Marketaux 는 슬롯당 1회로 줄여서):
```
== kr_open
   US500   2026-10-06  7818.93   +0.58      KR_BASE_RATE 2026-10-05  3.0     0.00
   IXIC    2026-10-06 27599.789  +0.45      KR3YT        2026-10-07  3.961  +0.71
   DJI     2026-10-06 51521.281  +0.49      KR10YT       2026-10-07  4.376  +0.16
   US10YT  2026-10-06     5.269  -0.79      USD/KRW      2026-10-07  1343.4 -1.11
   news 51 {mk.co.kr: 15, yna.co.kr: 15, hankyung.com: 15, seekingalpha.com: 2, thefintechtimes.com: 1, dart: 3}
   missing ()  closed []
== us_open
   ^KS11   2026-10-07  6803.9    -1.98
   ^KQ11   2026-10-07   898.43   -2.34
   (금리·환율·뉴스는 위와 같음)
   missing ()  closed []
```
두 슬롯을 같은 시각에 돌린 것이라 뉴스가 같다. 실제 슬롯 시각(09:00, 22:30 KST)에 돌린 것은 아니다.

## 발견한 이슈 (이번 범위 밖)
- [ ] **스냅샷에 표시 이름이 없다.** `Quote` 는 심볼만 갖는다. `^KS11` → "KOSPI" 는 `Settings.quote_symbols` 에 있지만 ECOS 계열(`KR3YT`, `USD/KRW` 등)의 이름은 어디에도 없다. 렌더러(delivery-channels Task 2)가 필요로 한다. Task 2 노트에서 "조립에서 붙인다"고 했는데 `MarketSnapshot` 에 자리가 없어 붙이지 못했다.
- [ ] **금리의 등락이 `%` 로 계산된다** (국고채 3년 +0.71%). %p·bp 로 보여야 한다. 표시 단위 결정이 아직 없다.
- [ ] **슬롯 자신의 시장이 휴장인 날**(예: 국내 공휴일의 국내 개장 브리핑)을 보낼지 말지는 여기서 판정하지 않는다. 스냅샷은 시세를 가져온 시장만 판정한다.
- [ ] 출처가 종가를 늦게 올리면 휴장으로 오판한다. 슬롯 시각이 마감 3시간 이상 뒤라 지금은 여유가 있다.
- [ ] 뉴스 51건은 메일 한 통에 싣기엔 많다. 고르는 단계(LLM 요약)의 분석이 없다.
- [ ] 뉴스 기준 폭(11·14시간)은 슬롯 시각이 바뀌면 함께 바꿔야 한다. 슬롯 시각은 delivery-channels Task 8 의 스케줄에 있다.

## 남은 것
- [ ] 이 주제(`data-sources`)의 Task 는 모두 끝났다. delivery-channels Task 7 이 `collect_snapshot` 과 `build_providers` 를 쓴다.
