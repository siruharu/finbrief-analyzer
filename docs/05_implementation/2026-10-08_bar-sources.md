---
type: implementation
project: finbrief-analyzer
topic: stock-screening
created: 2026-10-08
status: done
source_task: "[[2026-10-08_stock-screening]]"
commits: [062c91a]
blog_candidate: false
tags: [implementation]
---

# 🛠️ 구현: stock-screening Task 5 — 일봉 출처 어댑터

"한 번 받아 `Bar` 로 바꾸는 방법"만 만들었다. 무엇을 언제 받을지는 Task 6 이다.

## 한 일
- `screen/sources.py`: `frame_bars`, `rank_bar`, `FdrHistorySource`(국내, 종목당 1회), `YfBatchSource`(미국, 묶음), `BatchResult`.
- `Settings`: `screen_batch_size`(100), `screen_batch_pause_seconds`(1.0), `screen_history_days`(400, 최소 375).
- 테스트 19개 (`tests/screen/test_sources.py`). 네트워크 없이 fetch·download·sleep 을 주입한다.

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| 국내는 FDR 종목별, 미국은 yfinance 묶음 | 둘 다 한 방식 | PoC 실측. 국내 350종목은 종목별로 약 2분(처음 한 번), 미국 503종목은 묶음으로 17초. 국내 종목은 Yahoo 티커에 `.KS`/`.KQ` 구분이 필요하다 |
| 국내의 매일 값은 **순위 조회의 행을 그대로 `Bar` 로** (`rank_bar`) | 별도 어댑터 클래스 | Task 4 의 `NaverRanking` 이 이미 종가·거래량·거래일을 준다. 변환 한 줄이면 된다. 태스크 메모의 `KrDailySource` 는 만들지 않았다 |
| `Bar` 의 날짜는 **행이 가진 날짜** | 호출자가 준 날짜 | 태스크 메모는 "호출자가 날짜를 정해 준다"였다. PoC 뒤 순위 조회에 `localTradedAt` 이 있음을 확인했다. 받은 날짜가 마감된 날인지의 판정은 Task 6 이 한다 |
| 묶음이 **응답은 했는데 한 종목도 값이 없으면** 남은 묶음을 보내지 않는다 | 예외 종류(`YFRateLimitError`)로 판정 | `yf.download` 는 스레드 안의 종목별 오류를 삼키고 빈 표를 준다. 차단은 예외가 아니라 "전부 비어 있음"으로 나타난다. 계속 부르면 차단이 길어진다 |
| 묶음이 **예외로 죽으면** 그 묶음만 실패로 두고 계속한다 | 전체 중단 | 연결 오류 한 번으로 나머지 400종목을 버리지 않는다. 위의 "차단"과 구분한다 (`None` vs 빈 dict) |
| `fetch` 는 예외를 올리지 않고 `failed` 로 알린다 | `CollectError` | 일부만 성공하는 것이 정상 경로다. 실패한 종목은 Task 6 이 다음 실행에서 다시 대상으로 삼는다 |
| `auto_adjust=True` | 수정하지 않은 가격 | 분할이 반영되지 않으면 52주 고가 비율이 틀린다. PoC 에서 수정주가임을 확인했다 |
| `sleep` 주입 | `time.sleep` 직접 호출 | 테스트가 실제로 기다리지 않고, 쉰 횟수와 길이를 단언한다 |
| `screen_history_days` 의 최소값 375 | 제한 없음 | 52주 규칙이 364일 + 여유 10일의 이력을 요구한다. 그보다 짧게 설정하면 전 종목이 "이력 부족"으로 빠지는데 원인을 찾기 어렵다 |

## 막혔던 부분 / 해결 과정
없음. 첫 구현이 "죽은 묶음"과 "빈 응답"을 인스턴스 변수(`self._crashed`)로 구분했다. 테스트는 통과했지만 메서드가 숨은 상태를 남기는 모양이라 반환값(`None` / `{}`)으로 바꿨다.

## 검증 결과
```
uv run pytest tests/screen/test_sources.py  → 19 passed
uv run ruff check .                         → All checks passed!
uv run mypy                                 → Success: no issues found in 82 source files
uv run pytest                               → exit 0, 커버리지 98% (sources.py 100%)
```
실제 출처로 한 번 (2026-10-08, DB 에 쓰지 않음):
```
fdr 005930: 266행, 2025-09-03 ~ 2026-10-08 (마지막 행은 장중 값)
yf: NVDA 276행 ~2026-10-07 종가 237.47 / BRK-B 276행 종가 506.25 / failed ('NOSUCHTICKERX',)
single: AAPL 276행   ← 종목 하나짜리 묶음도 같은 경로
```

## 발견한 이슈 (이번 범위 밖)
- [ ] 국내 FDR 이력의 마지막 행은 장중이면 진행 중인 값이다 (위 005930). Task 6 이 마감된 날만 저장해야 한다.
- [ ] `frame_bars` 가 행을 하나씩 돈다. 850종목 × 276행에서 느린지는 Task 6 의 처음 받기에서 실측한다.

## 남은 것
- [ ] 없음.
