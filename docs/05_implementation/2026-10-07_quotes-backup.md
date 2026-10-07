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

# 🛠️ 구현: data-sources Task 11 — yfinance·네이버 예비 시세 어댑터

Task 5 에서 떼어 낸 앞 절반이다. 폴백 합성은 Task 5 에 남았다.

## 한 일
- `collect/quotes_yf.py`: `YfQuoteProvider`. 미국 지수 3개와 미 국채 10년.
- `collect/quotes_naver.py`: `NaverQuoteProvider`. KOSPI·KOSDAQ.
- `collect/quotes_base.py`: 세 어댑터가 함께 쓰는 규칙. Task 4 의 `quotes_fdr.py` 에 있던 것을 옮겼다.
- `tests/collect/test_quotes_backup.py`: 22개.

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| "행 목록 → `Quote`" 규칙을 `quote_from_rows` 하나로 | 어댑터마다 구현 | NaN 건너뛰기, 전일 종가, stale 판정이 출처마다 달라지면 안 된다. 네이버는 표가 아니라 배열을 주므로 `(날짜, 종가)` 쌍을 공통 입력으로 삼았다 |
| FDR 과 yfinance 는 `FrameQuoteProvider` 의 하위 클래스 | 각자 구현 | 둘의 차이는 조회 함수, 이름, 티커 대응표뿐이다 |
| 내부 심볼 → 출처 티커 대응표를 어댑터가 가진다 | 설정에 출처별 티커를 두기 | 대응표는 "이 어댑터가 무엇을 지원하는가"와 같은 정보다. `supports()` 가 같은 표를 본다 |
| 지원하지 않는 심볼은 조회하지 않고 건너뛴다 | 예외 | 폴백이 심볼을 섞어 넘겨도 부분 성공이 산다. 폴백은 `supports()` 로 미리 거를 수도 있다 |
| 네이버 응답을 `ast.literal_eval` 로 파싱 | 정규식, 작은따옴표를 바꿔 `json.loads` | 응답이 JSON 이 아니라 작은따옴표 머리글이 든 배열 리터럴이다. `literal_eval` 은 리터럴만 받고 호출·import 를 실행하지 않는다. 머리글에서 `날짜`·`종가` 의 위치를 찾으므로 열 순서가 바뀌어도 틀린 값을 읽지 않는다 |
| 응답 2만 자 초과는 거부 | 제한 없음 | 비공식 엔드포인트다. 10일치는 수백 바이트라, 훨씬 큰 응답은 기대한 답이 아니다. 깊게 중첩된 입력으로 파서를 괴롭히는 것도 막는다 |
| 읽지 못한 행은 버리고 나머지로 계산 | 한 행이라도 깨지면 실패 | 미완성 행(`None`)이 섞여도 직전 유효 행으로 종가를 낸다. FDR 의 NaN 처리와 같은 규칙이다 |
| `httpx.Client` 를 생성자로 받는다 | 어댑터가 직접 만든다 | 타임아웃은 `Settings` 에서 오고 조립(Task 10)이 클라이언트를 만든다. 테스트는 `MockTransport` 를 끼운다 |

yfinance 표는 인덱스에 시간대가 있다(`America/New_York`). 날짜를 `stamp.year/month/day` 로 떼어 내므로 시간대가 있든 없든 그 시장의 거래일이 나온다. UTC 로 바꿔 읽으면 하루 밀린다.

## 막혔던 부분 / 해결 과정
**증상** — "응답이 너무 큰 경우" 테스트를 `parametrize` 에 넣자 테스트가 실행되기도 전에 `ERROR at setup` 이 났다.

**원인** — pytest 가 매개변수 값을 그대로 테스트 ID 로 쓴다. 4만 자짜리 문자열이 ID 가 됐다.

**해결** — `pytest.param(..., id="too-large")` 로 짧은 ID 를 줬다. 구현 문제가 아니었다.

## 검증 결과
```
$ uv run pytest tests/collect/test_quotes_backup.py   (구현 전)
ERROR tests/collect/test_quotes_backup.py
1 warning, 1 error in 0.55s

$ uv run pytest
src\finbrief_analyzer\collect\quotes_base.py       58      0   100%
src\finbrief_analyzer\collect\quotes_fdr.py         8      0   100%
src\finbrief_analyzer\collect\quotes_naver.py      59      0   100%
src\finbrief_analyzer\collect\quotes_yf.py          9      0   100%
TOTAL                                             257      4    98%
56 passed, 1 warning in 0.65s
$ uv run ruff check .
All checks passed!
$ uv run mypy
Success: no issues found in 20 source files
```
Task 4 의 테스트 11개는 고치지 않았고 리팩터 뒤에도 그대로 통과한다.

실제 조회 (2026-10-07 저녁 KST):
```
naver ^KS11  2026-10-07  6803.9   전일 6941.39
naver ^KQ11  2026-10-07   898.43  전일  919.92
yf    US500  2026-10-06  7818.93  전일 7773.95
yf    IXIC   2026-10-06 27599.789 전일 27477.311
yf    DJI    2026-10-06 51521.281 전일 51267.898
yf    US10YT 2026-10-06     5.269 전일     5.311
```
1차(FDR) 값과 같다. 네이버는 httpx 기본 User-Agent 로 차단 없이 응답했다.

## 발견한 이슈 (이번 범위 밖)
- [ ] 네이버 엔드포인트의 이용 조건은 확인하지 않았다. 비공식 경로이고 예비로만 쓴다(1차가 실패한 날에만 호출).

## 남은 것
- [ ] Task 5: 폴백 합성. 국내 심볼은 네이버로, 미국 심볼은 yfinance 로 넘긴다.
