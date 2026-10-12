---
type: implementation
project: finbrief-analyzer
topic: news-summary
created: 2026-10-12
status: done
source_task: "[[2026-10-12_news-summary]]"
commits: [163d2db, 64fca95, a797acb, 2c8c7fe, 09d5869]
blog_candidate: true
tags: [implementation, news, llm, summary]
---

# 🛠️ 구현: news-summary Task 2~7 — Claude 로 뉴스 7건 고르고 한 줄씩 쓰기

PoC([[2026-10-12_news-summary-poc]], Task 1)에서 정한 값으로 수집 → **요약** → 작성의 새 단계를 넣었다. 키가 없거나 실패하면 이전 메일(최신순 10건)이 그대로 간다.

## 한 일
- **Task 2** (`163d2db`) `anthropic==1.13.0`; `Settings` 에 `anthropic_api_key`(SecretStr, 빈 값 = None), `summary_model`·`summary_effort`·`summary_picks`·`summary_max_tokens`·`summary_timeout_seconds`. `.env.example`.
- **Task 3** (`64fca95`) `summarize/models.py`(`DigestItem`, `NewsDigest`), `prepare.py`(연합 머리말 제거, 1부터 번호, `[n] (출처) 제목 — 리드` 입력, 번호→항목 되찾기), `ports.py`(`Summarizer` 프로토콜).
- **Task 4** (`a797acb`) `summarize/claude.py`: `messages.parse(output_format=Picks)` 한 번. 범위 밖·중복 번호·빈 줄·60자 초과를 버리고 N 개로 자른다. `anthropic.APIError`·`pydantic.ValidationError`·`stop_reason=refusal`·`parsed_output None` → 경고 한 줄 + `None`. `build_summarizer(settings)` 는 키 없으면 `None`.
- **Task 5** (`2c8c7fe`) `compose_simple(snapshot, date, digest=None, summary_expected=False)`. digest 가 있으면 뉴스 섹션 = `"요약 (출처)"` 줄 + 같은 순서의 원문 링크. 요약이 켜져 있었는데 없으면 `SUMMARY_FALLBACK_NOTE` 한 줄 뒤 v0 목록.
- **Task 6** (`09d5869`) `JobDeps.summarize`, `open_deps` 배선, `run()`: 수신자 대기 확인 → collect → `_summarize()` → compose → dispatch. 로그 `summary: picks=… input_tokens=… output_tokens=… model=…`.
- **Task 7** README "설정 — 뉴스 선별·한 줄 요약" 절, 실전 1회.
- 테스트 41개 추가(config 5, prepare 7, claude 14, compose 5, jobs 7, 그 외 fixture).

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| 어댑터에 **`client.messages.parse` 를 함수로 주입** | `anthropic.Anthropic` 객체 주입 / 모듈 전역 client | 테스트 가짜가 함수 하나다. SDK 의 `ParsedMessage` 를 만들 필요 없이 `parsed_output`·`stop_reason`·`usage` 만 가진 객체로 끝난다 |
| `anthropic.APIError` 하나로 잡고 **클래스 이름만 로그** | 유형별 분기(429·5xx·연결·타임아웃) | 어느 경우든 할 일은 같다(None + 경고). `str(error)` 는 요청 본문을 담을 수 있어 넣지 않는다. 테스트가 429·529·연결·타임아웃 네 가지로 "경고 1개·키 없음"을 확인한다 |
| `pydantic.ValidationError` 도 같이 잡는다 | 안 잡는다 | SDK 의 `parse_text` 는 `TypeAdapter.validate_json` 을 호출해 스키마 불일치를 **예외로** 던진다(`anthropic/lib/_parse/_response.py:16-19`). 구조화 출력이라도 방어한다 |
| 60자 넘는 줄은 **버린다** | 자른다 | 잘린 문장은 한 줄 적은 것보다 나쁘다. PoC 28줄 중 넘은 것 0 |
| 번호로 고르고 코드가 되찾는다 | 모델이 제목·URL 출력 | 링크 날조가 구조적으로 불가능. 입력에서 URL 을 빼 토큰도 아낀다 |
| `summary_expected` 를 작성기 인자로 | `NewsDigest` 에 실패 표시 | 작성기는 LLM 을 모른다. "켜져 있었는데 없다"는 작업만 아는 사실이라 작업이 넘긴다. 뉴스가 0건이면 False(요약할 게 없었던 것) |
| 요약 로그에 토큰을 남긴다 | 비용 추적 없음 | 월 비용은 `history.log`·`<slot>.log` 의 이 줄을 합치면 나온다 |
| Opus 5.5 의 `fallbacks`(거부 시 대체 모델) 미사용 | 켠다 | 거부는 None → v0 로 설계됐고 PoC·실전에서 거부가 없었다. 켜려면 `client.beta.messages` 경로가 필요해 어댑터가 달라진다. 거부가 보이면 그때 |
| `open_deps` 테스트를 실제로 돈다 | 배선 테스트 생략 | `SmtpNotifier`·`make_engine` 은 생성 시 연결하지 않는다(확인). smtp·db 값을 채운 `Settings` 로 `with open_deps(...)` 를 열어 `summarize` 가 None / `ClaudeSummarizer` 인지 본다 |

## 막혔던 부분 / 해결 과정
없음. 네 단계 모두 테스트 먼저(빨강 확인) → 구현 → 녹색. 린트에서 걸린 것은 시스템 프롬프트의 한국어 긴 줄(E501)이었고, 삼중 따옴표 안에서 `\` 줄잇기로 끊었다. 렌더 결과에는 줄바꿈이 들어가지 않는 것을 `SYSTEM_PROMPT.format(...)` 으로 확인했다.

## 검증 결과
```
uv run pytest tests/summarize tests/compose tests/jobs tests/test_config.py → 통과
task done 2·3·4·5·6 (각 ruff · mypy · 전체 pytest)                      → 통과
```
실전 (2026-10-12 17:14 KST, `scripts\run_briefing.cmd us_open`, 오늘 아직 안 보낸 슬롯):
```
summary: picks=7 input_tokens=6831 output_tokens=387 model=claude-opus-5-5
briefing us_open 2026-10-12: sent=1 skipped=0 failed=0 aborted=False
=== exit 0 ===           (요약 호출 약 60초 안, 전체 64초)
비밀값 6개 로그에 없음
```
오늘 22:30 의 자동 us_open 은 "이미 받음"으로 건너뛴다(수집·요약 없이).

## 발견한 이슈 (이번 범위 밖)
- [ ] 메일에 실린 요약 줄은 로그에 남지 않는다. 품질을 나중에 돌아보려면 `logs/` 에 그날의 digest 를 JSON 으로 떨어뜨리는 것이 쉽다(비용 0).
- [ ] `summary_expected` 가 True 인데 뉴스가 0건이면 설명 줄을 안 넣는다. 수집 자체가 실패한 날은 `missing` 안내가 따로 있으니 겹치지 않지만, 두 안내의 문구를 한 번에 보지 않았다.

## 남은 것
- [ ] **키를 비운 실행(v0 복귀) 실전 확인.** 오늘은 두 슬롯이 모두 발송돼 수집을 건너뛰므로 볼 수 없다. 테스트(`test_without_a_summarizer_the_news_is_the_plain_list`, `test_failed_summary_falls_back_*`)로는 덮였다.
- [ ] 2026-10-13 09:00 kr_open 자동 실행의 `summary: picks=` 와 메일 확인.
