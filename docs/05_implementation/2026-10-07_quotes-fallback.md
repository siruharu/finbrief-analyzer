---
type: implementation
project: finbrief-analyzer
topic: data-sources
created: 2026-10-07
status: done
source_task: "[[2026-10-07_data-sources]]"
commits: [d66a444]
blog_candidate: false
tags: [implementation]
---

# 🛠️ 구현: data-sources Task 5 — 폴백 합성

예비 어댑터는 Task 11 로 떼어 냈다. 이 Task 는 합성만 한다.

## 한 일
- `collect/quotes_fallback.py`: `FallbackQuoteProvider`, `QuoteResult`, `BackupQuoteProvider`(프로토콜).
- `tests/collect/test_quotes_fallback.py`: 10개. 가짜 제공자만 쓴다.

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| 예비를 **목록**으로 받는다 | 설계 메모의 `(primary, backup)` 한 쌍 | 국내는 네이버, 미국은 yfinance 로 예비가 둘이 됐다. 각 예비에는 `supports()` 가 참인 심볼만 넘긴다 |
| `QuoteResult(quotes, missing)` 를 돌려주고 예외를 던지지 않는다 | `QuoteProvider` 처럼 예외 | 조립(Task 10)이 "시세 일부 누락"을 스냅샷의 누락 목록에 그대로 옮길 수 있다. 그래서 이 클래스는 `QuoteProvider` 가 아니다 — 독스트링에 적었다 |
| `CollectError` 외의 예외도 잡는다 | 도메인 예외만 | 서드파티 라이브러리(pandas, yfinance)의 예상 못 한 오류가 브리핑 전체를 죽이면 안 된다. 대신 `logger.exception` 으로 스택을 남긴다 |
| 앞선 제공자의 값이 이긴다 | 나중 값으로 덮기 | 1차가 답한 심볼을 예비가 덮으면 출처가 뒤섞인다 |
| 요청하지 않은 심볼의 답은 버린다 | 그대로 포함 | 결과가 요청 목록의 부분집합이어야 `missing` 계산이 맞는다 |
| 결과는 요청한 순서대로 | 답이 온 순서 | 브리핑의 지수 순서가 "누가 답했는지"에 따라 바뀌면 안 된다 |

설계 메모의 엣지 케이스 "1차가 호출 전체로 실패하면 심볼별로 나눠 다시 호출"은 넣지 않았다. 어댑터들이 이미 심볼 단위로 조회하고 부분 성공을 돌려주므로(`collect_each`), 전체 실패는 "모든 심볼이 실패"와 같다.

## 막혔던 부분 / 해결 과정
없음.

## 검증 결과
```
$ uv run pytest tests/collect/test_quotes_fallback.py   (구현 전)
ERROR tests/collect/test_quotes_fallback.py
1 warning, 1 error in 0.13s

$ uv run pytest
src\finbrief_analyzer\collect\quotes_fallback.py      38      0   100%
TOTAL                                                295      4    99%
66 passed, 1 warning in 0.71s
$ uv run ruff check .
All checks passed!
$ uv run mypy
Success: no issues found in 22 source files
```
실제 조회 (2026-10-07 저녁 KST). 기본 심볼 6개에 없는 심볼 `NOPE` 를 섞었다.
```
1차 정상        → 6개 모두 반환, missing ('NOPE',)
1차를 죽인 경우 → 6개 모두 반환 (국내 2개는 네이버, 미국 4개는 yfinance), missing ('NOPE',)
```

## 발견한 이슈 (이번 범위 밖)
- [ ] 미국 지수의 예비(yfinance)는 1차와 같은 Yahoo 를 읽는다. Yahoo 가 막히면 미국 지수는 누락으로 표시된다. Yahoo 외의 미국 지수 원천은 아직 찾지 않았다.
- [ ] 어느 제공자가 답했는지는 `Quote` 에 남지 않는다. 로그로만 알 수 있다. 브리핑에 출처를 표시해야 하면 `Quote` 에 필드가 필요하다.

## 남은 것
- [ ] 없음. 시세 쪽은 Task 10(조립)에서 이 클래스를 쓴다.
