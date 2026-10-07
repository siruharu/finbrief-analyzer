---
type: research
project: finbrief-analyzer
topic: data-source-poc
created: 2026-10-07
status: done
source_task: "[[2026-10-07_data-sources]]"
tags: [research, poc, data-source, market-data, news]
next: implementation
---

# 🔍 데이터 출처 PoC (data-sources Task 1)

> **핵심 질문** — 분석이 가정으로 남긴 출처들이 실제로 필요한 값을 주는가. 틀린 가정은 무엇인가.

## 실행 조건
- 일시: 2026-10-07(수) 16:30 KST. 국내 장 마감(15:30) 1시간 뒤, 미국은 10-06 장이 끝난 상태.
- 버전: FinanceDataReader 0.9.202, yfinance 1.7.0, httpx, defusedxml. Python 3.12.
- 일회성 스크립트는 저장소 밖 scratch 폴더에서 `uv run --no-project --with ...` 로 실행했고 커밋하지 않았다.
- `.env` 의 키는 스크립트가 읽어 요청에만 썼다. 값은 출력·문서에 옮기지 않았다.

## 요약
| # | 질문 | 결과 |
|---|---|---|
| 1 | FinanceDataReader 로 6개 시세 | **부분적으로 됨.** 미국 3대 지수·환율은 됨. **`KS11`·`KQ11` 은 안 됨** (2026-09-17 에서 멈춤). `^KS11`·`^KQ11` 로 바꾸면 됨 |
| 2 | 발송 시각의 데이터 가용성 | 16:30 KST 에 당일 국내 종가 **됨**. 전일 미국 종가 **됨** (09:00 KST 시점은 간접 확인) |
| 3 | yfinance 값 일치 | **됨.** 종가가 소수점까지 같다. 단, **같은 Yahoo 를 본다** → 독립 예비가 아니다 |
| 4 | 금리 | **됨. 금리는 v1 에 넣는다.** 국내는 ECOS, 미국은 `US10YT`(FDR) |
| 5 | RSS 구조·파서 | **됨.** 파서는 `defusedxml`. 한국경제는 요약이 없고, 매일경제는 발행 시각 형식이 비표준 |
| 6 | Marketaux·DART | **됨.** Marketaux 는 요청당 3건 고정, DART 는 `status` 코드로 오류를 준다 |

## 1. FinanceDataReader 시세와 심볼

### 확정 심볼 표
| 항목 | 심볼 (FDR) | 예비 (yfinance) | 10-06 종가 | 10-07 종가 | 비고 |
|---|---|---|---|---|---|
| KOSPI | `^KS11` | `^KS11` | 6941.39 | 6803.90 | `KS11` 은 쓰지 않는다 |
| KOSDAQ | `^KQ11` | `^KQ11` | 919.92 | 898.43 | `KQ11` 은 쓰지 않는다 |
| S&P 500 | `US500` | `^GSPC` | 7818.93 | — | `S&P500` 도 같은 값 |
| 나스닥 | `IXIC` | `^IXIC` | 27599.79 | — | |
| 다우 | `DJI` | `^DJI` | 51521.28 | — | |
| 원/달러 | `USD/KRW` | `KRW=X` | NaN | 1337.x (장중) | 아래 주의 참고 |
| 미 국채 10년 | `US10YT` | `^TNX` | 5.269 | — | 금리 절 참고 |

### `KS11`·`KQ11` 이 안 되는 이유
- `fdr.DataReader("KS11", "2026-09-25")` → **0행.** 예외는 없다. 컬럼만 있는 빈 표가 돌아온다.
- 시작일을 `2026-01-01` 로 넓히면 175행이 나오지만 **마지막 행이 2026-09-17** 이다. 전체 조회(4114행)도 같다. 응답이 0.1초로, 실시간 조회가 아니라 어딘가에 쌓아 둔 표를 읽는 동작으로 보인다(추정).
- `KOSPI`, `KS200` 도 같은 증상. `KRX:KS11` 은 `ValueError: "KS11" is not supported`, `KRX-INDEX:1001` 은 `ValueError: LOGOUT`, `NAVER:KS11` 은 0행·컬럼 없음.
- `^KS11`, `^KQ11`, `YAHOO:^KS11` 은 7행, 마지막 행이 10-07 이다.
- **빈 표는 예외가 아니다.** Task 4 의 "빈 표면 데이터 없음" 처리가 실제로 필요한 경로다. 그리고 "행은 있는데 오래됐다"도 따로 걸러야 한다 — 3주 묵은 종가가 조용히 브리핑에 실릴 수 있었다.

### 반환 형식
- 컬럼: `Open, High, Low, Close, Volume, Adj Close`. 전부 `float64` (Volume 만 `int64`).
- 인덱스: `DatetimeIndex`, **시간대 없음**. 날짜는 그 시장의 현지 거래일이다.
- 값은 `7722.720215` 처럼 이진 부동소수 꼬리가 붙어 온다. 원천은 소수 둘째 자리다(ECOS·네이버 값과 둘째 자리까지 일치).
  → Task 2 판단 재료: `float` 로 보관하고 표시할 때 둘째 자리로 반올림하면 충분하다. `Decimal` 이 필요한 계산(합산·정산)은 없다.
- 등락률: Yahoo 계열 표에는 `Change` 컬럼이 **없다.** 종가 두 개로 직접 계산해야 한다.

### 환율(`USD/KRW`) 주의
- **주말 행이 있다** (10-04 일요일). 거래일 달력으로 쓰면 안 된다.
- **종가가 NaN 인 행이 있다** (10-06). `dropna` 없이 "마지막 두 행"을 쓰면 등락률이 NaN 이 된다.
- 오늘(10-07) 행은 장중 값이다. 두 번 조회에 1337.18 → 1337.00 으로 바뀌었다. 환율은 "종가"가 아니라 "조회 시점 값"이다.
- FDR 과 yfinance 의 **날짜가 하루 어긋난다.** 같은 1343.75 가 FDR 은 10-05, yfinance 는 10-06(Europe/London) 에 붙는다.
- ECOS 의 매매기준율(1343.4, 10-07)은 Yahoo 값(1337)과 다른 숫자다. 정의가 다르다(고시 기준율 vs 시장 호가).

## 2. 발송 시각의 가용성
- **미국 개장 슬롯(국내 종가가 필요):** 16:30 KST 에 `^KS11`·`^KQ11` 의 10-07 행이 있고 네이버 값(6803.9)과 일치한다 → **됨.**
- **국내 개장 슬롯(전일 미국 종가가 필요):** 16:30 KST 에 10-06 행이 있다. 미국 장은 05:00 KST(서머타임) 또는 06:00 KST 에 끝나므로 09:00 KST 에도 있을 것으로 본다 → **됨 (간접 확인).** 09:00 KST 에 직접 돌려 보지는 않았다.
- **확인 못 함:** 장중에 조회하면 Yahoo 는 당일 행에 현재가를 `Close` 로 넣는다(환율에서 관찰). 지수도 같다면 장 마감 전에 도는 작업은 미완성 종가를 싣는다. 슬롯 시각이 마감 뒤라 지금은 해당 없음.

## 3. yfinance 예비
- `^GSPC`·`^IXIC`·`^DJI` 의 10-02·10-05·10-06 종가가 FDR 값과 **소수 여섯째 자리까지 같다** → **됨.**
- 인덱스에 시간대가 **있다** (`America/New_York`, `Asia/Seoul`, `^TNX` 는 `America/Chicago`). FDR 은 없다. 어댑터에서 날짜만 떼어 내야 두 출처의 날짜가 맞는다.
- 컬럼에 `Dividends`, `Stock Splits` 가 더 있다.
- **값이 완전히 같다는 것은 같은 원천이라는 뜻이다.** FDR 의 미국 지수·환율·`^KS11` 은 Yahoo 를 읽는다. Yahoo 가 막히면 1차와 예비가 함께 죽는다. **플랜의 "1차 실패 시 예비" 가정은 코드 결함(FDR 라이브러리 고장)에는 듣지만 원천 장애에는 듣지 않는다.**

### Yahoo 가 아닌 원천 (독립 예비 후보)
| 출처 | 대상 | 당일 값 | 성격 |
|---|---|---|---|
| ECOS `802Y001` | KOSPI(`0001000`), KOSDAQ(`0089000`) | **없음** — 16:30 KST 에 10-06 까지만 | 공식 API, 키 필요. 하루 늦다 |
| 네이버 `fchart.stock.naver.com/siseJson.nhn` | KOSPI 등 | 있음 (10-07 6803.9) | 비공식. 응답이 JSON 이 아니라 작은따옴표 배열 텍스트 |
| FRED (`FRED:DGS10`) | 미 국채 금리 | 없음 — 10-05 까지만 | 공식. 하루 이상 늦다 |

미국 지수의 Yahoo 외 원천은 이번에 찾지 않았다.

## 4. 금리
### 국내 — ECOS (됨)
- 호출: `https://ecos.bok.or.kr/api/StatisticSearch/{키}/json/kr/{시작행}/{끝행}/{통계코드}/D/{YYYYMMDD}/{YYYYMMDD}/{항목코드}`
- **키가 URL 경로에 들어간다.** 쿼리 파라미터가 아니다. httpx 예외·로그에 URL 을 그대로 찍으면 키가 샌다.

| 항목 | 통계코드 | 항목코드 | 10-06 | 10-07 | 단위 |
|---|---|---|---|---|---|
| 기준금리 | `722Y001` | `0101000` | 3 | (미확인) | 연% |
| 국고채 3년 | `817Y002` | `010200000` | 3.933 | 3.961 | 연% |
| 국고채 10년 | `817Y002` | `010210000` | 4.369 | 4.376 | 연% |

- 국고채 금리는 **16:30 KST 에 당일 값이 있다.** (지수 `802Y001` 은 당일 값이 없다.)
- 응답: `{"StatisticSearch": {"list_total_count": N, "row": [...]}}`. 행의 `TIME`(YYYYMMDD 문자열), `DATA_VALUE`(**문자열**), `ITEM_NAME1`, `UNIT_NAME` 을 쓴다.
- 기준금리는 **매일 한 행씩** 나온다(주말 포함 여부는 미확인). "직전 값과 비교"는 변동이 없는 날이 대부분이라 등락 0 이 정상이다.
- 오류는 **HTTP 200** 으로 온다. `{"RESULT": {"CODE": ..., "MESSAGE": ...}}`
  - 잘못된 키: `INFO-100`
  - 데이터 없음(주말만 조회): `INFO-200`
- **확인 못 함:** 호출 한도와 이용 조건. 응답 헤더에 한도 정보가 없고, 연속 8회 호출에 제한은 없었다. 하루 2회 × 3항목이라 한도에 닿을 사용량은 아니지만 약관은 Task 6 전에 읽어야 한다.

### 미국 — `US10YT` (됨)
- `fdr.DataReader("US10YT")` = Yahoo `^TNX`. 10-06 종가 5.269. 지수와 같은 표 모양이라 **시세 어댑터를 그대로 쓸 수 있다.**
- `FRED:DGS10`(5.31, 10-05 까지)·`FRED:DGS2` 도 나오지만 하루 늦고 컬럼명이 심볼명(`DGS10`)이다.

**결정: 금리를 v1 에 넣는다.** Task 6 은 막지 않는다. 미 국채 10년은 시세 심볼 목록에 넣고, Task 6(ECOS)은 국내 금리만 맡는 것이 구현이 가장 작다 — 플랜 반영은 사용자 확인 뒤.

## 5. 언론사 RSS
| 피드 | URL | 항목 수 | 요약(`description`) | `pubDate` |
|---|---|---|---|---|
| 한국경제 경제 | `https://www.hankyung.com/feed/economy` | 50 | **없음** (태그 자체가 없다) | `Wed, 07 Oct 2026 15:58:43 +0900` |
| 한국경제 금융 | `https://www.hankyung.com/feed/finance` | 50 | **없음** | 위와 같음 |
| 매일경제 경제 | `https://www.mk.co.kr/rss/30100041/` | 50 | 최대 102자, `..` 로 끝남 | `Wed, 07 Oct 2026 16:27:31 +09:00` |
| 매일경제 증권 | `https://www.mk.co.kr/rss/50200011/` | 50 | 102자 | 위와 같음 |
| 연합뉴스 경제 | `https://www.yna.co.kr/rss/economy.xml` | 120 | 중간값 83자, 최대 103자 | `Wed, 7 Oct 2026 16:23:52 +0900` |
| 연합뉴스 마켓+ | `https://www.yna.co.kr/rss/market.xml` | 120 | 중간값 83자, 최대 113자 | 위와 같음 |

- 전부 RSS 2.0, UTF-8, HTTP 200. 일반 User-Agent(`finbrief-analyzer/0.1`)로 차단 없이 받았다. 항목 경로는 `./channel/item`.
- 제목·요약은 CDATA 로 싸여 있다. 요약에 HTML 태그는 한 건도 없었다(그래도 외부 입력이라 태그 제거는 유지한다).
- DOCTYPE 선언은 없다.
- **매일경제의 `+09:00` 은 RFC 822 형식이 아니다.** `email.utils.parsedate_to_datetime` 이 예외 없이 **시간대가 빠진 naive datetime 을 돌려준다.** Task 2 는 naive 값을 거부하므로 그대로 두면 매일경제 기사가 전부 버려진다. 파싱 전에 `+09:00` → `+0900` 으로 고치거나, naive 결과에 KST 를 붙인다.
- 연합뉴스 요약은 `(세종=연합뉴스) 이대희 기자 = ` 같은 머리말로 시작한다. 요약이 1자뿐인 항목도 있다.
- 피드가 담는 시간 폭: 경제 피드는 약 6~24시간. 연합뉴스 경제는 120건이 6시간 분량이라 **밤사이 뉴스를 아침에 모으면 앞부분이 잘릴 수 있다.**
- 한국경제는 제목·링크·시각·기자만 준다. 요약이 필요하면 다른 피드에 기대야 한다.

**파서 결정: `defusedxml.ElementTree`.** 외부 XML 이므로 표준 `xml.etree` 를 직접 쓰지 않는다. 6개 피드 모두 `defusedxml` 로 문제없이 읽혔다. 네임스페이스 태그(`media:content`, `dc:creator`)는 쓰지 않아도 된다. `feedparser` 는 필요 없다 — 쓰는 필드가 4개뿐이다. Task 3 의 의존성에 `defusedxml` 을 더해야 한다(플랜에 빠져 있다).

## 6. Marketaux · DART
### Marketaux (됨)
- `GET https://api.marketaux.com/v1/news/all?api_token=...&language=en&limit=3`
- **`limit=10` 을 보내도 3건만 온다** (`meta.limit: 3`, `returned: 3`). 무료 한도가 문서대로다. `page=2` 로 다음 3건을 받는다.
- 응답 헤더로 남은 횟수를 알 수 있다: `x-usagelimit-limit: 100`, `x-usagelimit-remaining: N` (하루), `x-ratelimit-limit: 30` (분당으로 보임).
- **타임아웃 난 요청도 한도에서 빠진다.** 첫 호출이 15초에 `ReadTimeout` 이 났는데 다음 응답의 잔여가 98 이었다. 느릴 때가 있으니 타임아웃은 넉넉히(30초 이상) 잡고, 재시도는 한도를 태운다는 점을 감안한다.
- 항목 필드: `uuid, title, description, keywords, snippet, url, image_url, language, published_at, source, relevance_score, entities, similar`.
  - `published_at`: `2026-10-07T06:33:06.000000Z` (UTC).
  - `description`: 67~345자. **요약으로는 이것을 쓴다.**
  - `snippet`: 믿을 수 없다. `"To ensure this doesn't happen in the future, please enable Javascript..."` 같은 차단 문구가 그대로 들어온다.
- `language=ko` 는 **동작한다** (29,490건). 다만 출처가 스타트업 매체 위주라 국내 시황 뉴스로는 쓸 수 없다. 국내는 RSS 로 간다는 분석 결정이 맞다.
- `countries=us` 는 **발행 매체의 국가가 아니다.** 기사에 엮인 종목(entity)의 국가다. `countries` 없이 `language=en` 만 주면 인도 매체(livemint, economictimes) 기사가 상단을 채운다. `countries=us` 를 주면 seekingalpha·cnbc 가 나온다 → **`countries=us` 를 기본으로 쓴다.**
- 상위 결과에 개별 종목 슬라이드·분석 글이 많다. 시황 뉴스만 골라내려면 `published_after` 외에 필터(`domains`, `filter_entities`, `must_have_entities`)가 더 필요할 수 있다 — 이번엔 확인하지 않았다.
- 잘못된 토큰: **HTTP 401**, `{"error": {"code": "invalid_api_token", "message": ...}}`.
- 이번 PoC 로 오늘 한도 5회를 썼다(잔여 95).

### DART (됨)
- `GET https://opendart.fss.or.kr/api/list.json?crtfc_key=...&bgn_de=YYYYMMDD&end_de=YYYYMMDD&page_count=N`
- 응답 최상위: `status, message, page_no, page_count, total_count, total_page, list`.
- 항목 필드: `corp_code, corp_name, stock_code, corp_cls, report_nm, rcept_no, flr_nm, rcept_dt, rm`. **요약도 링크도 없다.**
  - 링크는 `https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}` 로 만든다 (형식은 이번에 열어 보지 않았다 — Task 9 에서 확인).
  - 발행 **시각이 없다.** `rcept_dt` 는 날짜뿐이다. 시간대 있는 `datetime` 이 필수인 `NewsItem` 에 넣으려면 그날 00:00 KST 로 두는 규칙이 필요하다.
- **필터 없이 조회하면 하루 449건이고 대부분 펀드 투자설명서다.** `pblntf_ty=B`(주요사항보고) + `corp_cls=Y`(유가증권) 로 좁히면 3건(자기주식처분, 유상증자 등)이 된다 → 이 필터를 기본으로 쓴다.
- 오류는 **HTTP 200** + `status` 코드다.
  - `000` 정상 / `010` 등록되지 않은 키 / `013` 조회된 데이터 없음(주말). `020`(한도 초과)은 재현하지 않았다.

## 엣지 케이스 확인 결과
| 경우 | 관찰 |
|---|---|
| 주말만 조회 (FDR `KS11`) | 0행, 예외 없음 |
| 주말만 조회 (FDR `IXIC`, 10-03~10-04) | **범위 밖인 10-02 행 1개가 돌아온다.** 마지막 거래일 값이다 |
| 국내 휴장일 (10-05 대체공휴일) | 그 날짜의 행이 없다. 마지막 행은 그대로 직전 거래일이다 → 휴장 판정은 "마지막 행의 날짜가 기대한 거래일인가"로 한다 |
| 주말만 조회 (ECOS) | `INFO-200` |
| 주말만 조회 (DART) | `status 013` |
| 잘못된 키 | ECOS `INFO-100`(200) / Marketaux `invalid_api_token`(401) / DART `010`(200) |
| 연속 호출 차단 | FDR 8회 연속 1.1초, 차단 없음. 그 이상은 시험하지 않았다 |

## 이후 Task 에 미치는 영향
- **Task 2**: 값은 `float`. 등락률은 직접 계산. 발행 시각이 날짜뿐인 출처(DART)가 있다.
- **Task 3**: 기본 심볼은 위 확정 표. 의존성에 `defusedxml` 추가. 사용자의 `.env` 키 이름은 `OPENDART_KEY`, `MARKET_AUX_KEY`, `ECOS_KEY` 로, 설계의 `APP_DART_API_KEY`·`APP_MARKETAUX_TOKEN`·`APP_ECOS_API_KEY` 와 **다르다** — 어느 쪽에 맞출지 Task 3 에서 정한다.
- **Task 4**: NaN 종가 행을 버린 뒤 마지막 두 행을 쓴다. 0행과 "오래된 마지막 행"을 구분해 처리한다.
- **Task 5**: yfinance 는 날짜에서 시간대를 떼어 낸다. 예비가 같은 원천이라는 점은 아래 열린 질문.
- **Task 6**: 막지 않는다. 키가 URL 경로에 있어 예외 메시지에서 URL 을 지워야 한다. 오류가 200 으로 온다.
- **Task 7**: 매일경제 시각 형식 보정. 한국경제는 요약 없음을 정상으로 받는다.
- **Task 8**: `description` 을 요약으로, `countries=us` 기본, 타임아웃 30초 이상, 재시도 없음.
- **Task 9**: `pblntf_ty=B`·`corp_cls=Y` 기본. 링크는 `rcept_no` 로 조립.

## 확인 못 한 것
- [ ] 09:00 KST 에 전일 미국 종가가 실제로 있는지 (직접 실행)
- [ ] 장중 조회 시 지수의 당일 행이 어떻게 나오는지
- [ ] ECOS 호출 한도·이용 조건
- [ ] DART 공시 뷰어 링크 형식, `020` 응답 모양
- [ ] Marketaux 에서 시황 뉴스만 고르는 필터
- [ ] `KS11` 이 멈춘 원인 (일시 장애인지 영구적인지)

## 열린 질문 → 사용자 결정 (2026-10-07)
- [x] **예비 출처.** 국내 지수의 예비는 **네이버**로 바꾼다. 1차는 Yahoo(FDR `^KS11`·`^KQ11`) 그대로다. 미국 지수의 예비는 Yahoo 외 원천을 찾지 못해 yfinance 로 둔다(라이브러리 고장만 막는다).
- [x] **미 국채 10년.** 시세 심볼 목록에 `US10YT` 로 넣는다. Task 6(ECOS)은 국내 금리만 맡는다.
- [x] **환율.** **ECOS 매매기준율**(`731Y001` / `0000001`)을 싣는다. Yahoo 의 `USD/KRW` 는 쓰지 않는다 → 환율은 시세 어댑터가 아니라 Task 6 의 ECOS 어댑터에서 나온다.
