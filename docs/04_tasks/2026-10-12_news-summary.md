---
type: task
project: finbrief-analyzer
topic: news-summary
created: 2026-10-12
source_plan: "[[2026-10-12_news-summary]]"
branch: feat/news-summary
issue: 없음
tags: [task, news, llm, summary]
next: implementation
---

# ✅ 작업: LLM 뉴스 선별·요약 단계

> **작업 상태의 정본은 이 문서가 아니라 `news-summary.tasks.json` 이다.**
> 체크박스를 여기에 다시 적지 않는다 — 두 곳을 손으로 맞추면 반드시 어긋난다.
>
> ```bash
> .claude/hooks/harness.py task list
> .claude/hooks/harness.py task next
> ```
>
> 이 문서는 **왜 이렇게 쪼갰는지**를 적는 곳이다.

## 쪼갠 기준
- **PoC(Task 1)를 맨 앞에.** 모델·N·effort·줄 길이는 실측 없이 못 정하고, 기본값이 Task 2 의 설정에 들어간다. 코드가 하나도 없는 시점이 틀렸을 때 버릴 것이 가장 적다.
- **순수 함수(Task 3)와 외부 호출(Task 4)을 나눴다.** 전처리·번호 되찾기·결과 검증은 네트워크 없이 테스트된다. 어댑터는 `messages.parse` 하나만 가짜로 바꾸면 된다.
- **작성기(Task 5)는 어댑터(Task 4)와 독립.** `NewsDigest` 자료형(Task 3)만 있으면 되므로 둘은 병렬이다. 작성기 테스트에 LLM 가짜가 필요하지 않다.
- **작업 연결(Task 6)이 대체 경로의 주인.** "실패하면 v0" 는 어댑터가 `None` 을 돌려주고 작업이 그대로 `compose` 에 넘기는 것으로 끝난다. 작성기는 LLM 의 존재를 모른다.
- **실전 확인(Task 7)을 따로.** 메일을 실제로 받아 보는 것과 README 는 코드 커밋과 섞이면 완료 판정이 흔들린다.

## 공통 규칙
- 완료 판정의 `uv run ruff check . && uv run mypy && uv run pytest` 는 `make check` 와 같다(이 PC 에 `make` 없음).
- 테스트는 실제 API 를 부르지 않는다. Task 1 만 예외(스크래치, 미커밋).
- 모델이 돌려준 텍스트·입력 뉴스 제목이 로그에 통째로 찍히지 않게 한다. 비밀값(`APP_ANTHROPIC_API_KEY`)은 `SecretStr`, 예외 메시지를 그대로 로그에 넣지 않는다.
- SDK 는 `anthropic` 1.13.x. `httpx2` 기반이라 프로젝트의 `httpx.Client` 를 넘기지 않는다. 키는 `Anthropic(api_key=...)` 로 **명시적으로** 넘긴다(설정은 `Settings` 로만).
- 5.5 세대 규칙: assistant prefill 금지, `tool_choice` 강제 금지 → JSON 은 **구조화 출력**(`output_config.format` / `messages.parse`)으로만. thinking 은 기본(어댑티브), effort 는 `output_config={"effort": ...}` 로 명시.

## Task 별 설계 메모

### Task 1 — PoC: 실제 하루치 뉴스로 모델·effort 비교

**손댈 곳**

| 파일 | 내용 | 작업 |
|---|---|---|
| `docs/01_research/2026-10-12_news-summary-poc.md` | 결과·확정값 | 신규 |
| (scratch) `news_dump.py` | `collect_snapshot(Slot.KR_OPEN, now, providers, symbols)` 로 뉴스만 뽑아 `news.json`(title/source/summary/link/published_at) 저장 | 미커밋 |
| (scratch) `poc_summary.py` | 같은 입력·같은 프롬프트로 `claude-opus-5-5`(effort medium/low)·`claude-sonnet-5-5`·`claude-haiku-5-5` 호출. `client.messages.parse(output_format=Picks)`; `usage` 와 소요 시간 기록; `client.messages.count_tokens` 로 한국어 토큰/글자 | 미커밋 |

**먼저 쓸 테스트** — 없음(탐색). 답할 것:
1. 입력 80건의 토큰 수(모델별 `count_tokens`)와 한글 글자당 토큰.
2. 4가지 호출의 `picks` 수·줄 길이 분포·`usage`(input/output, thinking 포함 여부)·비용·초.
3. 기준 ①~⑤ 표: ① 입력에 없는 사실·수치 ② 리드의 단순 축약 ③ 같은 사건 중복 ④ 한국어 자연스러움 ⑤ 60자 안.
4. 스키마 준수: 범위 밖 번호·중복·빈 줄이 몇 번 나왔나.
5. **확정값**: 모델, effort, N, 줄 길이 상한, `max_tokens`. 프롬프트 초안 전문.

**엣지 케이스**
- 신규 조직은 Evaluation 티어일 수 있다 → 429 면 재시도 간격을 보고 노트에 적는다.
- `stop_reason == "refusal"` 이 나오면 어떤 입력에서였는지 적는다(금융 뉴스에서는 드물어야 한다).
- 토큰 100K 초과 시 Haiku 단가가 바뀌지만 15K 라 해당 없음 — 수치로 확인해 적는다.
- 출력 원문에 비밀값이 섞일 일은 없지만 키는 `.env` 에서만 읽는다(`Settings` 미사용 PoC 라도 `os.environ` 평문 하드코딩 금지).

**완료 판정** — `tasks.json` 의 `verify` 와 같다
```bash
python -c "import pathlib;t=pathlib.Path('docs/01_research/2026-10-12_news-summary-poc.md').read_text(encoding='utf-8');assert all(k in t for k in ['claude-opus-5-5','claude-haiku-5-5','usage','확정'])"
```

### Task 2 — 의존성(anthropic)과 요약 설정

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `pyproject.toml`, `uv.lock` | `anthropic==1.13.x` | `uv add anthropic` |
| `src/finbrief_analyzer/core/config.py` | `Settings.anthropic_api_key: SecretStr \| None = None`, `summary_model: str = "<PoC 확정>"`, `summary_picks: int = Field(default=<PoC>, ge=1, le=20)`, `summary_effort: Literal["low","medium","high"] = "<PoC>"`, `summary_timeout_seconds: float = Field(default=120.0, gt=0)`, `summary_max_tokens: int = Field(default=4000, ge=256)`; `_blank_key_is_unset` 목록에 `anthropic_api_key` 추가 | 수정 |
| `.env.example` | `APP_ANTHROPIC_API_KEY=` 와 주석 "비우면 뉴스는 최신순 목록" | 수정 |
| `tests/test_config.py` | `_isolated_env` 의 delenv 목록에 `APP_ANTHROPIC_API_KEY` 추가 | 수정 |

**먼저 쓸 테스트**
- `anthropic_api_key 가 빈 문자열이면 None 이다`
- `anthropic_api_key 는 SecretStr 이고 repr 에 값이 없다`
- `summary_picks 가 0 이나 21 이면 ValidationError`
- `summary 설정의 기본값은 PoC 확정값이다` (모델 ID 문자열 고정)

**엣지 케이스**
- `.env` 에 키가 없고 환경에도 없음 → None (전부 비활성). 키만 있고 모델 설정 없음 → 기본값.
- 모델 ID 는 날짜 접미사 없는 정식 ID 만(`claude-opus-5-5` 등).

**완료 판정**
```bash
uv run pytest tests/test_config.py && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 3 — 요약 자료형·입력 전처리·프로토콜

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/summarize/__init__.py` | — | 신규 |
| `src/finbrief_analyzer/summarize/models.py` | `DigestItem(news: NewsItem, line: str)`, `NewsDigest(items: tuple[DigestItem, ...], model: str, input_tokens: int, output_tokens: int)` — frozen dataclass | 신규 |
| `src/finbrief_analyzer/summarize/prepare.py` | `strip_byline(text) -> str` (연합 "(○○=연합뉴스) ○○○ 기자 =" 제거, 정규식 하나), `Candidate(index: int, news: NewsItem)`, `candidates(news: Sequence[NewsItem]) -> tuple[Candidate, ...]` (1부터 번호), `render_input(candidates) -> str` (줄 형식 `[n] (출처) 제목 — 리드`, URL 제외, 리드 None 이면 제목만), `resolve(candidates, index) -> NewsItem \| None` | 신규 |
| `src/finbrief_analyzer/summarize/ports.py` | `class Summarizer(Protocol): def summarize(self, news: Sequence[NewsItem], slot: Slot) -> NewsDigest \| None` | 신규 |
| `tests/summarize/__init__.py`, `tests/summarize/test_prepare.py` | | 신규 |

**먼저 쓸 테스트**
- `연합 머리말은 리드에서 제거되고 본문은 남는다` ("(서울=연합뉴스) 홍길동 기자 = 코스피가…" → "코스피가…")
- `머리말이 없는 리드는 그대로다`
- `후보는 1 부터 번호가 붙고 번호로 원 항목을 되찾는다`
- `리드가 None 인 항목은 제목만 들어간다`
- `입력 텍스트에 URL 은 들어가지 않는다`
- `범위 밖 번호를 되찾으면 None`
- `빈 뉴스는 빈 후보·빈 입력`

**엣지 케이스**
- 머리말 변형: "(세종=연합뉴스)", "(서울=연합뉴스) 홍길동 김철수 기자 =", 기자 이름 없는 "= " 만. 정규식은 `^\([^)]*연합뉴스\)\s*[^=]*=\s*`.
- 제목에 `[n]` 같은 대괄호가 있어도 번호 파싱은 모델 출력(JSON 정수)에서만 하므로 영향 없음.
- 80건 상한은 수집이 보장한다. 여기서는 더 자르지 않는다.

**완료 판정**
```bash
uv run pytest tests/summarize && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 4 — Claude 어댑터

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/summarize/claude.py` | `SYSTEM_PROMPT` 상수(PoC 초안), `class Picks(BaseModel)`: `picks: list[Pick]`, `class Pick(BaseModel)`: `index: int`, `line: str`; `class ClaudeSummarizer: __init__(client, settings)`, `summarize(news, slot) -> NewsDigest \| None`; 내부 `_request(text) -> ParsedMessage`, `_digest(parsed, candidates) -> NewsDigest \| None`, `_valid_picks(picks, n_candidates, limit) -> list[Pick]`; `build_summarizer(settings) -> ClaudeSummarizer \| None` (키 없으면 None, `Anthropic(api_key=..., timeout=..., max_retries=2)`) | 신규 |
| `tests/summarize/test_claude.py` | 가짜 client: `messages.parse(**kwargs)` 를 기록하고 미리 정한 `ParsedMessage` 꼴(`parsed_output`, `stop_reason`, `usage`)을 돌려주는 객체 | 신규 |

**먼저 쓸 테스트**
- `정상 응답은 선택 순서대로 DigestItem 이 되고 모델명·토큰이 기록된다`
- `범위 밖 번호와 중복 번호와 빈 줄은 버린다`
- `검증 뒤 남는 것이 없으면 None`
- `N 을 넘는 선택은 앞 N 개만`
- `줄 길이 상한을 넘는 줄은 잘라서 쓴다`(또는 버린다 — PoC 뒤 결정)
- `RateLimitError·APIConnectionError·APITimeoutError·APIStatusError 는 None 과 경고 하나`
- `stop_reason 이 refusal 이면 None 과 경고`
- `경고 로그에 API 키가 없다`
- `요청에 model·max_tokens·output_config.effort 가 설정값으로 들어간다`
- `뉴스가 비어 있으면 호출하지 않고 None`

**엣지 케이스**
- `parsed_output` 이 None(파싱 실패) → None + 경고.
- 모델이 같은 사건을 두 번 골랐을 때 중복 제거는 번호 기준만(내용 중복은 프롬프트에 맡긴다).
- `usage` 에 `cache_*` 필드가 있어도 쓰지 않는다. 입력·출력 토큰만 기록.
- 예외는 유형별로 잡되 `anthropic.APIError` 밖의 예외(프로그래밍 오류)는 그대로 올린다 — 작업 로그에 스택이 남고 exit 1.
- 타임아웃은 `Anthropic(timeout=settings.summary_timeout_seconds)` 로. 재시도 2회 × 120초가 최악 6분 — 작업 30분 안.

**완료 판정**
```bash
uv run pytest tests/summarize && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 5 — 작성기: 요약이 있으면 줄+링크, 없으면 v0

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/compose/simple.py` | `compose_simple(snapshot, briefing_date, digest: NewsDigest \| None = None, summary_expected: bool = False)`; `_news_section(items, digest, summary_expected)`: digest 있으면 `lines=("요약 (출처)", …)`, `links=(원문 …)` 같은 순서; digest 없고 `summary_expected` 면 `lines=("자동 요약을 만들지 못해 최신 기사 순으로 싣습니다.",)` + v0 links; 둘 다 아니면 v0 | 수정 |
| `tests/compose/test_simple.py` | | 수정 |

**먼저 쓸 테스트**
- `digest 가 있으면 뉴스 섹션 lines 는 "요약 (출처)" 꼴이고 links 는 같은 순서의 원문이다`
- `digest 가 None 이면 v0 와 같다` (기존 `test_news_lists_title_link_and_source_without_the_summary_text`, `test_news_is_capped_keeping_the_newest_items` 유지)
- `요약이 켜져 있었는데 digest 가 None 이면 설명 한 줄 뒤 v0 목록`
- `digest 가 있어도 뉴스 섹션은 required 가 아니다`
- `digest 의 항목 수가 MAX_NEWS_ITEMS 를 넘어도 그대로 싣는다`(N 은 설정이 정한다; 작성기는 자르지 않는다)

**엣지 케이스**
- 같은 출처 연속일 때 출처 표기 생략? → 하지 않는다. 줄마다 출처(단순함).
- `digest.items` 가 빈 튜플이면 None 과 같이 취급(어댑터가 None 을 주므로 방어만).

**완료 판정**
```bash
uv run pytest tests/compose && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 6 — 작업 연결: collect → summarize → compose, 실패 시 v0

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/jobs/run_briefing.py` | `JobDeps.summarize: Summarizer \| None = None`; `run()`: 수신자 대기 확인 → `snapshot = collect` → `digest = _summarize(deps, snapshot, slot)` → `compose_simple(snapshot, day, digest, summary_expected=deps.summarize is not None)`; `_summarize()` 가 로그 `summary: picks=%d input_tokens=%d output_tokens=%d model=%s` 또는 `summary skipped`; `open_deps`: `summarize=build_summarizer(settings)` | 수정 |
| `tests/jobs/test_run_briefing.py` | `deps()` 빌더에 `summarize=` 인자; 가짜 `Summarizer`(고정 digest / None / 예외) | 수정 |

**먼저 쓸 테스트**
- `summarize 가 None 이면 요약 없이 v0 메일이 간다`
- `summarize 가 digest 를 주면 메일 본문에 요약 줄과 원문 링크가 있다`
- `summarize 가 None 을 돌려주면 메일은 설명 한 줄 + v0 로 가고 경고가 남는다`
- `전원이 이미 받은 날은 summarize 도 불리지 않는다`
- `open_deps 는 키가 없으면 summarize=None` (기존 `test_open_deps_*` 꼴)
- `요약 로그에 선택 건수와 토큰이 있다`

**엣지 케이스**
- `run()` 길이 30줄 — 요약 호출·로그를 `_summarize()` 로 뺀다.
- summarize 가 `anthropic` 밖 예외를 던지면 작업 크래시 → exit 1 (설계대로; 테스트 `test_unhandled_error_is_logged_and_exits_non_zero` 유지).
- 뉴스가 0건이면 어댑터가 호출 없이 None → 설명 한 줄이 "뉴스 없음"과 겹친다 → 뉴스 0건이면 `summary_expected` 를 False 로 넘긴다.

**완료 판정**
```bash
uv run pytest tests/jobs && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 7 — 실전 확인과 운영 문서

**손댈 곳**

| 파일 | 내용 | 작업 |
|---|---|---|
| `.env` (미커밋) | `APP_ANTHROPIC_API_KEY` | 사용자 |
| `README.md` | "설정" 절: 키·모델·N·"키가 없으면 최신순 목록"; 월 비용 추정 | 수정 |
| `docs/05_implementation/…` | 실제 메일 발췌, 토큰·비용, 로그 | 구현 노트 |

**손으로 확인할 것**
1. 키를 넣고 `scripts\run_briefing.cmd <아직 안 보낸 슬롯>` → 메일 뉴스 섹션에 요약 줄 + 링크, `logs\<slot>.log` 에 `summary: picks=`.
2. 키를 비우고 다음 발송 → 지금 메일(v0). 같은 날 같은 슬롯은 수집을 건너뛰므로(Task 10) 다른 슬롯이나 다음 날로.
3. 로그에 키·기사 본문이 없다.

**엣지 케이스**
- 첫 호출에서 Evaluation 티어 429 → SDK 재시도 2회 뒤 None → v0. 로그로 확인 후 티어·충전 안내를 README 에.

**완료 판정**
```bash
findstr /c:"summary: picks=" logs\kr_open.log && uv run ruff check . && uv run mypy && uv run pytest
```
(`kr_open.log` 가 아닌 슬롯에서 확인했다면 `verify` 의 파일명을 그 슬롯으로 바꾼다.)

## 브랜치
- `feat/news-summary` 하나로 Task 1~7. 이슈는 만들지 않는다(앞 주제들과 같음). 리서치·분석·플랜·태스크 문서가 있는 `docs/news-summary-research` 를 이 이름으로 바꿔 이어 간다.

## 열어둔 질문
- Task 4 의 "줄 길이 상한을 넘으면 자르나 버리나"는 PoC 결과를 보고 정한다.
- Task 1 의 API 계정·충전은 사용자가 한다. 키가 준비되기 전에는 Task 1 을 시작할 수 없다.
