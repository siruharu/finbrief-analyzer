---
type: task
project: finbrief-analyzer
topic: data-sources
created: 2026-10-07
source_plan: "[[2026-10-07_data-sources]]"
branch: feat/data-sources-collect
issue: #
tags: [task]
next: implementation
---

# ✅ 작업: 데이터 출처 (시세·뉴스 수집)

> **작업 상태의 정본은 이 문서가 아니라 `data-sources.tasks.json` 이다.**
> 체크박스를 여기에 다시 적지 않는다 — 두 곳을 손으로 맞추면 반드시 어긋난다.
>
> ```bash
> .claude/hooks/harness.py stage task data-sources
> .claude/hooks/harness.py task list
> .claude/hooks/harness.py task next
> ```
>
> 이 문서는 **왜 이렇게 쪼갰는지**를 적는 곳이다.

## 쪼갠 기준
- **PoC 를 맨 앞에 뒀다.** 심볼 표기, 발송 시각의 데이터 가용성, 금리 출처가 틀리면 Task 4·6 의 코드가 통째로 바뀐다. 코드가 0줄일 때 확인한다.
- **모델(Task 2)과 설정(Task 3)을 어댑터보다 먼저.** 어댑터 5개가 같은 타입과 같은 `Settings` 필드에 기대므로 이 둘이 먼저 굳어야 어댑터를 순서 없이 만들 수 있다.
- **어댑터는 출처당 1 Task.** 서로 import 하지 않아서 하나가 막혀도 나머지가 진행된다. 출처가 틀렸을 때 되돌리는 단위도 커밋 하나다.
- **폴백(Task 5)을 FDR 어댑터(Task 4)와 나눴다.** Task 4 만으로도 시세가 나온다. 폴백은 "깨졌을 때"의 동작이라 테스트 성격이 다르다.
- **조립(Task 10)은 Task 6·9 를 기다리지 않는다.** 금리는 PoC 결과에 따라 빠질 수 있고 DART 는 보조 재료다. 조립은 "제공자 목록"을 받으므로 둘은 나중에 끼워도 된다.

## 공통 규칙
- 완료 판정의 `uv run ruff check . && uv run mypy && uv run pytest` 는 `make check` 와 같은 내용이다. 이 PC 에 `make` 가 없어 풀어서 적었다.
- 테스트는 네트워크를 타지 않는다. 외부 호출은 생성자 주입(`fetch` 함수 또는 `httpx.Client`)으로 바꿔 끼운다.
- 테스트는 Given/When/Then 주석 구조, 이름은 보장하는 성질을 말한다.
- 함수 30줄 이하. 주석·식별자는 영어.
- `.env` 의 실제 키 값은 읽어서 문서·로그·커밋에 옮기지 않는다. 키 이름만 다룬다.

## PoC 이후 바뀐 것 (2026-10-07 사용자 결정)
근거는 `docs/01_research/2026-10-07_data-source-poc.md`. 아래 Task 별 메모와 어긋나면 이 절이 우선한다.
- **Task 2**: 값은 `float`. `Quote` 는 심볼·종가·전일 종가·기준일만 가진다. 금리·환율도 같은 `Quote` 로 싣는다.
- **Task 3**: 기본 시세 심볼은 `^KS11`, `^KQ11`, `US500`, `IXIC`, `DJI`, `US10YT` (국내 2·미국 3·미 국채 1). **환율은 심볼 목록에서 뺀다.** 의존성에 `defusedxml` 추가.
- **Task 5**: 국내 지수의 예비는 yfinance 가 아니라 **네이버**(`fchart.stock.naver.com/siseJson.nhn`)다. 미국 지수의 예비는 yfinance 그대로.
- **Task 6**: 막지 않는다. ECOS 로 기준금리·국고채 3년·10년과 **원/달러 매매기준율**을 가져온다.

## Task 별 설계 메모

### Task 1 — PoC: 출처별 심볼·가용성·금리 출처·RSS 구조 확인

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `docs/01_research/2026-10-07_data-source-poc.md` | — | 신규. 항목별 "됨 / 안 됨 / 대안"과 확정 심볼 표 |
| (scratch) 일회성 스크립트 | — | 커밋하지 않는다. 저장소 밖 임시 폴더에서 실행 |

**먼저 쓸 테스트**
- 없음 (탐색 Task). 대신 아래 6개 질문에 답을 적는다.
  1. FinanceDataReader 로 KOSPI·KOSDAQ·S&P 500·나스닥·다우·원/달러의 최근 종가와 전일 종가가 나오는가. 심볼 표기는.
  2. 15:30 KST 이후 같은 날에 당일 국내 종가가 나오는가. 09:00 KST 에 전일 미국 종가가 나오는가.
  3. yfinance 로 미국 3대 지수가 같은 값으로 나오는가.
  4. ECOS: 키로 기준금리·국고채 금리가 조회되는가, 호출 한도·이용 조건은. 미국 국채 금리를 얻을 출처는.
  5. 한국경제·매일경제·연합뉴스 경제 RSS 의 항목 구조(요약 길이, 발행 시각 형식, 인코딩)와 XML 파서 선택.
  6. Marketaux 가 요청당 3건·언어 필터대로 동작하는가. DART `list.json` 의 응답 필드.

**엣지 케이스**
- 주말·휴장일에 조회하면 무엇이 돌아오는가 (마지막 거래일 값인지, 빈 값인지).
- 키가 잘못됐을 때의 응답 모양 (Task 6·8·9 의 오류 처리 근거가 된다).
- 스크레이핑 출처가 연속 호출에서 차단(429)을 내는지.
- 금리 출처를 못 찾으면: Task 6 을 `task block` 으로 막고 플랜에 "금리는 v1 제외"를 적는다.

**완료 판정**
```bash
python -c "import pathlib;t=pathlib.Path('docs/01_research/2026-10-07_data-source-poc.md').read_text(encoding='utf-8');assert all(k in t for k in ['FinanceDataReader', 'yfinance', 'ECOS', 'RSS', 'Marketaux', 'DART'])"
```

### Task 2 — 도메인 모델과 제공자 인터페이스

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/collect/__init__.py` | — | 신규 (빈 패키지) |
| `src/finbrief_analyzer/collect/models.py` | `Slot`(StrEnum: `KR_OPEN`, `US_OPEN`), `Market`, `Quote`, `NewsItem`, `MarketSnapshot`, `CollectError` | 신규. frozen dataclass |
| `src/finbrief_analyzer/collect/ports.py` | `QuoteProvider`, `RateProvider`, `NewsProvider` (`Protocol`) | 신규 |
| `tests/collect/__init__.py`, `tests/collect/test_models.py` | — | 신규 |

**먼저 쓸 테스트**
- `Quote 가 종가와 전일 종가를 가지면 등락률을 백분율로 계산한다`
- `Quote 의 전일 종가가 없으면 등락률은 None 이다`
- `Quote 의 전일 종가가 0 이면 등락률은 None 이다`
- `MarketSnapshot 은 누락된 출처 이름을 순서대로 보존한다`
- `MarketSnapshot 은 휴장으로 표시된 시장을 조회할 수 있다`
- `NewsItem 은 링크가 같으면 같은 항목으로 취급된다`

**엣지 케이스**
- 등락률 계산의 부동소수 오차 → `Decimal` 로 보관할지 Task 1 의 값 형식을 보고 정한다.
- 발행 시각은 시간대가 있는 `datetime` 만 허용한다 (naive 값은 생성 시 거부).
- 시세 0건·뉴스 0건인 스냅샷도 유효한 값이다.

**완료 판정**
```bash
uv run pytest tests/collect/test_models.py && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 3 — 설정과 의존성 (버전 고정)

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `pyproject.toml` | `dependencies`, `[[tool.mypy.overrides]]` | httpx(런타임)·finance-datareader·yfinance 추가와 버전 고정. override 는 두 라이브러리 모듈만 |
| `src/finbrief_analyzer/core/config.py` | `Settings` | `marketaux_token`, `dart_api_key`, `ecos_api_key` (`SecretStr | None`), `kr_rss_feeds`, `quote_symbols`, `marketaux_max_calls_per_slot`, `http_timeout_seconds` |
| `.env.example` | — | 새 변수 이름과 빈 값 |
| `deploy/terraform/service/terraform.tfvars.example` | `secrets` | 키 3개의 ARN 예시(주석) |
| `tests/test_config.py` | — | 신규 |

**먼저 쓸 테스트**
- `APP_MARKETAUX_TOKEN 이 설정되면 SecretStr 로 읽히고 repr 에 값이 나오지 않는다`
- `API 키가 없으면 해당 필드는 None 이다`
- `피드 URL 목록은 기본값을 가지며 환경변수로 덮어쓸 수 있다`
- `심볼 목록은 기본값으로 국내 2개·미국 3개·환율 1개를 가진다`
- `타임아웃이 0 이하이면 Settings 생성이 실패한다`

**엣지 케이스**
- 사용자의 `.env` 에 이미 들어 있는 키 이름이 위 필드명과 다를 수 있다 → Task 시작 시 **이름만** 대조한다 (값은 읽지 않는다).
- `extra="ignore"` 라 오타 난 환경변수는 조용히 무시된다 → 필수 키 누락은 "제공자 비활성"으로 드러나게 한다.
- 목록형 환경변수의 파싱 형식(JSON 배열)을 `.env.example` 에 예시로 남긴다.
- `get_settings()` 의 `lru_cache` 때문에 테스트 간 값이 샌다 → 테스트에서 `Settings()` 를 직접 만든다.

**완료 판정**
```bash
uv run pytest tests/test_config.py && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 4 — FinanceDataReader 시세 어댑터

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/collect/quotes_fdr.py` | `FdrQuoteProvider.__init__(fetch)`, `.get_quotes(symbols)`, `_to_quote(symbol, frame)` | 신규. `fetch` 기본값만 실제 라이브러리를 부른다 |
| `tests/collect/test_quotes_fdr.py` | — | 신규. 가짜 `fetch` 가 작은 표를 돌려준다 |

**먼저 쓸 테스트**
- `조회 결과가 2행 이상이면 마지막 행을 종가, 그 앞 행을 전일 종가로 한 Quote 를 만든다`
- `조회 결과가 1행이면 전일 종가가 없는 Quote 를 만든다`
- `조회 결과가 비어 있으면 CollectError 를 던진다`
- `조회 함수가 예외를 던지면 원인을 담은 CollectError 로 바꿔 던진다`
- `종가 칸이 NaN 인 행은 건너뛰고 그 앞의 유효한 행을 쓴다`
- `Quote 의 기준일은 표의 마지막 유효 행 날짜다`

**엣지 케이스**
- 장중 조회 시 당일 행이 미완성 값으로 들어오는지 (Task 1-2 결과 반영).
- 심볼마다 열 이름이 다를 가능성 (`Close` 등) → Task 1 에서 확인한 열 이름만 지원하고 그 외는 오류.
- pandas 타입은 `_to_quote` 안에서 끝낸다. 반환값에 `Any` 가 남지 않게 한다.
- 조회 기간은 최근 10일 정도로 잡아 연휴 뒤에도 전일 종가가 잡히게 한다.

**완료 판정**
```bash
uv run pytest tests/collect/test_quotes_fdr.py && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 5 — yfinance 예비 어댑터와 폴백 합성

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/collect/quotes_yf.py` | `YfQuoteProvider.__init__(fetch)`, `.get_quotes(symbols)`, `.supports(symbol)` | 신규. 미국 지수만 지원 |
| `src/finbrief_analyzer/collect/quotes_fallback.py` | `FallbackQuoteProvider.__init__(primary, backup)`, `.get_quotes(symbols)`, `QuoteResult`(quotes, missing) | 신규 |
| `tests/collect/test_quotes_fallback.py` | — | 신규. 가짜 제공자 2개 |

**먼저 쓸 테스트**
- `1차 제공자가 모든 심볼에 성공하면 예비 제공자를 호출하지 않는다`
- `1차 제공자가 실패한 심볼만 예비 제공자로 넘긴다`
- `두 제공자 모두 실패한 심볼은 결과에서 빠지고 missing 에 들어간다`
- `예비 제공자가 지원하지 않는 심볼은 예비로 넘기지 않고 missing 에 넣는다`
- `폴백 제공자는 어떤 경우에도 예외를 던지지 않는다`
- `yfinance 어댑터는 차단 응답을 CollectError 로 바꾼다`

**엣지 케이스**
- 두 출처의 심볼 표기가 다르다 (예: 같은 지수의 서로 다른 티커) → 내부 심볼 → 출처별 티커 매핑 표를 어댑터가 가진다.
- 1차가 심볼 단위가 아니라 호출 전체로 실패하는 경우 → 심볼별로 나눠 호출해 부분 성공을 살린다.
- 예비 출처 값이 1차와 기준일이 다를 수 있다 → `Quote.as_of` 를 그대로 싣고 맞추지 않는다.

**완료 판정**
```bash
uv run pytest tests/collect/test_quotes_fallback.py && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 6 — 금리 어댑터 (PoC 결과에 따라 조건부)

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/collect/rates.py` | `EcosRateProvider.__init__(client, api_key)`, `.get_rates(codes)`, `_parse(payload)` | 신규. 출처가 ECOS 가 아니면 이름과 구조를 Task 1 결과에 맞춘다 |
| `tests/collect/fixtures/ecos_rate.json` | — | 신규. Task 1 에서 받은 실제 응답을 줄인 것(키 제거) |
| `tests/collect/test_rates.py` | — | 신규. `httpx.MockTransport` |

**먼저 쓸 테스트**
- `샘플 응답에서 가장 최근 값과 직전 값을 뽑아 Quote 로 만든다`
- `인증 실패 응답이면 CollectError 를 던진다`
- `값 목록이 비어 있으면 CollectError 를 던진다`
- `요청 URL 에 들어간 인증키가 예외 메시지에 남지 않는다`
- `타임아웃이 나면 CollectError 로 바꿔 던진다`

**엣지 케이스**
- 금리는 매일 바뀌지 않는다(기준금리) → "직전 값"이 며칠 전일 수 있다. 등락은 %p 차이로 표시한다.
- ECOS 가 인증키를 URL 경로에 넣는 방식이면 로그에 URL 을 찍지 않는다.
- **Task 1 에서 출처를 못 찾으면 이 Task 는 만들지 않는다.** `task block 6` 으로 표시하고 Task 10 은 금리 없이 진행한다.

**완료 판정**
```bash
uv run pytest tests/collect/test_rates.py && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 7 — 언론사 RSS 뉴스 어댑터

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/collect/news_rss.py` | `RssNewsProvider.__init__(client, feeds)`, `.get_news(since)`, `_parse_feed(xml, source)`, `_strip_html(text)` | 신규 |
| `tests/collect/fixtures/rss_hankyung.xml`, `rss_mk.xml`, `rss_broken.xml` | — | 신규. 실제 피드를 3~4항목으로 줄인 것 |
| `tests/collect/test_news_rss.py` | — | 신규. `httpx.MockTransport` |

**먼저 쓸 테스트**
- `피드 XML 의 항목을 제목·요약·링크·발행 시각을 가진 NewsItem 으로 바꾼다`
- `요약에 들어 있는 HTML 태그와 엔티티를 벗겨 낸다`
- `기준 시각보다 먼저 발행된 항목은 걸러낸다`
- `같은 링크가 두 피드에 있으면 한 번만 남긴다`
- `피드 하나가 5xx 를 돌려줘도 나머지 피드의 항목을 돌려준다`
- `깨진 XML 은 해당 피드만 실패로 처리한다`
- `발행 시각이 없는 항목은 버린다`

**엣지 케이스**
- 인코딩이 UTF-8 이 아닌 피드 (EUC-KR 선언) → 응답 바이트를 그대로 파서에 넘긴다.
- 발행 시각 형식이 RFC 822 가 아닌 피드.
- 외부 XML 의 엔티티 확장 공격 → Task 1 에서 고른 안전한 파서만 쓴다.
- 요약이 비어 있거나 제목과 같은 항목 → 요약을 빈 문자열로 둔다.
- 기사 본문 페이지는 가져오지 않는다 (피드 항목만).

**완료 판정**
```bash
uv run pytest tests/collect/test_news_rss.py && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 8 — Marketaux 뉴스 어댑터

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/collect/news_marketaux.py` | `MarketauxNewsProvider.__init__(client, token, max_calls)`, `.get_news(since)`, `_parse(payload)` | 신규 |
| `tests/collect/fixtures/marketaux_page.json` | — | 신규 |
| `tests/collect/test_news_marketaux.py` | — | 신규. `httpx.MockTransport` |

**먼저 쓸 테스트**
- `응답 JSON 의 기사를 NewsItem 으로 바꾼다`
- `호출 상한까지만 페이지를 요청한다`
- `한도 초과 응답(429)을 받으면 멈추고 그때까지 모은 항목을 돌려준다`
- `첫 호출부터 인증 실패면 CollectError 를 던진다`
- `빈 페이지를 받으면 더 요청하지 않는다`
- `토큰이 예외 메시지와 로그에 남지 않는다`

**엣지 케이스**
- 토큰이 쿼리 파라미터로 나간다 → 예외에 URL 을 그대로 담지 않는다.
- 하루 2슬롯 × 슬롯당 호출 상한이 무료 한도(100회/일) 안에 들어야 한다 → 기본 상한을 그에 맞춰 잡는다.
- 같은 기사가 페이지를 넘어 중복될 수 있다 → 링크로 중복 제거.
- `published_at` 의 시간대 표기.

**완료 판정**
```bash
uv run pytest tests/collect/test_news_marketaux.py && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 9 — DART 공시 어댑터

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/collect/news_dart.py` | `DartNewsProvider.__init__(client, api_key)`, `.get_news(since)`, `_parse(payload)`, `_filing_url(rcept_no)` | 신규 |
| `tests/collect/fixtures/dart_list.json`, `dart_empty.json`, `dart_limit.json` | — | 신규 |
| `tests/collect/test_news_dart.py` | — | 신규. `httpx.MockTransport` |

**먼저 쓸 테스트**
- `공시 목록 응답을 회사명과 보고서명을 제목으로 가진 NewsItem 으로 바꾼다`
- `NewsItem 의 링크는 접수번호로 만든 공시 뷰어 주소다`
- `조회 결과 없음 코드는 빈 목록으로 처리한다`
- `한도 초과 코드(020)는 CollectError 를 던진다`
- `그 밖의 오류 코드는 코드와 메시지를 담은 CollectError 를 던진다`
- `인증키가 예외 메시지에 남지 않는다`

**엣지 케이스**
- DART 는 HTTP 200 에 본문 `status` 코드로 오류를 알린다 → HTTP 상태만 보면 안 된다.
- 하루 공시가 수백 건이다 → 공시 유형·법인 구분 필터와 최대 건수를 Task 1 결과로 정한다.
- 접수일은 날짜만 있고 시각이 없다 → 기준 시각 비교를 날짜 단위로 한다.

**완료 판정**
```bash
uv run pytest tests/collect/test_news_dart.py && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 10 — 수집 조립과 휴장 판정

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/collect/service.py` | `collect_snapshot(slot, now, providers)`, `Providers`(quotes, rates, news 목록), `_symbols_for(slot)`, `_news_since(slot, now)`, `_is_closed(quotes, market, now)` | 신규 |
| `src/finbrief_analyzer/collect/factory.py` | `build_providers(settings)` | 신규. 키가 없는 제공자는 목록에서 뺀다 |
| `tests/collect/test_service.py` | — | 신규. 가짜 제공자만 사용 |

**먼저 쓸 테스트**
- `국내 개장 슬롯은 미국 지수·환율과 전날 저녁 이후의 뉴스를 담는다`
- `미국 개장 슬롯은 국내 지수·환율과 당일 아침 이후의 뉴스를 담는다`
- `뉴스 제공자 하나가 예외를 던져도 스냅샷이 만들어지고 missing 에 그 출처가 적힌다`
- `시세 제공자가 통째로 실패해도 뉴스만 담은 스냅샷을 돌려준다`
- `지수의 기준일이 직전 거래일보다 오래됐으면 그 시장을 휴장으로 표시한다`
- `키가 없는 제공자는 build_providers 결과에 들어가지 않는다`
- `금리 제공자가 없으면 금리 없이 스냅샷을 만든다`
- `collect_snapshot 은 어떤 제공자 오류에도 예외를 던지지 않는다`

**엣지 케이스**
- 월요일 국내 개장 슬롯: 직전 미국 거래일은 금요일이다. 주말을 휴장으로 오판하지 않는다.
- 한국만 휴장·미국만 휴장인 날: 시장별로 따로 판정한다.
- 뉴스 기준 시각은 "직전 슬롯 시각"이다. 첫 실행이나 연휴 뒤에는 상한(예: 24시간)을 둔다.
- `now` 를 인자로 받아 테스트가 시계에 기대지 않게 한다.
- 뉴스 총 건수 상한을 두어 이후 작성 단계의 입력이 폭주하지 않게 한다.

**완료 판정**
```bash
uv run pytest tests/collect/test_service.py && uv run ruff check . && uv run mypy && uv run pytest
```

## 열어둔 질문
- **이 PC 에 `uv`, `make`, `gh` 가 설치돼 있지 않다.** 완료 판정 명령은 `uv` 가 있어야 돈다. 구현 전에 `uv` 설치가 필요하다.
- `.env` 에 넣은 키의 변수 이름이 Task 3 의 필드명(`APP_MARKETAUX_TOKEN`, `APP_DART_API_KEY`, `APP_ECOS_API_KEY`)과 같은지.
- 이슈는 만들지 않았다. 브랜치명은 이슈 번호 없이 `feat/data-sources-collect` 로 제안한다.
- 금리 출처 (Task 1 에서 결정).
- 브리핑에 넣을 지수 목록의 최종안 (기본: KOSPI·KOSDAQ·S&P 500·나스닥·다우·원/달러).
