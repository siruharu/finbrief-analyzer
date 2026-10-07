---
type: implementation
project: finbrief-analyzer
topic: data-sources
created: 2026-10-07
status: done
source_task: "[[2026-10-07_data-sources]]"
commits: []
blog_candidate: true
tags: [implementation, security]
---

# 🛠️ 구현: data-sources Task 8 — Marketaux 뉴스 어댑터

## 한 일
- `collect/news_marketaux.py`: `MarketauxNewsProvider`, `_parse`, `_to_item`.
- `collect/redact.py`: HTTP 클라이언트의 요청 로그에서 API 키를 가린다. **Task 6 의 ECOS 어댑터에도 적용했다.**
- `collect/text.py`: Task 7 의 `_strip_html` 을 `plain_text` 로 옮겨 두 뉴스 어댑터가 함께 쓴다.
- 테스트: `test_news_marketaux.py` 16개, `test_redact.py` 5개, `test_rates.py` 에 1개 추가.

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| 첫 호출이 실패하면 `CollectError`, 그 뒤 페이지의 실패는 거기서 멈추고 모은 것을 돌려준다 | 어떤 실패든 예외 / 어떤 실패든 빈 목록 | 첫 호출 실패는 "이 출처 누락"으로 적혀야 한다. 3페이지째의 429 로 앞의 6건을 버릴 이유는 없다 |
| 재시도하지 않는다 | 타임아웃 시 한 번 더 | PoC 에서 타임아웃 난 요청도 하루 한도(100회)에서 빠졌다 |
| 요약은 `description` 만 쓴다 | `snippet` 으로 보충 | `snippet` 에 "enable Javascript and cookies" 같은 차단 문구가 그대로 들어온다 |
| `countries=us` 고정 | 필터 없음 | 없으면 인도 매체 기사가 상단을 채운다(PoC) |
| `published_after` 는 UTC 로 바꿔 분 단위로 보낸다 | `since` 를 그대로 | API 가 UTC 를 기대한다. 어댑터가 받은 결과를 `since` 로 한 번 더 거르므로 분 단위 절삭으로 새는 것은 없다 |
| 오류 메시지에는 HTTP 상태 코드나 예외 종류 이름만 | 응답 본문·예외 문구 포함 | 토큰이 쿼리 파라미터에 있다. ECOS 와 같은 방식으로 `except` 블록 밖에서 던져 예외 체인을 끊었다 |

## 막혔던 부분 / 해결 과정
> 💡 블로그 소재. "내 코드는 키를 안 찍는데 라이브러리가 찍는다"

**증상** — "토큰이 예외 메시지와 로그에 남지 않는다" 테스트를 `caplog` 으로 썼더니 실패했다. 예외 메시지는 깨끗했다. 로그에 이런 줄이 있었다.
```
INFO httpx HTTP Request: GET https://api.marketaux.com/v1/news/all?api_token=tok-SECRET-0123456789&language=en... "HTTP/1.1 401 Unauthorized"
```

**원인** — httpx 는 모든 요청을 `httpx` 로거에 INFO 로 남긴다. URL 전체가 들어간다. 운영의 `APP_LOG_LEVEL` 기본값이 INFO 다. 즉 배포하면 수집이 돌 때마다 Marketaux 토큰과 DART 키(쿼리), ECOS 키(경로)가 CloudWatch 에 평문으로 쌓였을 것이다. **이미 완료 처리한 Task 6(ECOS)도 같은 문제를 안고 있었다** — 그 테스트는 예외 객체만 봤고 로그는 보지 않았다.

**검토한 해결책**
1. `httpx` 로거 수준을 WARNING 으로 올린다 → 로깅 설정을 누가 다시 INFO 로 내리면 조용히 되살아난다. 요청 로그 자체도 잃는다.
2. 클라이언트를 만드는 곳에서 처리한다 → 어댑터를 다른 클라이언트와 함께 쓰면 보호가 빠진다.
3. **`httpx` 로거에 필터를 달아 등록된 비밀값을 `***` 로 바꾼다** → 로그 수준과 무관하고, 요청 로그는 남는다. 이걸 골랐다.

**해결** — `redact.hide_from_http_log(secret)`. 키를 쓰는 어댑터가 생성자에서 자기 키를 등록한다. 키에 URL 예약 문자가 있으면 로그에는 퍼센트 인코딩된 모양으로 찍히므로 그 모양도 함께 가린다. 빈 문자열은 등록하지 않는다(모든 글자 사이가 `***` 가 된다).

**확인** — 요청 로그를 INFO 로 켜고 실제 호출을 했다.
```
httpx HTTP Request: GET https://api.marketaux.com/v1/news/all?api_token=***&language=en&countries=us&limit=3&... "HTTP/1.1 200 OK"
```

**남는 구멍** — 필터는 `httpx` 로거에만 달려 있다. 다른 경로(예: 예외를 통째로 덤프하는 오류 수집기, httpcore 의 DEBUG 추적)는 따로 봐야 한다. httpcore 의 DEBUG 로그는 테스트에서 켜 봤고 URL 이 나오지 않았다.

## 검증 결과
```
$ uv run pytest tests/collect/test_news_marketaux.py   (구현 전)
ERROR tests/collect/test_news_marketaux.py
1 warning, 1 error in 0.15s

$ uv run pytest
src\finbrief_analyzer\collect\news_marketaux.py       72      0   100%
src\finbrief_analyzer\collect\rates.py                64      0   100%
src\finbrief_analyzer\collect\redact.py               25      0   100%
src\finbrief_analyzer\collect\text.py                  6      0   100%
TOTAL                                                541      4    99%
122 passed, 1 warning in 0.82s
$ uv run ruff check .
All checks passed!
$ uv run mypy
Success: no issues found in 31 source files
```
실제 조회 (2026-10-07 17시경 KST, 2회 호출, 최근 12시간): 6건. seekingalpha 4, cnbc 1, insidermonkey 1.

## 발견한 이슈 (이번 범위 밖)
- [ ] **결과의 질이 낮다.** 6건 중 시황 기사는 CNBC 1건이고 나머지는 개별 종목 슬라이드·분석 글이다. `domains`·`must_have_entities` 같은 필터나 다른 출처가 필요하다. 슬롯당 3회 호출이면 9건인데 그중 쓸 만한 것이 1~2건이다. 미국 뉴스 출처는 분석으로 돌아가 다시 볼 만하다.
- [ ] 같은 기사가 URL 만 다르게 두 번 나온다(Rocket Pharmaceuticals). 링크 기준 중복 제거로는 못 잡는다.
- [ ] Task 9(DART)도 키가 쿼리 파라미터다. 같은 `hide_from_http_log` 를 써야 한다.

## 남은 것
- [ ] 없음.
