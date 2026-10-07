---
type: implementation
project: finbrief-analyzer
topic: data-sources
created: 2026-10-07
status: done
source_task: "[[2026-10-07_data-sources]]"
commits: [84a9ddc]
blog_candidate: true
tags: [implementation]
---

# 🛠️ 구현: data-sources Task 6 — ECOS 금리·환율 어댑터

## 한 일
- `collect/rates.py`: `EcosRateProvider`, `EcosSeries`, `DEFAULT_SERIES`.
- `tests/collect/test_rates.py`: 15개. `httpx.MockTransport` 만 쓴다.
- `tests/collect/fixtures/ecos_rate.json`: PoC 에서 받은 국고채 3년 응답을 줄인 것 (키 없음).

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| 기본 계열 4개: 기준금리, 국고채 3년·10년, **원/달러 매매기준율** | 금리만 | PoC 뒤 사용자 결정. 환율은 ECOS 매매기준율로 싣는다 |
| 예외를 `except` 블록 **밖에서** 던진다 | `raise ... from error`, `from None` | 아래 "막혔던 부분" 참고 |
| 오류 메시지에 예외 **종류 이름만** 넣는다 | `str(error)` 포함 | httpx 오류 문구는 요청 URL 을 인용하고, ECOS 는 키가 URL 경로에 있다 |
| `RESULT` 가 있으면 오류로 본다 (HTTP 200 이어도) | 상태 코드만 확인 | ECOS 는 잘못된 키(`INFO-100`)와 데이터 없음(`INFO-200`)을 모두 200 으로 준다 |
| 오류 메시지에 `CODE` 만 싣고 `MESSAGE` 는 버린다 | 서버 문구 그대로 | 서버가 주는 문장을 그대로 로그에 옮기지 않는다. 코드만으로 원인을 알 수 있다 |
| 계열 하나가 실패해도 나머지를 돌려준다 | 전체 실패 | 환율 통계가 늦는 날에도 금리는 실린다. 시세 어댑터와 같은 규칙(`collect_each`)이다 |
| 행 → `Quote` 는 시세 어댑터의 `quote_from_rows` 를 그대로 쓴다 | 금리용 규칙을 따로 | 읽지 못한 값 건너뛰기, 직전 값, 오래된 값 거부가 같다 |
| `get_rates()` 는 인자가 없다 | 설계 메모의 `get_rates(codes)` | Task 2 의 `RateProvider` 포트가 그렇다. 무엇을 가져올지는 생성자의 `series` 가 정한다 |

## 막혔던 부분 / 해결 과정
> 💡 블로그 소재. "예외 체인이 비밀값을 실어 나른다"

**증상** — 키가 URL 경로에 들어가는 API 다. `CollectError` 메시지에서 URL 을 빼는 것만으로 충분한지 따져 봤다.

**가설과 검증**
1. `raise CollectError(...) from error` → `__cause__` 에 httpx 예외가 붙는다. 그 예외의 문구에 URL 전체가 있다. `logger.exception` 한 번이면 키가 로그에 찍힌다.
2. `raise CollectError(...) from None` → 트레이스백 출력에서는 숨겨지지만 `__context__` 에는 원래 예외가 **그대로 남는다.** `__suppress_context__` 는 표시 여부만 바꾼다. 예외 객체를 직접 뒤지는 도구(오류 수집기 등)는 여전히 URL 을 본다.

**해결** — `except` 블록 안에서는 예외 종류 이름만 변수에 담고, 블록을 빠져나온 뒤에 `CollectError` 를 던진다. 이러면 `__cause__` 도 `__context__` 도 `None` 이다. 테스트가 메시지뿐 아니라 이 두 속성까지 확인한다.

**대가** — 원래 예외의 스택을 잃는다. 남는 것은 `ReadTimeout`, `HTTPStatusError` 같은 종류 이름뿐이다. 이 API 에서는 그 거래가 맞다고 봤다.

## 검증 결과
```
$ uv run pytest tests/collect/test_rates.py   (구현 전)
ERROR tests/collect/test_rates.py
1 warning, 1 error in 0.13s

$ uv run pytest
srcinbrief_analyzer\collectates.py                62      0   100%
81 passed, 1 warning
$ uv run ruff check .
All checks passed!
$ uv run mypy
Success: no issues found in 24 source files
```
실제 조회 (2026-10-07 저녁 KST, 로컬 `.env` 의 키):
```
KR_BASE_RATE 2026-10-05  3.0     직전 3.0
KR3YT        2026-10-07  3.961   직전 3.933
KR10YT       2026-10-07  4.376   직전 4.369
USD/KRW      2026-10-07  1343.4  직전 1358.5
```

## 발견한 이슈 (이번 범위 밖)
- [ ] **기준금리는 이틀 늦게 나온다** (10-07 조회에 10-05 가 최신). 10일 창 안이라 오래된 값으로 걸리지는 않지만, Task 10 의 휴장 판정이 "기준일이 직전 거래일이 아니면 휴장"을 금리·환율에 적용하면 기준금리가 매번 걸린다. 휴장 판정은 지수(`Market.KR`·`Market.US`)에만 적용해야 한다.
- [ ] 금리의 등락은 `%` 가 아니라 %p·bp 로 표시해야 한다 (Task 4 노트와 같은 항목). `Quote.change_pct` 는 3.933 → 3.961 을 +0.71% 로 계산한다.
- [ ] 이 계열들의 표시 이름과 `Market` 대응은 아직 어디에도 없다. `Settings.quote_symbols` 는 시세 어댑터용이다. Task 10 에서 정한다.
- [ ] ECOS 호출 한도·이용 조건은 여전히 확인하지 못했다. 슬롯당 4회 호출이다.

## 남은 것
- [ ] 없음.
