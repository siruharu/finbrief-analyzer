---
type: research
project: finbrief-analyzer
topic: 개별 종목 스크리닝 (국내·미국)
created: 2026-10-08
status: draft        # draft | done
tags: [research, screening, quant, market-data, fundamentals, backtest, regulation]
next: analysis
---

# 🔍 개별 종목 스크리닝 (국내·미국)

> **핵심 질문** — 개인 PC 에서 무료 데이터만으로 국내·미국 개별 종목을 매일 스크리닝(관심 종목 시세, 단기 가격·거래량 규칙, 장기 재무 팩터)하려면 어떤 데이터 출처와 방법이 있고, 각각의 한도·제약은 무엇인가?

## 배경
사용자가 첫 브리핑 메일을 받은 뒤(2026-10-08) 지수·금리 외에 개별 종목 정보를 원했다: 국내·미국 단일 종목, "장기적으로 추천할 만한 종목", "단타 칠 만한 것", 퀀트 분석.
조건: 개인 PC 에서 실행(AWS 미사용, 2026-10-08 결정), 무료 데이터, 수신자는 본인과 지인 10명 이하, 무료 발송.

표기: ✅ = 메인 세션에서 직접 확인(실행 또는 원문). 표기 없음 = 서브에이전트 요약 기준(원문을 요약 모델을 거쳐 읽음). 논문 DOI 는 대부분 재확인하지 않았다.

## 코드베이스 안에 이미 있는 것
| 위치 | 하는 일 | 재사용 가능? |
|---|---|---|
| `collect/quotes_base.py:14, 16, 54-63` | 조회 창 10일, 표에서 `Close` 열만 읽는다. 거래량·시고저는 버린다 | 그대로는 거래량·1년 이력 규칙에 못 쓴다 |
| `collect/quotes_base.py:25-37, 88-97` | 심볼마다 요청 1회, 순차 실행. 병렬·배치 없음 | 수백 종목이면 방식이 달라진다 |
| `collect/models.py:34-44` | `Quote` 는 symbol, close, as_of, prev_close, name, market. 거래량·시계열 없음 | 관심 종목 시세에는 그대로 맞는다 |
| `collect/models.py:16-23` | `Market` 에 개별 종목용 값 없음 | 묶음 추가 필요 |
| `core/config.py:12-19, 24-45` | `QuoteSymbol` 목록, `APP_QUOTE_SYMBOLS` 로 덮어쓴다. 기본값에 개별 종목 없음 | 관심 종목 설정 경로 |
| `collect/quotes_yf.py:15-34` | yfinance 는 매핑에 있는 18개 심볼만 지원 | 개별 종목은 매핑에 없다 |
| `collect/news_dart.py:20, 49-57` | DART 는 공시 목록(`list.json`) 하나만 부른다 | 키는 같은 것을 재무 API 에 쓸 수 있다 |
| `collect/news_dart.py:86-102` | 응답의 `stock_code`·`corp_code` 를 쓰지 않는다 | — |
| `collect/factory.py:20`, `news_marketaux.py:57` | 수집 쪽 재시도·캐시·호출 간격 제어 없음. httpx 타임아웃 30초만 있다 | 대량 조회 시 새로 필요 |
| `store/tables.py:27-50` | 테이블은 `recipients`, `delivery_log` 둘뿐. 가격 이력·관심 종목 저장소 없음 | 이력을 쌓으려면 새 테이블 |
| `compose/simple.py:12-27, 39-53` | 시장별로 `Section` 1개. market 이 없는 시세는 "기타" | 섹션 추가는 같은 방식으로 가능 |
| `deliver/models.py:51-63` | `Section` 은 title, lines(문자열), links, required. 표 구조 없음 | 순위표는 글줄로만 표현된다 |
| `docs/01_research/2026-10-07_data-source-poc.md:72, 166` | FDR 과 yfinance 는 같은 Yahoo 를 읽는다. FDR 연속 8회 호출 1.1초까지만 시험 | 대량 조회는 미시험 |
| `docs/01_research/2026-10-08_quote-symbols-poc.md:47` | 장중 조회 시 당일 행이 진행 중인 값으로 온다 | 개별 종목에도 같은 성질 |

이력: 시세 관련 커밋(ed8eb80, a55a32c, d66a444, b9599a0, daf67ef) 중 되돌린 것은 없다. 개별 종목·재무·대량 조회를 시도한 기록도 없다.

## 외부 조사

### 1. 종목 목록
- **FinanceDataReader 0.9.202** (2026-05-13 릴리스, MIT)
  - ✅ `StockListing('KRX')` 한 번(0.3초)에 2,872종목: Code, Name, Market, Close, Open, High, Low, Volume, Amount, Marcap, Stocks 등. `'KOSPI'` 942종목, `'KOSDAQ'` 1,823종목. (2026-10-08 실행)
  - ✅ `StockListing('S&P500')` 503종목(Symbol, Name, Sector, Industry). `'NASDAQ'` 3,996종목(7.8초). 미국 목록에는 가격이 없다.
  - S&P 500 목록은 Wikipedia, NASDAQ·NYSE·AMEX 목록은 Naver 에서 읽는다. Nasdaq 100 전용 인자는 없다.
  - KRX 목록의 출처는 data.krx.co.kr. 코드에 로그인 처리·폴백 없음.
  - 열린 장애 이슈: #288(2026-09-29) `StockListing("KOSPI")` 빈 결과·`"KRX-DESC"` 404, #282(2026-08-07) "약 2주마다" KRX 목록 404·몇 시간~최대 2일 지속, #267(2026-02-28) KRX 응답 "LOGOUT".
  - `'KRX-DELISTING'` 으로 상장폐지 목록을 제공한다.
  - 출처: https://pypi.org/project/finance-datareader/ , https://github.com/FinanceData/FinanceDataReader , https://github.com/FinanceData/FinanceDataReader/issues/288 , https://github.com/FinanceData/FinanceDataReader/issues/282
- **pykrx 1.2.9** (2026-09-19, Python >=3.10, MIT) — 이 저장소에 설치돼 있지 않다
  - 날짜 하나로 전 종목: `get_market_ohlcv(date, market=)`, `get_market_cap(date)`, `get_market_fundamental(date)`(BPS·PER·PBR·EPS·DIV·DPS). KOSPI 200 구성종목 `get_index_portfolio_deposit_file("1028")`.
  - "KRX 로그인이 필요한 API"는 환경변수 `KRX_ID`·`KRX_PW` 가 필수라고 적혀 있다. 어느 함수가 대상인지는 README 에 없다.
  - README: "무분별한 API 호출을 자제", 반복 예제에 `time.sleep(1)`. KRX·Naver 를 스크래핑하며 참고용이라는 면책 문구.
  - 출처: https://pypi.org/project/pykrx/ , https://github.com/sharebook-kr/pykrx
- **KRX Open API (공식)**: 유가증권·코스닥 일별매매정보(2010-01-04 이후), 인증키 신청 메뉴가 있다. 요금·일일 한도는 공식 페이지에서 확인 못 함(2차 출처에 일 10,000회). https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd
- **공공데이터포털 금융위원회_주식시세정보**: 무료, 개발계정 일 10,000건, "기준일자로부터 영업일 하루 뒤 오후 1시 이후에 업데이트". https://www.data.go.kr/data/15094808/openapi.do

### 2. 일별 주가·거래량
- **FinanceDataReader `DataReader`**
  - ✅ `'005930'`, `'247540'`(코스닥) 1년치 246행 0.3초, 열은 Open·High·Low·Close·Volume·Change. `'AAPL'` 257행 0.4초, 열은 Open·High·Low·Close·Volume·Adj Close. (2026-10-08 실행)
  - 국내 종목코드의 기본 출처는 Naver(2000년 이후). 접두어 `NAVER:`·`KRX:`·`YAHOO:` 지원. 종목당 호출 한도는 문서에 없다.
- **yfinance 1.7.0** (2026-08-26)
  - ✅ `yf.download([8종목], period="1y", group_by="ticker")` 0.9초에 국내(`.KS`, `.KQ`)·미국 8종목 모두 값이 왔다. (2026-10-08 실행)
  - `download(..., threads=True, auto_adjust=True, timeout=10)` 가 기본값. 이 저장소의 어댑터는 `auto_adjust=False` 로 `Ticker.history` 를 쓴다.
  - 문서: "the Yahoo! finance API is intended for personal use only", "research and educational purposes", Yahoo 와 무관한 비공식 도구.
  - 공식 한도 수치는 없다. 보고: #2422(2025-04-30) 단일 호출에서도 "Too Many Requests", #2128 약 950종목 뒤 429, Discussion #2431 "약 100요청 뒤 30초 대기" 와 협력자 답변 "fetch smarter with … yfinance-cache".
  - 출처: https://pypi.org/project/yfinance/ , https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html , https://github.com/ranaroussi/yfinance/issues/2422 , https://github.com/ranaroussi/yfinance/discussions/2431
- **그 외 무료 티어**
  - Alpha Vantage: "25 API requests per day". https://www.alphavantage.co/support/
  - Tiingo: 월 고유 심볼 500, 시간당 50요청, 일 1,000요청. 한국 커버리지 확인 못 함. https://www.tiingo.com/about/pricing
  - Polygon(현 Massive) Stocks Basic: "5 API Calls / Minute", 2년 이력, 종가 데이터, 미국만. https://massive.com/pricing
  - Stooq: 일일 한도가 있다는 2차 출처만 확인. 수치 확인 못 함.
- **분 단위·실시간 (국내)**
  - 한국투자증권 Open API: 계좌 개설 후 앱키 발급. 당일 분봉·일별 분봉·기간별 시세·실시간 체결가(WebSocket). 한도 "실전 초당 20회"는 2차 출처. 요금은 저장소에 기재 없음.
  - KIS 외의 무료 국내 분봉 출처는 확인 못 함.
  - 출처: https://github.com/koreainvestment/open-trading-api , https://apiportal.koreainvestment.com/apiservice-category

### 3. 재무 데이터 — 국내
- **OpenDART 정기보고서 재무정보** (이 프로젝트가 가진 키로 호출)
  - ✅ 다중회사 주요계정 `fnlttMultiAcnt`: `corp_code` 를 쉼표로 여러 개, 021 "조회 가능한 회사 개수가 초과하였습니다.(최대 100건)". 인자 `bsns_year`(2015 이후), `reprt_code`(11013 1분기, 11012 반기, 11014 3분기, 11011 사업보고서). 응답에 `stock_code`, `account_nm`, `fs_div`(연결/개별), `sj_div`, 당기·전기·전전기 금액, `currency`. (공식 가이드 직접 확인)
  - ✅ 020: "일반적으로는 20,000건 이상의 요청에 대하여 이 에러 메시지가 발생되나, 요청 제한이 다르게 설정된 경우에는 이에 준하여 발생됩니다." 문구에 기간 단위("일")가 없다.
  - 단일회사 전체 재무제표 `fnlttSinglAcntAll`: `fs_div` 필수, `sj_div` = BS/IS/CIS/CF/SCE.
  - 재무지표 `fnlttSinglIndx`(단일)·`fnlttCmpnyIndx`(다중, 최대 100개사): 수익성 M210000, 안정성 M220000, 성장성 M230000, 활동성 M240000. "2023년 3분기 이후 부터 정보제공". PER·PBR 같은 가격 기반 지표가 들어 있는지는 확인 못 함.
  - `corpCode.xml`: Zip 안에 corp_code(8자리), corp_name, stock_code(상장사 6자리), modify_date.
  - XBRL 원본은 접수번호 단위. 전 종목 일괄 다운로드 API 는 가이드에서 확인 못 함.
  - 분당 한도는 공식 문서에서 확인 못 함 (2차 출처에 "분당 100회").
  - 출처: https://opendart.fss.or.kr/guide/main.do?apiGrpCd=DS003 , https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019017 , https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019018
- **제출 기한**: 사업보고서 사업연도 경과 후 90일, 분기·반기보고서 45일(자본시장법 제159조·제160조). 2차 사이트 기준이며 law.go.kr 원문은 확인 못 함.
- **가격 기반 지표(PER·PBR)**
  - pykrx `get_market_fundamental(date)` 가 전 종목 값을 준다고 README 에 있다. 로그인 대상인지, 지금 동작하는지는 확인 못 함.
  - ✅ yfinance `Ticker('005930.KS').info` 는 `trailingPE`·`priceToBook` 이 `None` 이고 `returnOnEquity`·`marketCap` 만 왔다. (2026-10-08 실행)
- **래퍼**: OpenDartReader 0.3.3(2026-08-10, Python >=3.13 표기), dart-fss 0.4.17(2026-07-10).

### 4. 재무 데이터 — 미국
- **SEC EDGAR (data.sec.gov)** — API 키 불필요
  - `companyfacts`(CIK 당 전체 항목), `frames`(한 항목·한 기간을 전 보고주체에 대해 한 번에, 기간 표기 `CY2025Q4I` 등), `submissions`.
  - "no more than 10 requests per second", 초과 시 IP 차단 가능. 연락처를 담은 User-Agent 선언 요구.
  - 벌크 `companyfacts.zip`·`submissions.zip` 은 매일 밤 재생성(약 03:00 ET). 크기는 2차 출처에 약 2GB·5GB.
  - 티커 → CIK 매핑 `company_tickers.json`.
  - 출처: https://www.sec.gov/search-filings/edgar-application-programming-interfaces , https://www.sec.gov/about/developer-resources , https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- **yfinance**
  - ✅ `Ticker('AAPL').info` 0.7초: `trailingPE` 38.6, `priceToBook` 45.7, `returnOnEquity` 1.4875, `marketCap`, `dividendYield` 0.32. (2026-10-08 실행. `dividendYield` 의 단위가 % 인지 비율인지는 확인 못 함)
  - 종목당 1회 호출이다. #2480 단일 티커 `.info` 에서도 "Too Many Requests" 보고. 필드별 신뢰도는 확인 못 함.
- **그 외**: SimFin 무료 — API 초당 2회, 재무 5년, 미국 5,000종목, 비율 벌크는 유료. Tiingo 재무는 무료 미포함. Alpha Vantage 일 25회. FMP 일 250회(검색 요약만), Finnhub 확인 못 함.

### 5. 스크리닝 규칙과 근거
| 규칙 | 계산 | 근거로 인용되는 연구 | 반대·제한 증거 |
|---|---|---|---|
| 가치 | B/M, 이익수익률(E/P) | Fama·French 1992, Basu 1977 | — |
| 모멘텀 12-1 | t-12 ~ t-2월 누적수익률(직전 1개월 제외) | Jegadeesh·Titman 1993 | 직전 1개월은 반전: Jegadeesh 1990, Lehmann 1990(주간) |
| 수익성 | 매출총이익/총자산, RMW | Novy-Marx 2013, Fama·French 2015 | — |
| 저변동성 | 고유변동성 | Ang 외 2006 | — |
| 규모 | 시가총액 | Banz 1981 | — |
| 52주 고가 근접 | 현재가 / 52주 최고가 | George·Hwang 2004 | — |
| 이동평균 교차 | 단기 MA vs 장기 MA | Brock·Lakonishok·LeBaron 1992 (DJIA 1897–1986) | Sullivan·Timmermann·White 1999 표본외 우위 미확인, Bajgrowicz·Scaillet 2012 거래비용 반영 시 소멸 |
| RSI(14) | 100 − 100/(1+RS), RS = 14일 평균상승폭/평균하락폭 | Chong·Ng 2008 (FT30) | 위 데이터 스누핑 연구와 같은 한계 |
| 거래량 급증 | 당일 거래량 / N일 평균 | Gervais·Kaniel·Mingelgrin 2001 (약 1개월 프리미엄) | — |
| 갭 상승 | 시가 / 전일 종가 | 학술 근거 확인 못 함 | — |

- 한국 시장: JDQS 2021(표본 1999.1–2021.2)이 한국의 모멘텀 이익이 직전 2개월 반전의 이월에서 비롯된다고 보고. Chui·Titman·Wei 2010 은 국가별로 모멘텀 이익이 다르다고 보고.
- 출처: https://doi.org/10.1111/j.1540-6261.1993.tb04702.x , https://doi.org/10.1111/j.1540-6261.2004.00695.x , https://doi.org/10.1111/0022-1082.00163 , https://doi.org/10.1016/j.jfineco.2012.06.001 , https://doi.org/10.1108/JDQS-02-2021-0005 , https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor.html (나머지 DOI 는 서브에이전트 보고 기준)

### 6. 백테스트
| 라이브러리 | 버전 (릴리스) | 라이선스 | pandas 3 |
|---|---|---|---|
| vectorbt | 1.1.1 (2026-09-26) | Apache 2.0 + Commons Clause | pandas>=3.0.3,<4 명시 |
| backtrader | 1.9.78.123 (2023-04-19, 마지막 커밋도 같은 날) | GPLv3+ | 명시 없음 |
| bt | 1.3.0 (릴리스일 출처 간 불일치) | MIT | 명시 없음 |
| zipline-reloaded | 3.1.1 | Apache-2.0 | **pandas<3.0** |
| backtesting.py | 0.6.6 (2026-07-22) | AGPL-3.0 | 명시 없음 |
| quantstats | 0.0.86 (2026-09-27) | Apache-2.0 | pandas>=2.0 |
| alphalens-reloaded | 0.4.6 (2025-06-02) | Apache-2.0 | **pandas<3.0** |

이 저장소는 pandas 3.0.6, numpy 2.5.3 이다 (✅ `uv pip list`).

알려진 함정:
- **미래 참조**: Fama·French 1992 는 회계자료를 최소 6개월 늦춰 맞췄다. 국내 분기보고서는 45일, 사업보고서는 90일 뒤에 나온다.
- **생존 편향**: Brown 외 1992. FDR 은 `KRX-DELISTING` 을 제공, pykrx 는 상폐 종목이 종가 0·-100% 로 나온다고 기술. yfinance 의 상폐 종목 보존 여부는 확인 못 함.
- **거래 비용**: 2026-01-01 부터 증권거래세 코스피 0.05% + 농특세 0.15% = 0.20%, 코스닥 0.20% (보도 기준, 법령 원문 확인 못 함). 통상 수수료율 확인 못 함.
- **다중 검정**: Harvey·Liu·Zhu 2016 은 새 요인에 t>3.0 기준을 제안.
- **수정주가**: yfinance `download` 는 `auto_adjust=True` 가 기본, pykrx 도 수정주가가 기본.

### 7. 규제 (국내)
- 자본시장법 제101조①(2024-08-14 시행): "투자자문업자 외의 자로서 고객으로부터 일정한 대가를 받고 간행물·출판물·통신물 또는 방송 등을 통하여 … 개별성 없는 조언을 하는 것을 업"으로 하려는 자는 금융위에 신고. (law.go.kr 본문은 읽지 못해 미러로 확인)
- 금융위 2024-08-13 보도자료: 유사투자자문업은 단방향 채널로 불특정 다수에게 개별성 없는 조언만 가능. 양방향 채널의 유료 회원제 영업은 투자자문업 등록 대상.
- 금융위 2021-05-03 보도자료: 직접 대가를 받는 개인방송은 신고 대상, 광고수익·간헐적 후원만 있는 경우는 신고 대상에서 제외로 설명. 같은 자료가 유사투자자문업자의 AI 자동매매 프로그램 판매·제공을 불법 유형으로 열거.
- 지인 간 무료·비영리 공유를 직접 다룬 공식 문서: 확인 못 함. 알고리즘이 만든 종목 목록의 이메일 발송을 다룬 공식 문서: 확인 못 함.
- 유사투자자문업자의 표시 의무(개별 상담 불가, 원금 손실 가능성 고지)와 금지 행위(이익 보장, 허위·미실현 수익률, 유리한 기간만 제시)는 보도자료 기준. 법정 문구 원문은 확인 못 함.
- 출처: https://www.law.go.kr/법령/자본시장과금융투자업에관한법률/제101조 , https://www.fsc.go.kr/po010101/82887?curPage=89 , https://fsc.go.kr/po010105/75847

## 겹치는 것 · 엇갈리는 것
- **겹침**: 국내 전 종목의 하루치 시세를 한 번에 주는 경로(FDR 목록, pykrx, KRX Open API, 공공데이터포털)는 모두 KRX 가 원천이다.
- **겹침**: FDR 과 yfinance 는 미국 종목에서 같은 Yahoo 를 읽는다. 한쪽이 막히면 다른 쪽도 막힌다.
- **엇갈림**: FDR 이슈에는 "KOSPI 목록이 비어 온다"(2026-09-29)가 열려 있지만, 2026-10-08 실행에서는 942종목이 정상으로 왔다. 이슈가 말하는 대로 간헐적일 수 있다.
- **엇갈림**: yfinance 에서 950종목 뒤 차단됐다는 보고와 단일 호출에서도 차단됐다는 보고가 함께 있다. 8종목 일괄 호출은 이 PC 에서 문제없었다. 한도의 실제 위치는 알 수 없다.
- **엇갈림**: DART 한도 "20,000건"을 일 단위로 적은 2차 출처가 많지만 공식 문구에는 기간이 없다.
- **엇갈림**: 이동평균·RSI 는 지지하는 연구와, 다중 검정·거래비용을 넣으면 사라진다는 연구가 함께 있다.
- **엇갈림**: 모멘텀(12-1)은 직전 1개월을 뺀다. 직전 1주~1개월은 반전이 보고돼 있어 "최근 많이 오른 종목"을 단기 후보로 뽑는 규칙과 방향이 반대다.
- **엇갈림**: 국내 PER·PBR 은 pykrx 문서에는 있고, yfinance 실행 결과에는 없다.

## 트레이드오프 (사실만. 판단은 분석 단계)
| 항목 | A: 관심 종목 시세 | B: 가격·거래량 규칙 (일봉) | C: 재무 팩터 | D: 분 단위 신호 |
|---|---|---|---|---|
| 필요한 데이터 | 종목별 최근 종가 | 종목군 전체의 약 1년 일봉·거래량 | B + 재무제표 또는 지표 | 분봉·실시간 |
| 확인된 무료 출처 | FDR·yfinance (✅ 동작) | 국내: FDR 종목별(✅), 전 종목 하루치(✅). 미국: FDR·yfinance 종목별(✅), 대량은 미시험 | 국내: DART(문서 확인, 미실행). 미국: SEC EDGAR(문서), yfinance `.info`(✅ 1종목) | 한국투자증권 Open API (계좌 필요, 미확인) |
| 하루 호출 수 (수백 종목 기준) | 종목 수만큼 | 이력을 저장하지 않으면 종목 수만큼, 저장하면 국내는 1회 | DART 100개사당 1회. EDGAR `frames` 는 항목당 1회 | 확인 못 함 |
| 코드베이스 변경 범위 | 설정에 심볼 추가, `Market` 값 추가 | 거래량·이력을 읽는 수집, 이력 저장소 | 새 어댑터(DART 재무·EDGAR), 종목코드 매핑, 공시 시점 처리 | 새 출처, 실행 주기 변경 |
| 알려진 제약 | 장중 실행 시 장중 값 | Yahoo 한도 불명, KRX 경로 간헐 장애 보고 | 공시 지연 45~90일, 국내 가격 지표 출처 미확정 | 계좌·인증, 일봉 기반 설계와 실행 주기가 다름 |
| 학술 근거 | 해당 없음 | 52주 고가·거래량은 지지 연구 있음. MA·RSI 는 엇갈림 | 가치·수익성·모멘텀은 지지 연구 다수 | 조사하지 않음 |
| 되돌리기 난이도 | 확인 못 함 | 확인 못 함 | 확인 못 함 | 확인 못 함 |

## 확인 못 한 것
- [ ] yfinance·FDR 로 수백 종목의 1년 일봉을 한 번에 받을 때 실제로 차단되는지, 걸리는 시간
- [ ] pykrx 의 어느 함수가 KRX 로그인 대상인지, `get_market_fundamental` 이 지금 동작하는지
- [ ] DART `fnlttMultiAcnt`·`fnlttCmpnyIndx` 를 이 프로젝트의 키로 실제 호출한 결과 (응답 크기, 누락 종목, 금융업의 계정 차이)
- [ ] DART 재무지표 API 에 PER·PBR 이 있는지
- [ ] DART 한도 20,000건의 기간 단위와 분당 한도
- [ ] SEC `frames` 가 S&P 500 을 얼마나 덮는지 (회계연도가 달력과 다른 회사)
- [ ] yfinance `.info` 필드의 신뢰도와 `dividendYield` 의 단위
- [ ] KRX Open API 의 요금·한도 (공식)
- [ ] 한국투자증권 Open API 의 요금, 분봉 조회 가능 기간
- [ ] 지인에게 무료로 종목 목록을 보내는 행위에 대한 공식 해석
- [ ] 증권거래세율의 법령 원문, 통상 수수료율
- [ ] 논문 DOI 대부분 (서브에이전트가 기억으로 적었다고 밝힘)

## 열린 질문 → 분석 단계로
- [ ] 종목군을 어디까지 볼 것인가? (국내: KOSPI 200 / 전 종목 2,872개, 미국: S&P 500 / Nasdaq 100)
- [ ] 가격 이력을 매일 다시 받을 것인가, DB 에 쌓을 것인가? (국내는 전 종목 하루치가 한 번에 온다)
- [ ] 단기 후보의 "단기"는 며칠인가? 일봉으로 충분한가, 분 단위(한국투자증권 계좌)가 필요한가?
- [ ] 엇갈리는 단기 규칙(최근 급등 vs 단기 반전) 중 무엇을 싣는가, 둘 다 싣는가?
- [ ] 장기 후보의 국내 PER·PBR 을 어디서 얻는가? (pykrx, 직접 계산 = DART 순이익·자본 ÷ 시가총액)
- [ ] 백테스트를 메일에 싣기 전의 조건으로 둘 것인가, 나중으로 미룰 것인가?
- [ ] 메일에서 무엇이라고 부를 것인가? ("추천" / "조건 충족 종목") 고지 문구를 넣을 것인가?
- [ ] 수신 범위가 지인 10명 이하·무료에서 벗어날 계획이 있는가?
- [ ] 관심 종목 목록은 무엇인가? (사용자가 아직 정하지 않았다)

## 참고
- [FinanceDataReader](https://github.com/FinanceData/FinanceDataReader) — 종목 목록, 국내·미국 일봉
- [pykrx](https://github.com/sharebook-kr/pykrx) — 날짜별 전 종목 시세·PER·PBR
- [OpenDART 재무정보 가이드](https://opendart.fss.or.kr/guide/main.do?apiGrpCd=DS003) — 다중회사 주요계정, 재무지표
- [SEC EDGAR API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) — companyfacts, frames
- [yfinance](https://ranaroussi.github.io/yfinance/) — 일괄 다운로드, 사용 목적 문구
- [한국투자증권 Open API](https://apiportal.koreainvestment.com/apiservice-category) — 분봉·실시간
- [금융위 2024-08-13 보도자료](https://www.fsc.go.kr/po010101/82887?curPage=89) — 유사투자자문업 규제
- [Ken French Data Library: Momentum](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor.html) — 12-1 모멘텀 정의
