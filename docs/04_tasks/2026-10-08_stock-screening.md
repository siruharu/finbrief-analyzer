---
type: task
project: finbrief-analyzer
topic: stock-screening
created: 2026-10-08
source_plan: "[[2026-10-08_stock-screening]]"
branch: feat/stock-screening
issue: #
tags: [task]
next: implementation
---

# ✅ 작업: 개별 종목 스크리닝 1차 (관심 종목 + 단기 규칙)

> **작업 상태의 정본은 이 문서가 아니라 `stock-screening.tasks.json` 이다.**
> 체크박스를 여기에 다시 적지 않는다.
>
> ```bash
> python .claude/hooks/harness.py stage task stock-screening
> python .claude/hooks/harness.py task list
> python .claude/hooks/harness.py task next
> ```
>
> 이 문서는 **왜 이렇게 쪼갰는지**를 적는 곳이다.

## 쪼갠 기준
- **PoC 를 맨 앞에 뒀다.** Yahoo 가 500종목 조회를 막으면 미국이 빠진다. 그때 바뀌는 것이 설정값과 Task 5 의 미국 묶음 조회뿐이도록 나머지를 출처와 무관하게 쪼갰다.
- **관심 종목(Task 2)을 이력(Task 3~6)과 떼었다.** 관심 종목은 기존 시세 경로만 쓴다. DB 가 없어도 동작하고, PoC 직후 바로 메일에 실린다.
- **스키마(Task 3)와 그것을 쓰는 코드(Task 4~6)를 나눴다.** 마이그레이션만 담은 커밋이 먼저 들어간다 (delivery-channels 와 같은 순서).
- **출처(Task 5)와 갱신 규칙(Task 6)을 나눴다.** Task 5 는 "한 번 받아 `Bar` 로 바꾸는 방법", Task 6 은 "무엇을 언제 받을지"다. 출처가 바뀌어도 Task 6 은 그대로다.
- **규칙(Task 7)은 아무것에도 기대지 않는다.** `Bar` 목록만 받는 순수 함수다. 백테스트가 같은 함수를 쓴다.
- **연결(Task 8)을 맨 뒤에 뒀다.** 이력이 실제로 쌓이는 것(Task 6)을 본 뒤에 메일에 싣는다.

## 공통 규칙
- 완료 판정의 `uv run ruff check . && uv run mypy && uv run pytest` 는 `make check` 와 같은 내용이다 (이 PC 에 `make` 가 없다).
- 테스트는 네트워크에 접속하지 않는다. 출처는 fetch 함수를 주입한다. DB 테스트는 SQLite(`tests/conftest.py` 의 `engine`·`store` 픽스처).
- 테스트는 Given/When/Then 주석 구조, 이름은 보장하는 성질을 말한다. 함수 30줄 이하. 주석·식별자는 영어.
- pandas 값은 어댑터 밖으로 나가지 않는다. 경계에서 `Bar` 로 바꾼다 (기존 `quotes_base.frame_rows` 와 같은 규칙).
- 설정은 `Settings` 로만 읽는다.
- 메일 문구에 "추천", "매수", "유망"을 쓰지 않는다.
- 한 PC 의 Bash 도구에서 긴 여러 줄 스크립트를 heredoc 으로 넘기면 따옴표 해석 오류가 난다 (delivery-channels 구현 중 두 번). 스크립트는 파일로 쓰고 실행한다.

## 분석·플랜에서 정해진 것 (요약)
- 일봉만. 국내 시가총액 상위 KOSPI 200 + KOSDAQ 150, 미국 S&P 500.
- 단기 규칙은 "52주 신고가 근접"과 "거래량 급증" 둘. 시장별·규칙별 상위 5개.
- 이력은 DB 에 쌓는다. 마감이 끝난 날만. 겹쳐 받아 어긋나면 다시 받는다.
- 섹션 이름은 "조건 충족 종목". 규칙·기준일·고지 문구를 싣는다.
- 관심 종목은 시가총액 상위 10개씩이 기본값.

## PoC 뒤 정해진 것 (2026-10-08) — 아래 Task 별 메모와 어긋나면 이 절이 우선한다
근거는 [screening-poc](../01_research/2026-10-08_screening-poc.md).
- **`StockListing('KRX')` 는 가격·시가총액을 주지 않는다.** 국내 종목군(Task 4)과 매일 덧붙이기(Task 5 의 `KrDailySource`)는 네이버 시가총액 순위 조회를 읽는다. KOSPI 4페이지, KOSDAQ 2페이지.
- **걸러 내는 기준**: `stockEndType == "stock"`, 종목코드가 `0` 으로 끝남, 이름에 "스팩" 없음, 이름이 "리츠"로 끝나지 않음. 이름으로 우선주를 잡지 않는다(`성우` 오탐). "리츠" 포함으로 보지 않는다(`메리츠금융지주` 오탐).
- **순위 조회의 응답은 완전히 정렬돼 있지 않고, 장중에는 페이지 사이에 종목이 겹치거나 빠진다.** 종목코드로 중복을 없애고 직접 정렬한다.
- **`Bar` 는 종가와 거래량이 필수, 시·고·저는 선택값이다** (Task 3). 매일 덧붙이는 행에는 시·고·저가 없다.
- **장중이면 매일 덧붙이기를 하지 않는다.** `marketStatus` 와 `localTradedAt` 으로 판정한다.
- **어긋남 감지** (Task 6): "오늘 종가 − 전일 대비"가 저장된 전일 종가와 상대 0.5% 넘게 다르면 그 종목만 FDR 로 다시 받는다.
- **동점 처리** (Task 7): 점수 → 당일 등락률(내림차순) → 종목코드. 52주 고가 비율이 1 인 종목이 하루에 9개 나왔다.
- **최소 거래대금**: 국내 20일 평균 10억 원. 미국은 미정.
- **관심 종목 기본값** (Task 2): 국내 005930, 000660, 402340, 009150, 373220, 005380, 105560, 207940, 032830, 028260. 미국 NVDA, AAPL, GOOGL, MSFT, AMZN, META, AVGO, TSLA, BRK-B, LLY. 사용자 확인 대기.
- **국내 350종목의 처음 받기는 약 2분이다** (실측 116.6초, 실패 0).
- **미국 쪽 수치** (Task 9, 2026-10-08): 묶음 100, 간격 1초, 처음 받기 400일치, 최소 거래대금 2천만 달러. 503종목 400일치가 17초, 차단 없음.
- **장중 판정은 `marketStatus` 문자열에 기대지 않는다.** 행의 날짜가 `expected_session(Market.KR, now)` 이하일 때만 저장한다.

## Task 별 설계 메모

### Task 1 — PoC: 대량 일봉 조회·종목군 걸러 내기·어긋남 감지·관심 종목 선정

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `docs/01_research/2026-10-08_screening-poc.md` | — | 신규. 7개 항목의 결과와 결정 |
| (scratch) 일회성 스크립트 | — | 커밋하지 않는다 |

**먼저 쓸 테스트**
- 없음 (탐색). 대신 아래에 답한다.
  1. FDR 로 국내 350종목의 1년 일봉을 종목별로 받는 시간, 실패·차단 여부.
  2. `yf.download` 로 미국 500종목 × 1년치: 묶음 50·100·250 별 시간과 차단 여부. 차단되면 풀리는 시간.
  3. 미국 500종목의 최근 5일 묶음 조회 시간. `StockListing('KRX')` 가 주는 값의 날짜가 실행 시각(장중·마감 뒤·개장 전)에 따라 무엇인지.
  4. 국내 목록에서 우선주·ETF·ETN·스팩·리츠를 걸러 내는 기준 (`Dept`, 이름, 종목코드 끝자리).
  5. 국내 FDR 이력이 수정주가인지. 최근 분할 종목 하나로 "겹친 날의 종가가 달라지는가".
  6. 종목군 안의 거래대금 분포와 최소 거래대금 기준값.
  7. 관심 종목 기본 20개 (국내는 `Marcap` 상위, 미국은 시가총액 출처를 정한다).

**엣지 케이스**
- 2번에서 차단되면 같은 IP 로 하는 다른 Yahoo 호출(브리핑의 지수 시세)도 막힐 수 있다 → **작은 묶음부터** 시험하고, 차단되면 즉시 멈춘다. 오늘 밤 미국 개장 브리핑을 보낼 계획이면 그 뒤에 시험한다.
- KRX 목록이 그 시각에 404 일 수 있다 (FDR 이슈 #282) → 시각을 적고 나중에 다시 시도한다.
- 결과가 "미국 불가"면 플랜의 롤백 절대로 국내만 진행한다. 문서에 그 결정을 적는다.

**완료 판정**
```bash
python -c "import pathlib;t=pathlib.Path('docs/01_research/2026-10-08_screening-poc.md').read_text(encoding='utf-8');assert all(k in t for k in ['yf.download', 'StockListing', '거래대금', '관심 종목', '수정주가'])"
```

### Task 2 — 관심 종목 시세

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/collect/models.py` | `Market.KR_STOCK`, `Market.US_STOCK` | 수정 |
| `src/finbrief_analyzer/core/config.py` | `DEFAULT_WATCHLIST`, `Settings.watchlist: tuple[QuoteSymbol, ...]` | 수정 |
| `src/finbrief_analyzer/collect/service.py` | `collect_snapshot(..., symbols)` 호출부 — 관심 종목을 심볼 목록에 합친다 | 수정 (`jobs/run_briefing.py` 의 `open_deps` 가 `quote_symbols + watchlist` 를 넘긴다) |
| `src/finbrief_analyzer/collect/quotes_yf.py` | `YfQuoteProvider.supports`, 티커 변환 | 수정. 매핑에 없으면 그대로 통과하되 국내 6자리 코드는 지원하지 않는다고 답한다 |
| `src/finbrief_analyzer/compose/simple.py` | `GROUP_TITLES`, `GROUP_ORDER` | 수정. "국내 관심 종목", "미국 관심 종목" |
| `.env.example` | — | `APP_WATCHLIST` 예시 |
| `tests/collect/test_service.py`, `tests/compose/test_simple.py`, `tests/test_config.py`, `tests/collect/test_quotes_backup.py` | — | 수정 |

**먼저 쓸 테스트**
- `관심 종목 기본값은 국내 10개와 미국 10개이고 지수 심볼과 겹치지 않는다`
- `관심 종목을 빈 배열로 설정하면 관심 종목이 없다`
- `관심 종목은 지수와 함께 한 번의 요청 목록으로 수집된다`
- `관심 종목 하나를 못 가져오면 missing 에 올라가고 나머지는 실린다`
- `관심 종목의 기준일이 오래돼도 시장을 휴장으로 판정하지 않는다`
- `작성기는 국내 관심 종목과 미국 관심 종목을 따로 묶는다`
- `관심 종목 묶음은 지수·금리·환율 묶음 뒤에 온다`
- `미국 개장 브리핑에서도 관심 종목 묶음의 순서는 같다`
- `매핑에 없는 미국 티커는 예비 출처가 그대로 조회한다`
- `국내 6자리 종목코드는 yfinance 예비가 지원하지 않는다고 답한다`

**엣지 케이스**
- 휴장 판정(`_closed_markets`)은 `Market.KR`·`US` 인 시세만 본다. 관심 종목은 새 `Market` 값이라 끼어들지 않는다 — 거래정지 종목 하나가 "국내 휴장"을 만들면 안 된다.
- 국내 종목의 가격은 원 단위 정수다. 소수 둘째 자리 표기("71,500.00")가 어색하다 → 값이 정수이고 1,000 이상이면 소수를 뺀다. 지수 표기는 바뀌지 않아야 한다.
- 장중에 실행하면 장중 값이 실린다 (지수와 같은 성질). 이 Task 에서 고치지 않는다.
- 필수 섹션 판정: 관심 종목 묶음이 "첫 번째로 값이 있는 묶음"이 될 수 있다 (지수가 전부 실패한 날). 그 경우에도 발송 가능이다 — 기존 규칙 그대로.
- 심볼 20개가 늘어 수집 시간이 늘어난다. 실측해 구현 노트에 적는다.

**완료 판정**
```bash
uv run pytest tests/collect tests/compose tests/test_config.py && uv run ruff check . && uv run mypy && uv run pytest
```
수동 확인: 본문 미리 뽑기로 20종목이 실리는지.

### Task 3 — 일봉·종목군 스키마와 저장소

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/screen/__init__.py`, `screen/models.py` | `Bar`(symbol, day, open, high, low, close, volume), `Member`(market, symbol, name) | 신규. frozen dataclass |
| `src/finbrief_analyzer/store/tables.py` | `price_bars`(symbol, day, open, high, low, close, volume, 유일 제약 2열), `universe_members`(market, symbol, name, as_of) | 수정 |
| `src/finbrief_analyzer/store/price_bars.py` | `add_bars(session, bars)`, `history(session, symbol, since)`, `last_days(session, symbols)`, `delete_symbol(session, symbol)` | 신규 |
| `src/finbrief_analyzer/store/universe.py` | `replace_members(session, market, members, as_of)`, `members(session, market)`, `built_on(session, market)` | 신규 |
| `src/finbrief_analyzer/migrations/versions/0002_price_bars_universe.py` | `upgrade`, `downgrade` | 신규 |
| `tests/store/test_price_bars.py`, `tests/store/test_universe.py` | — | 신규 |
| `tests/store/test_delivery_log.py` | 마이그레이션 왕복·열 비교 테스트 | 그대로 통과해야 한다 (새 테이블을 자동으로 본다) |

**먼저 쓸 테스트**
- `같은 종목·날짜를 두 번 넣어도 한 행만 남고 값은 처음 것이다`
- `이미 있는 날과 새 날이 섞인 묶음에서 새 날만 들어간다`
- `이력은 날짜 오름차순으로 돌아온다`
- `since 이전의 행은 돌아오지 않는다`
- `종목별 마지막 날짜를 한 번의 조회로 읽는다`
- `이력이 없는 종목은 마지막 날짜 결과에 없다`
- `한 종목을 지워도 다른 종목의 이력은 남는다`
- `종목군 교체 뒤에는 새 구성만 남는다`
- `한 시장의 종목군 교체가 다른 시장의 구성을 건드리지 않는다`
- `종목군이 만들어진 날짜를 읽는다`

**엣지 케이스**
- 넣기는 `ON CONFLICT` 를 쓰지 않는다 (PoC 6번 결정: SQLite·Postgres 공통). 이미 있는 (종목, 날짜)를 먼저 읽어 뺀 뒤 넣는다. 발송 작업은 한 번에 하나만 돌므로 경합은 없다고 본다 — 전제를 주석으로 남긴다.
- 850종목 × 250행 = 약 21만 행. 한 문장에 전부 넣지 않고 종목 단위로 넣는다.
- 거래량은 정수지만 미국 대형주는 32비트를 넘는다 → `BigInteger`.
- 가격은 `Float`. `Numeric` 은 SQLite 에서 경고가 난다.
- 수정주가 여부(Task 1-5)에 따라 수정 종가 열이 필요할 수 있다 → Task 1 의 결정을 따른다.

**완료 판정**
```bash
uv run pytest tests/store && uv run ruff check . && uv run mypy && uv run pytest
```
수동 확인: 로컬 postgres 에서 `uv run alembic upgrade head` → `downgrade -1` → `upgrade head`.

### Task 4 — 종목군 구성 (시가총액 순위)

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/screen/universe.py` | `Listing`(code, name, market, marcap, dept), `pick_kr(listings, kospi_n, kosdaq_n)`, `is_common_stock(listing)`, `refresh_universe(session, sources, today, settings)`, `ListingSource`(Protocol) | 신규 |
| `src/finbrief_analyzer/core/config.py` | `screen_kospi_size`(200), `screen_kosdaq_size`(150) | 수정 |
| `tests/screen/__init__.py`, `tests/screen/test_universe.py` | — | 신규 |

**먼저 쓸 테스트**
- `시가총액 상위 N 개를 시장별로 자른다`
- `우선주는 순위에 들어가지 않는다`
- `ETF·스팩은 순위에 들어가지 않는다`
- `시가총액이 같으면 종목코드 순으로 결과가 항상 같다`
- `목록이 비어 오면 기존 종목군을 지우지 않는다`
- `목록 출처가 예외를 던져도 기존 종목군이 남고 예외가 밖으로 나가지 않는다`
- `같은 달에는 종목군을 다시 계산하지 않는다`
- `달이 바뀌면 종목군을 다시 계산한다`
- `종목군이 아직 없으면 달과 무관하게 계산한다`
- `미국 종목군은 목록의 종목을 그대로 쓴다`

**엣지 케이스**
- 제외 기준은 Task 1-4 의 결과를 그대로 쓴다. 여기서 새로 정하지 않는다.
- 목록의 종목 수가 평소의 절반 이하면 부분 응답으로 보고 교체하지 않는다 (FDR 이슈 #288: "KRX 에 KOSPI 누락").
- 종목군에서 빠진 종목의 이력은 지우지 않는다. 다시 들어올 수 있고 백테스트에 쓴다.
- 실제 목록 조회 함수(FDR 호출)는 이 Task 에 두되 `# pragma: no cover - network`. 표 → `Listing` 변환은 테스트한다.

**완료 판정**
```bash
uv run pytest tests/screen/test_universe.py && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 5 — 일봉 출처 어댑터

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/screen/sources.py` | `frame_bars(symbol, frame)`, `FdrHistorySource.history(symbol, since)`, `YfBatchSource.recent(symbols, since)`, `KrDailySource.day(day)`, `BatchResult`(bars, failed) | 신규 |
| `src/finbrief_analyzer/core/config.py` | `screen_batch_size`, `screen_batch_pause_seconds` | 수정. 기본값은 Task 1-2 의 결과 |
| `tests/screen/test_sources.py` | 가짜 fetch | 신규 |

**먼저 쓸 테스트**
- `표의 한 행이 시·고·저·종·거래량을 가진 Bar 가 된다`
- `종가가 NaN 인 행은 버린다`
- `거래량이 NaN 이면 0 으로 읽는다`
- `묶음 조회는 설정된 크기로 종목을 나눈다`
- `묶음 사이에 설정된 간격만큼 쉰다`
- `마지막 묶음 뒤에는 쉬지 않는다`
- `한 묶음이 실패해도 나머지 묶음의 결과가 돌아온다`
- `실패한 묶음의 종목은 failed 에 들어 있다`
- `묶음 응답에 없는 종목은 failed 에 들어 있다`
- `국내 하루치는 종목군에 속한 종목만 Bar 로 만든다`
- `국내 하루치의 Bar 날짜는 호출자가 준 날짜다`

**엣지 케이스**
- 쉬는 함수(`sleep`)는 주입한다. 테스트가 실제로 기다리지 않는다.
- `yf.download` 의 다중 종목 결과는 열이 2단이다. 종목 하나만 넘기면 모양이 달라질 수 있다 → 묶음이 1개여도 같은 경로를 타게 한다.
- yfinance 인덱스에는 시간대가 있고 FDR 은 없다 (data-source-poc). 날짜만 꺼낸다.
- 국내 전 종목 하루치는 응답에 날짜가 없다 → 날짜는 호출자(Task 6)가 `expected_session` 으로 정해서 준다. 장중에는 부르지 않는다.
- 차단 응답(`YFRateLimitError`)은 그 묶음의 실패로 보고 **남은 묶음을 시도하지 않는다** (더 부르면 차단이 길어진다).
- `Any` 는 pandas 경계에만. 이유를 주석으로 (기존 `quotes_base.Fetch` 와 같은 방식).

**완료 판정**
```bash
uv run pytest tests/screen/test_sources.py && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 6 — 이력 갱신과 처음 받기 명령

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/screen/history.py` | `backfill(engine, members, source, since, deadline)`, `update_recent(engine, members, sources, now, deadline)`, `_mismatched(stored, fetched)`, `UpdateReport`(added, refetched, failed, skipped) | 신규 |
| `src/finbrief_analyzer/jobs/backfill_prices.py` | `main(argv)`, `run(deps)` | 신규 |
| `src/finbrief_analyzer/core/config.py` | `screen_history_days`(400), `screen_update_seconds`(상한) | 수정 |
| `tests/screen/test_history.py`, `tests/jobs/test_backfill_prices.py` | — | 신규 |

**먼저 쓸 테스트**
- `이력이 없는 종목만 처음 받기 대상이다`
- `처음 받기를 다시 실행하면 이미 받은 종목은 건너뛴다`
- `매일 갱신은 마감이 끝나지 않은 날의 행을 저장하지 않는다`
- `매일 갱신은 마지막으로 저장된 날 다음 날부터 들어간다`
- `겹친 날의 종가가 저장된 값과 같으면 다시 받지 않는다`
- `겹친 날의 종가가 허용 오차를 넘게 다르면 그 종목을 지우고 다시 받는다`
- `출처가 실패한 종목은 저장된 이력이 그대로 남는다`
- `시간 상한을 넘으면 남은 종목을 건너뛰고 건너뛴 수를 보고한다`
- `처음 받기 명령은 받은 수와 실패 수를 로그에 남기고 0 으로 끝난다`
- `DB 설정이 없으면 처음 받기 명령은 0 이 아닌 코드로 끝난다`

**엣지 케이스**
- 허용 오차: 부동소수 비교라 상대 오차로 본다. 기준값은 Task 1-5 에서 본 분할의 크기로 정한다 (배당락 같은 작은 조정에 매번 다시 받지 않게).
- 다시 받기가 실패하면 지운 이력을 잃는다 → **받은 뒤에** 지우고 넣는다. 한 트랜잭션.
- 주말·휴장일에는 새 행이 없다. 오류가 아니다.
- PC 가 며칠 꺼져 있었다면 국내 하루치 호출로는 빈 날을 못 메운다 → 마지막 저장일이 직전 거래일보다 오래된 종목은 종목별 이력 조회로 받는다.
- 시각은 `now` 를 주입한다. `deadline` 도 주입한 시계로 판정한다.
- 처음 받기는 오래 걸린다. 중간에 끊겨도 다시 실행하면 이어서 받는다 (첫 두 테스트가 보장).

**완료 판정**
```bash
uv run pytest tests/screen/test_history.py tests/jobs && uv run ruff check . && uv run mypy && uv run pytest
```
수동 확인: `uv run python -m finbrief_analyzer.jobs.backfill_prices` → 로컬 DB 의 종목 수와 행 수.

### Task 7 — 규칙 (52주 고가 근접·거래량 급증)

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/screen/models.py` | `ScreenHit`(symbol, name, close, change_pct, score), `ScreenResult`(rule, market, as_of, hits) , `Rule`(StrEnum) | 수정 |
| `src/finbrief_analyzer/screen/rules.py` | `high_ratio(bars, window=252)`, `volume_ratio(bars, window=20)`, `trading_value(bars, window=20)`, `rank(scores, top)` | 신규 |
| `tests/screen/test_rules.py` | — | 신규 |

**먼저 쓸 테스트**
- `52주 고가 비율은 마지막 종가를 최근 252거래일의 최고 종가로 나눈 값이다`
- `마지막 날이 최고가면 비율은 1 이다`
- `이력이 기준 일수보다 짧으면 점수가 없다`
- `거래량 비율은 마지막 날 거래량을 직전 20일 평균으로 나눈 값이다`
- `마지막 날의 거래량은 평균에 들어가지 않는다`
- `직전 평균 거래량이 0 이면 점수가 없다`
- `평균 거래대금은 종가와 거래량의 곱의 평균이다`
- `순위는 점수 내림차순 상위 N 개다`
- `동점은 종목코드 오름차순으로 결과가 항상 같다`
- `점수가 없는 종목은 순위에 없다`
- `종목이 N 개보다 적으면 있는 만큼만 돌려준다`

**엣지 케이스**
- 이 모듈은 pandas·DB·네트워크를 import 하지 않는다. 표준 라이브러리만.
- 252거래일이 안 되는 신규 상장 종목 → 점수 없음. "상장 후 최고가"를 52주 고가로 부르지 않는다.
- 52주 고가는 **종가** 기준이다 (George·Hwang 의 정의). 장중 고가를 쓰지 않는다.
- 거래정지 종목은 거래량 0 이 이어진다 → 평균 0 으로 빠진다.
- 입력이 날짜순이 아니어도 결과가 같아야 한다 (함수 안에서 정렬하거나, 정렬됐다는 전제를 테스트로 고정).

**완료 판정**
```bash
uv run pytest tests/screen/test_rules.py && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 8 — 수집·작성에 연결하고 메일에 싣기

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/screen/service.py` | `ScreenService.run(now)` → `tuple[ScreenResult, ...]`, `_screen_market(...)` | 신규. 갱신 → 이력 읽기 → 규칙 → 결과 |
| `src/finbrief_analyzer/collect/models.py` | `MarketSnapshot.screens` | 수정 |
| `src/finbrief_analyzer/collect/service.py` | `Providers.screens`, `_collect_screens(...)` | 수정. 실패하면 `missing` 에 `"screen"` |
| `src/finbrief_analyzer/core/config.py` | `screen_enabled`(기본 False), `screen_top`(5), `screen_min_trading_value_*` | 수정 |
| `src/finbrief_analyzer/deliver/models.py`, `deliver/render.py` | `Briefing.footnotes`, 본문 아래 렌더링 | 수정 |
| `src/finbrief_analyzer/compose/simple.py` | `_screen_sections(snapshot)`, `_hit_line(hit)`, `DISCLAIMER` | 수정 |
| `src/finbrief_analyzer/jobs/run_briefing.py` | `open_deps` 에 스크리닝 배선 | 수정 |
| `.env.example` | `APP_SCREEN_*` 예시 | 수정 |
| `tests/screen/test_service.py`, `tests/compose/test_simple.py`, `tests/deliver/test_render.py`, `tests/collect/test_service.py`, `tests/jobs/test_run_briefing.py` | — | 신규/수정 |

**먼저 쓸 테스트**
- `스크리닝 결과가 스냅샷에 실린다`
- `스크리닝이 예외를 던지면 missing 에 screen 이 올라가고 시세와 뉴스는 그대로다`
- `스크리닝 제공자가 없으면 결과도 missing 항목도 없다`
- `조건 충족 섹션의 제목에 추천이라는 말이 없다`
- `조건 충족 섹션은 규칙 설명 한 줄과 기준일을 가진다`
- `조건 충족 종목 한 줄은 이름·종가·등락률·규칙 점수를 가진다`
- `조건 충족 섹션은 시세와 관심 종목 뒤, 뉴스 앞에 온다`
- `결과가 빈 규칙은 섹션을 만들지 않는다`
- `조건 충족 섹션이 하나라도 있으면 고지 문구가 각주에 있다`
- `조건 충족 섹션이 없으면 각주도 없다`
- `각주는 text 본문과 HTML 본문의 맨 아래에 있다`
- `조건 충족 섹션만 있고 시세가 없으면 발송 불가다`
- `스크리닝이 꺼져 있으면 발송 작업이 스크리닝 의존성을 만들지 않는다`

**엣지 케이스**
- `screen_enabled` 의 기본값은 False 다. 처음 받기를 하지 않은 DB 에서 켜지면 발송 작업이 850종목을 받으려 든다. 켜는 것은 사용자가 `.env` 에서 한다.
- 이력이 없는 상태에서 켜졌다면: 시간 상한 안에서 받을 수 있는 만큼만 받고, 규칙은 이력이 충분한 종목에만 적용된다. 결과가 비면 섹션이 없다.
- 기준일이 시장마다 다르다 (국내는 어제, 미국은 간밤). 섹션마다 따로 적는다.
- 종목 이름에 외부 문자열이 들어온다 → 렌더러의 이스케이프가 그대로 적용되는지 테스트로 확인한다.
- 메일 길이: 규칙 2개 × 시장 2개 × 5개 = 최대 20줄 + 관심 종목 20줄.
- 고지 문구 초안은 구현 전에 사용자에게 보여 준다 (플랜의 "사용자 확인이 필요한 것").
- 필수 섹션 판정을 바꾸지 않는다. 스크리닝 섹션은 `required=False` 이고 "첫 번째로 값이 있는 시세 묶음"의 계산에 들어가지 않는다.

**완료 판정**
```bash
uv run pytest tests/compose tests/collect tests/jobs tests/deliver && uv run ruff check . && uv run mypy && uv run pytest
```
수동 확인: `.env` 에 `APP_SCREEN_ENABLED=true` → 아직 보내지 않은 슬롯으로 `run_briefing` → 메일 1통.

## Task 간 의존 중 하네스에 못 건 것
- **이 주제 전체가 `delivery-channels` 의 Task 2~7·9 위에 서 있다** (작성기, DB 기반, 발송 작업). 그 커밋들은 `feat/delivery-email-smtp` 에 있고 main 에 들어가지 않았다. 브랜치를 그 위에서 판다.
- Task 3 의 마이그레이션 번호 `0002` 는 `0001`(delivery-channels Task 4) 다음이다.

## 열어둔 질문
- **브랜치.** `feat/stock-screening` 을 `feat/delivery-email-smtp` 위에서 파는 것을 제안한다. 이슈는 만들지 않았다. 앞 브랜치는 15개 커밋이 main 앞에 있고 push 하지 않은 상태다 — 먼저 PR 로 올릴지는 사용자가 정한다.
- **오늘 밤 미국 개장 브리핑을 보낼 것인가.** 보낸다면 Task 1 의 Yahoo 대량 조회 시험은 그 뒤에 한다 (차단되면 브리핑의 지수 시세도 막힐 수 있다).
- 관심 종목 20개와 고지 문구는 각각 Task 1·Task 8 에서 사용자 확인을 받는다.
- 리서치·분석·플랜·태스크 문서 4개가 아직 커밋되지 않았다.

## Task 1 을 둘로 나눴다 (2026-10-08)
- Task 1 의 국내 부분과 관심 종목 선정은 끝났다. 미국 500종목 대량 조회는 오늘 밤 미국 개장 브리핑 뒤에 한다 (사용자 결정).
- 하네스가 Task 1 이 끝나기 전에는 Task 2 를 시작하지 못하게 막아서, 남은 부분을 **Task 9 "PoC 나머지: 미국 500종목 대량 조회"** 로 떼어 냈다.
- **하네스에 못 건 의존**: Task 5(일봉 출처 어댑터)의 미국 묶음 조회와 Task 6(처음 받기)의 미국 부분은 Task 9 가 끝나야 값(묶음 크기·간격)을 정할 수 있다. Task 5·6 을 시작하기 전에 Task 9 가 done 인지 확인한다.
