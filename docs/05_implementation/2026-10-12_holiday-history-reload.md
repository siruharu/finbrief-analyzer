---
type: implementation
project: finbrief-analyzer
topic: stock-screening
created: 2026-10-12
status: done
source_task: "[[2026-10-08_stock-screening]]"
commits: [cb8a9eb]
blog_candidate: true
tags: [implementation, stock-screening, history]
---

# 🛠️ 구현: stock-screening Task 12 — 국내 공휴일 뒤 전 종목 재수신 막기

> 단계 생략 — 리서치·분석·플랜 없이 `/implement` 로 바로 갔다. [[2026-10-12_local-schedule]] 구현 중 실측으로 발견한 버그이고, 원인이 코드 두 줄로 좁혀져 있었다. `task add` 로 Task 12 를 추가했다.

## 한 일
- `screen/ranking.py` — `NaverRanking.trading_days(exchange)`: 지수 일별 시세(`/api/index/{KOSPI|KOSDAQ}/price`)의 날짜 목록. 거래소가 **실제로 거래한 날**이다. 진행 중인 오늘도 들어 있다.
- `screen/history.py` — `_kr_settled()`: 달력 추정치(`expected_session`)를 지수 거래일로 보정한다. 추정치 이하의 가장 늦은 거래일이 마지막 완료 세션. 지수 조회가 실패하면 경고를 남기고 추정치를 그대로 쓴다(이전 동작).
- `screen/history.py` — `_continues()` 의 전일가 비교 허용폭을 `REFERENCE_TOLERANCE`(15%)로 분리. 동일 날짜 종가 비교(`TOLERANCE` 0.5%)는 그대로다.
- 테스트: history 4개(공휴일 뒤 재수신 없음 / 진짜 빠진 세션은 재수신 / 지수 실패 시 달력으로 / NXT 기준가 차이는 추가로 처리), ranking 2개. 가짜 `Ranking` 3곳에 `trading_days` 추가.

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| **지수 거래일**로 마지막 세션을 정한다 | 공휴일 표를 코드에 둔다 | 표는 매년 손으로 갱신해야 하고 임시 휴장을 모른다. 지수 시세는 거래소가 실제로 열었던 날을 그대로 말한다. 호출 1회 |
| 전일가 비교로 "사이에 세션 없음"을 판정하지 않는다 (첫 시도에서 되돌림) | 진행 중 행의 `prev_close` 가 저장 종가와 같으면 최신으로 본다 | 실측에서 350종목 중 153개가 어긋났다. 네이버의 전일가는 **NXT 야간 시장을 합친 기준가**라 KRX 종가와 최대 10% 다르다. 그 값으로 "빠진 세션"을 판정하면 실제 세션을 놓친 종목을 영영 못 채운다 |
| 전일가 비교 허용폭 15% | 0.5% 유지 / 비교 삭제 | 비교의 목적은 분할·대규모 조정 감지다. 분할은 2배 이상, NXT 야간 가격 제한은 ±10%. 15% 는 둘을 가른다. 0.5% 로 두면 매일 밤 22:30 실행에서 NXT 종목 ~150개가 FDR 로 재수신된다 |
| 지수 실패 시 달력 추정치로 | 실패로 끝낸다 | 재수신은 비용이지 오류가 아니다. 보조 정보가 없을 때 이전처럼 동작하면 된다 |
| 미국 경로는 손대지 않음 | 같은 보정 | 미국은 같은 날짜의 종가끼리 겹쳐 비교하므로 휴일에도 "겹치는 날 없음 → 재수신"이 아니라 `stale` 목록에 들어가 배치 1회로 끝난다. 실측 US 재수신 0 |

## 막혔던 부분 / 해결 과정
**증상** — 2026-10-12(월, 전 금요일이 한글날) 실행마다 `price history: reloaded=353`(그리고 350). 국내 전 종목을 FDR 로 다시 받느라 2분, 외부 호출 350회.

**가설 1** — `expected_session(KR, 월 14:00)` = 10-09. 저장된 마지막 날 10-08 < 10-09 이고, 진행 중인 오늘(10-12) 행은 `traded_on <= settled` 에서 걸러져 `_continues` 로도 못 가니 `_load_kr(replace=True)`. 확인: `expected_session` 을 직접 호출해 10-09 를 봤다.

**첫 수정과 실측** — 진행 중 행의 `prev_close` 가 저장 종가와 같으면 "사이에 완료 세션 없음"으로 보는 지름길을 넣었다. 테스트는 통과했지만 실측은 `reloaded=153`. 분류해 보니 197개는 전일가가 맞고 **153개는 ~1% 어긋났다**(SK스퀘어 저장 1,059,000 / 네이버 전일가 1,050,000).

**가설 2** — 10-09 에 실제 세션이 있었나? FDR 과 네이버 일별 시세 둘 다 10-08 다음이 10-12 다. 세션은 없었다. 그럼 1,050,000 은 무엇인가 → 원시 응답의 `overMarketPriceInfo` 를 보니 NXT 야간 거래 정보가 따로 있고, `compareToPreviousClosePrice` 가 그 기준으로 계산돼 있었다. **네이버의 전일 대비는 KRX+NXT 통합 기준가 대비**다. NXT 에서 거래되는 대형주(코스피)만 어긋나고 소형 코스닥은 맞는 것과 일치한다.

**함의** — 이 어긋남은 공휴일과 무관하게 **매일** 있다. 22:30 실행에서 완료 행(`traded_on`=오늘)이 `_continues` 의 0.5% 비교를 통과하지 못해 ~150종목이 매일 FDR 로 재수신되고 있었을 것이다(로그가 없어 과거는 확인 못 함).

**해결** — 지름길을 버리고 마지막 세션 자체를 지수 거래일로 바로잡았다(가설 1 의 근본 원인). 전일가 비교는 분할 감지만 하도록 허용폭을 15% 로 분리했다(가설 2).

## 검증 결과
```
uv run pytest tests/screen tests/jobs  → 121 passed
uv run ruff check . / ruff format      → 통과
uv run mypy                            → Success: no issues found in 90 source files
task done 12 (전체 pytest 포함)         → 통과

실측 (2026-10-12 14:40 KST, 장중, 로컬 DB)
  수정 전: UpdateReport(added=93159, reloaded=353) ~130s  /  첫 수정: reloaded=153, 73.1s
  수정 후: calendar guess 2026-10-09 | index says [10-12, 10-08, 10-07, 10-06, 10-02] | settled 2026-10-08
          UpdateReport(added=0, loaded=0, reloaded=0, failed=(), skipped=0) in 1.6s
```

## 발견한 이슈 (이번 범위 밖)
- [ ] `rank_bar(row)` 로 저장하는 종가가 22:30 시점에 KRX 정규장 종가인지 NXT 야간 가격인지 확인하지 않았다. 오늘 밤 22:30 실행 뒤 `price_bars` 의 10-12 종가를 네이버 일별 시세와 대조한다.
- [ ] 외부 호출 횟수·소요 시간을 `price history` 로그 한 줄에 함께 남기면 이런 회귀를 바로 본다.

## 남은 것
- [ ] 10-13(화) 09:00 kr_open 로그에서 `reloaded=0` 확인.
