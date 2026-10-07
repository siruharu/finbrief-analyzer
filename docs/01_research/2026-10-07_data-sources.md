---
type: research
project: finbrief-analyzer
topic: 데이터 출처 (시세·뉴스 API)
created: 2026-10-07
status: draft        # draft | done
tags: [research, data-source, market-data, news]
next: analysis
---

# 🔍 데이터 출처 (시세·뉴스 API)

> **핵심 질문** — 일일 금융 브리핑에 쓸 시세·뉴스 API 로 무엇이 있고, 각각의 비용·한도·이용약관(재배포) 조건은 무엇인가?

## 배경
finbrief-analyzer 는 시세·뉴스를 수집·분석해 일일 브리핑을 만들고 구독자에게 보낸다.
수집한 데이터를 **가공해 제3자에게 전송**하는 구조이므로, 호출 한도·요금뿐 아니라
약관의 재배포·상업적 이용 조항이 출처 선택의 재료가 된다.
발송 채널은 별도 노트 [2026-10-07_delivery-channels.md](2026-10-07_delivery-channels.md).

표기: ✅ = 메인 세션에서 원문 직접 확인(2026-10-07), 표기 없음 = 서브에이전트 요약 기준.
요금은 별도 표기가 없으면 USD.

## 코드베이스 안에 이미 있는 것
| 위치 | 하는 일 | 재사용 가능? |
|---|---|---|
| `src/finbrief_analyzer/` 전체 | 앱 팩토리(`main.py:10-20`)와 `/health` 라우트(`api/routes.py:16-19`)뿐. 외부 HTTP 호출·수집·스케줄링 코드 없음 | 해당 없음 |
| `pyproject.toml:6-19` | 런타임 의존성은 fastapi·uvicorn·pydantic-settings. `httpx` 는 dev 그룹에만 있음. requests·boto3·스케줄러 없음. 버전 제약 없음 | — |
| `core/config.py:8-14` | `Settings`(`env_prefix="APP_"`), 필드 4개(name·host·port·log_level). 비밀값 필드·`SecretStr` 없음 | API 키를 받을 자리 |
| `deploy/terraform/service/variables.tf:75-76`, `main.tf:83` | `secrets` 맵(환경변수 이름 → SSM/Secrets Manager ARN)이 컨테이너 `secrets.valueFrom` 으로 주입됨 | API 키 주입 경로 |
| `deploy/terraform/platform/cluster.tf:75-79,152`, `network.tf:18,88-92` | ECS 호스트는 프라이빗 서브넷, NAT 게이트웨이 경유, egress 0.0.0.0/0 전 프로토콜 | 외부 API 호출 경로 |
| `deploy/terraform/service/main.tf:25-203` | EventBridge/Scheduler/cron 리소스 없음 | 일 1회 수집 트리거는 없음 |
| `compose.yml:9-60` | 로컬 프로파일 db(postgres:18)·cache(redis:8)·mq(rabbitmq:4)·mqtt(mosquitto:2). 앱에서 접속하는 코드는 없음 | — |

git 이력은 템플릿 초기화 커밋 1건(`b87d142`)뿐이라 과거에 시도했다 접은 방식은 없다.

## 외부 조사

### 시세 — 한국

#### 옵션 A1 — 한국투자증권 KIS Developers
- 버전: 확인 못 함 (REST Open API, 버전 표기 미확인)
- 요약: appkey/appsecret 으로 토큰 발급(1분당 1회), 계좌번호 필요. 제3자에게 서비스를 제공하는 "제휴"는 투자일임·자문업 등 제도권 금융회사만 대상이고 개인·일반법인·핀테크는 대상이 아님. 제휴사가 시세를 제공하려면 KRX·해외거래소와 정보이용계약 필요. 실전 초당 20건이라는 수치는 비공식 출처로만 확인.
- 출처: https://apiportal.koreainvestment.com/provider , https://github.com/koreainvestment/open-trading-api , (비공식) https://algolab.co.kr/platforms/kis

#### 옵션 A2 — 공공데이터포털 금융위원회 주식시세정보
- 버전: 확인 못 함
- 요약 ✅: 무료, 서비스키 인증. 트래픽 "개발계정 : 10,000 / 운영계정 : 활용사례 등록시 신청하면 트래픽 증가 가능". 이용허락범위 "출처표시, 상업적 이용금지, 변경금지 (제 4유형)". "실시간이 아니며, 데이터 갱신은 기준일자로부터 영업일 하루 뒤 오후 1시 이후". 상업적 이용은 KRX Data Marketplace 유료 구매로 안내(서브에이전트 확인).
- 출처: https://www.data.go.kr/data/15094808/openapi.do

#### 옵션 A3 — KRX Open API / 정보데이터시스템
- 버전: 확인 못 함
- 요약 ✅: Data Marketplace 가입 후 인증키 신청, 서비스별 관리자 승인. 약관 제6조② "may only use the API Service for non-commercial purposes and may not charge third parties any consideration", 제8조④ 키당 일 10,000건, 제11조② "may not provide the data provided by the KRX to any third parties". 정보데이터시스템 면책조항은 사전 허가 없는 복제·전송·제3자 배포를 금지(서브에이전트 확인).
- 출처: https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO005.jsp , https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp , https://data.krx.co.kr/templets/mdc/disclaimer_p1.jsp

#### 옵션 A4 — 한국은행 ECOS (환율·금리)
- 버전: 확인 못 함
- 요약: 인증키 신청 페이지가 있다는 것만 확인. 한도·비용·이용 조건은 확인 못 함.
- 출처: https://ecos.bok.or.kr/api/#/AuthKeyApply

#### 옵션 A5 — pykrx (비공식)
- 버전: 1.2.9 (2026-09-19), MIT
- 요약: KRX·Naver 스크레이핑. 일부 API 는 KRX 로그인 환경변수 필수. README 는 저작권이 제공처에 있고 상업적 사용 시 제공처 약관을 지키라고 명시.
- 출처: https://pypi.org/pypi/pykrx/json , https://github.com/sharebook-kr/pykrx

#### 옵션 A6 — FinanceDataReader (비공식)
- 버전: 0.9.202 (2026-05-13), MIT
- 요약: 스스로 "crawler" 라고 밝힘. 소스는 KRX·Naver·Yahoo·Investing 등. 지수·환율·암호화폐 포함.
- 출처: https://pypi.org/pypi/finance-datareader/json , https://github.com/FinanceData/FinanceDataReader

### 시세 — 해외/글로벌

| 옵션 | 무료 한도 | 유료 시작가 | 약관의 재배포·상업적 이용 문구 | 출처 |
|---|---|---|---|---|
| B1 Alpha Vantage | 일 25건 | 월 $49.99 (분당 75건) | 개인·비상업 기본. User 외의 사람이 정보에 접근하게 하는 상업 활동은 "commercial use" 로 별도 문의(§2.a) | [요금](https://www.alphavantage.co/premium/) · [약관](https://www.alphavantage.co/terms_of_service/) |
| B2 Finnhub | 확인 못 함 (비공식: 분당 60건) | 확인 못 함 (비공식: 약 $50) | 서면 승인 없이 데이터·파생 결과의 제3자 재배포·공유 금지. 웹사이트 플랜은 개인용, 사업체는 내부 사용도 서면 승인 필요. 플랜과 별개로 초당 30건 상한 | [약관](https://finnhub.io/terms-of-service) · [한도](https://finnhub.io/docs/api/rate-limit) |
| B3 Twelve Data | 분당 8크레딧·일 800 ("Internal non-display usage") | Grow 월 $79 | 재배포·외부 표시는 Redistribution Rights Add-On 또는 별도 서면 계약 필요(§2.2(e), §2.3(b)). 무료 티어 상업적 이용 금지(§2.3(l)). 한국 3개 거래소는 Pro/Venture 에서 EOD | [요금](https://twelvedata.com/pricing) · [거래소](https://twelvedata.com/exchanges) · [약관](https://twelvedata.com/terms) |
| B4 Massive (구 Polygon.io) | 분당 5건·EOD·2년 이력 | Stocks Starter 월 $29 (15분 지연), Advanced 월 $199 (실시간), "Individual use only" | 개인 약관은 "personal, non-commercial, and non-business purposes" 한정(§2), 접근권·자료의 판매·이전 금지(§6.1(h)) | [요금](https://massive.com/pricing) · [약관](https://massive.com/legal/individuals-terms-of-service) |
| B5 Financial Modeling Prep | 일 250건·EOD | Starter 월 $19 (연 결제, US), Global 은 Ultimate 월 $99 (연 결제) | 개인 플랜은 개인·비상업용(§2.2.1). 표시·재배포에는 별도 Data Display and Licensing Agreement 필요(§2.2.2) | [요금](https://site.financialmodelingprep.com/developer/docs/pricing) · [약관](https://site.financialmodelingprep.com/terms-of-service) |
| B6 EODHD | 일 20건 | 월 $19.99 (일 100,000건) | Personal 플랜과 Commercial/B2B 플랜을 구분 | [요금](https://eodhd.com/pricing) |
| B7 yfinance (비공식) 1.7.0 (2026-08-26), Apache-2.0 | 키 없음. 429/YFRateLimitError 보고 있음 | — | README: 연구·교육 목적, "personal use only". Yahoo 약관은 명시적 허용 없는 상업적 재사용·배포·자동 수집 금지 | [PyPI](https://pypi.org/pypi/yfinance/json) · [이슈](https://github.com/ranaroussi/yfinance/issues/2422) · [Yahoo 약관](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) |

### 뉴스·공시 — 한국

#### 옵션 C1 — 네이버 검색 API (뉴스)
- 버전: v1 (`/v1/search/news`)
- 요약: 검색 API 하루 25,000회. title·originallink·link·description(요약 패시지)·pubDate 제공, 본문 없음. display 최대 100, start 최대 1000. 헤더 `X-Naver-Client-Id`/`Secret`.
- 약관 ✅(조항 2.1~2.4 존재 확인): "네이버 검색결과를 제공하기 위한 목적으로만" 이용, 가공 없이 노출, 출처 표시·원문 링크 의무. 금지 행위로 데이터의 제3자 제공·판매, **AI 에 입력하거나 학습·개선·평가·노출 등에 활용**, 복사·저장·캐싱(2.4 예외: 이력 조회용 최대 21일).
- 출처: https://developers.naver.com/docs/serviceapi/search/news/news.md , https://developers.naver.com/products/terms/

#### 옵션 C2 — 카카오/다음 검색 API
- 버전: v2
- 요약: 웹문서·동영상·이미지·블로그·책·카페 6종. **뉴스 검색은 문서에 없음.** 각 30,000건/일, 월 3,000,000건.
- 출처: http://developers.kakao.com/docs/ko/daum-search/dev-guide , http://developers.kakao.com/docs/ko/getting-started/quota

#### 옵션 C3 — 빅카인즈 (한국언론진흥재단)
- 버전: 확인 못 함
- 요약: "OPEN API 서비스 신청/사용현황" 메뉴가 있음. 요금·한도·필드·신청 자격은 확인 못 함. 사이트 하단에 "모든 기사는 「저작권법」의 보호를 받으며, 이를 전재, 복제, 배포하는 행위를 금합니다".
- 출처: https://www.bigkinds.or.kr/v4/openApi/index.do , https://www.bigkinds.or.kr/

#### 옵션 C4 — 금융감독원 DART Open API (공시)
- 버전: 확인 못 함
- 요약: 공시검색(list.json), 공시 원문 XML, 재무정보. `crtfc_key`(40자리). 오류코드 020 이 "일반적으로는 20,000건 이상의 요청에 대하여" 발생. 요금 표기 없음. 약관에 재배포·상업적 이용·출처표시 조항은 없고 제10조 4항에 허용량 제한만 있음.
- 출처: https://opendart.fss.or.kr/intro/main.do , https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001 , https://opendart.fss.or.kr/intro/terms.do

#### 옵션 C5 — 언론사 RSS
- 버전: 해당 없음
- 요약: 연합뉴스는 "비상업적 블로그와 개인적인 용도로만 … 허용", "사전 서면 허가 없이 RSS 서비스를 상업적으로 이용하는 것을 금지". 한국경제(13개 피드)·매일경제는 RSS 페이지에 전용 이용 조건 문구 없음.
- 출처: https://www.yna.co.kr/rss/index , https://www.hankyung.com/feed , https://www.mk.co.kr/rss

### 뉴스·공시 — 해외

| 옵션 | 무료 한도 | 유료 시작가 | 제공 범위 | 약관·이용 조건 문구 | 출처 |
|---|---|---|---|---|---|
| D1 NewsAPI.org | 100회/일, 24시간 지연, 최근 1개월 | Business 월 $449 | content 200자 절단. 지원 언어에 ko 없음 | Developer 는 "development environment only, and cannot be used in a staging or production environment (including internally)" | [요금](https://newsapi.org/pricing) · [약관](https://newsapi.org/terms) |
| D2 GNews | 100회/일, 요청당 10건, 12시간 지연 | Essential 월 €49.99 | 무료는 본문 절단, 유료는 전문. 한국어 없음 | Free 는 "non-commercial projects, development and testing only". 약관 3.3: 상업적 이용 가능하되 저작권법 준수 | [요금](https://gnews.io/pricing) · [약관](https://gnews.io/legal/terms-of-service) |
| D3 Finnhub news | 확인 못 함 | 확인 못 함 | 확인 못 함 | 시세 B2 와 동일 약관 | [약관](https://finnhub.io/terms-of-service) |
| D4 Alpha Vantage NEWS_SENTIMENT | 일 25건 (키 공통) | 월 $49.99 | 제목·요약·URL·감성. 문서에 "Premium" 라벨 | 시세 B1 과 동일 약관 | [문서](https://www.alphavantage.co/documentation/#news-sentiment) |
| D5 Marketaux | 100회/일, 요청당 3건 | Basic 월 $29 (2,500회/일) | title·description·snippet·url. 전문 없음. ko 지원 | 사이트 콘텐츠는 "solely for your personal, non-commercial use". API 데이터 재배포 전용 조항은 찾지 못함 | [요금](https://www.marketaux.com/pricing) · [약관](https://www.marketaux.com/tos) |
| D6 Google News RSS | 한도 표기 없음 | — | 제목·링크 | 피드 `<copyright>`: "personal feed reader for personal, non-commercial use. Any other use of the feed is expressly prohibited" | [피드](https://news.google.com/rss/search?q=economy&hl=ko&gl=KR&ceid=KR:ko) |
| D7 SEC EDGAR | 최대 10 요청/초 | 무료 | 제출 이력·XBRL JSON | 키 없음, User-Agent 선언 요구. 해당 페이지에 재이용 제한 문구 없음 | [안내](https://www.sec.gov/os/accessing-edgar-data) |

### 한국 뉴스 저작권 — 한국언론진흥재단 「디지털 뉴스콘텐츠 이용규칙」
- 단순링크 ✅: "웹사이트를 단순링크하는 방법으로 자유롭게 이용할 수 있다" (단순링크 = 메인 페이지 링크).
- 직접링크: 개별 기사 링크는 저작권법상 복제·전송에 해당하지 않는다는 것이 법원 판단이지만, 업무적·상업적으로 이용해 경제적 이득을 취하면 민법상 부당이득·불법행위 책임을 질 수 있다고 안내 (서브에이전트 인용. 메인 세션 확인에서는 정의 문구만 확인).
- RSS ✅: "개인 PC 등 한정된 공간 안에서 … 개인적으로 구독 이용하는 데 그쳐야 하며", 허락 없는 공중 배포·재RSS 는 "무단 복제, 무단 공중송신에 해당하므로 금지".
- 온라인 뉴스레터 ✅: "다수의 이용자에게 이메일을 통해 배포되는 온라인 뉴스레터 … 에도 본 '이용규칙'이 제시한 원칙은 그대로 적용된다."
- 기사 제목·요약 이용에 관한 별도 문구 ✅: 해당 게시물에 없음.
- 출처: https://www.kpf.or.kr/front/board/boardContentsView.do?board_id=291&contents_id=855b0c963b5c4a42ba6b26d06c7186d4 (2020-01-21 게시)

## 겹치는 것 · 엇갈리는 것
- **겹침**: 조사한 시세 출처 중 무료·개인 플랜에서 제3자 제공을 명시적으로 허용하는 약관은 발견되지 않았다. 한국 공식 출처(A2·A3)는 비상업·제3자 제공 금지, 해외 출처(B1~B5)는 재배포에 별도 계약·애드온을 요구한다.
- **겹침**: Finnhub 약관 문구는 시세·뉴스 두 조사에서 동일하게 확인됐다.
- **엇갈림**: Alpha Vantage 약관 — 시세 조사는 HTML 약관(§2.a)을 읽었고, 뉴스 조사는 약관 PDF 판독에 실패해 "확인 못 함"으로 보고했다.
- **엇갈림**: Finnhub 무료 한도 — 공식 페이지(JS 렌더링)에서는 두 조사 모두 확인하지 못했고, 비공식 출처에만 분당 60건으로 나온다.
- **재배포 제한 문구가 없는 출처**: DART Open API 약관, SEC EDGAR 안내 페이지. (문구가 "없음"을 확인한 것이며 허용 문구를 확인한 것은 아니다.)

## 트레이드오프 (사실만. 판단은 분석 단계)
| 항목 | 공식 무료 API (A2·A3·C1·C4) | 유료 상용 API (B·D 유료 플랜) | 비공식 라이브러리 (A5·A6·B7) | RSS (C5·D6) |
|---|---|---|---|---|
| 구현 비용 | 키 발급·승인 절차. REST 호출 | 키 발급. REST 호출 | pip 설치, 키 불필요(pykrx 일부는 KRX 로그인 필요) | 피드 파싱 |
| 운영 비용 | 무료, 일 10,000~25,000건 한도 | 월 $19~$449, 재배포는 별도 계약·애드온 | 무료. 스크레이핑 기반, 429 보고(yfinance) | 무료 |
| 생태계/레퍼런스 | 공식 문서 있음 | 공식 문서 있음. 한국 주식 커버리지는 대부분 확인 못 함 | pykrx 2026-09, FDR 2026-05, yfinance 2026-08 릴리스 | 섹션별 피드 |
| 약관 문구 | A2·A3 비상업·제3자 제공 금지, C1 가공·AI 입력·제3자 제공 금지, C4 제한 문구 없음 | 개인 플랜은 비상업, 재배포는 별도 계약 | 제공처 약관을 따르라고 README 가 명시 | 연합·Google 은 개인·비상업 한정 문구, 한경·매경은 문구 없음 |
| 되돌리기 난이도 | 확인 못 함 | 확인 못 함 (계약 기간 조건 미조사) | 확인 못 함 | 확인 못 함 |

## 확인 못 한 것
- [ ] KIS: 공식 유량 제한 수치, 이용 요금, 토큰 유효기간, 시세 제3자 제공에 관한 약관 조항 원문
- [ ] ECOS: 호출 한도, 비용, 저작권·상업적 이용 조건, 제공 통계 목록
- [ ] KRX Open API 의 비용·데이터 제공 시점, KRX Data Marketplace 의 상업용 시세 요금
- [ ] 공공데이터포털 운영계정 트래픽 수치
- [ ] Finnhub 공식 요금·무료 한도·뉴스 엔드포인트 필드·한국 주식 커버리지
- [ ] Alpha Vantage·Massive·EODHD·FMP(Global) 의 한국 주식 커버리지, Alpha Vantage 무료 티어 지연 여부, NEWS_SENTIMENT 가 무료 키로 호출되는지
- [ ] pykrx·FinanceDataReader 의 구체적 차단·중단 이슈
- [ ] 빅카인즈 Open API 의 요금·한도·필드·신청 자격·약관
- [ ] 네이버 검색 API 의 유료·제휴 조건(약관 제한을 푸는 계약이 있는지)
- [ ] 한국경제·매일경제 RSS 의 상업적 이용 조건(각 사 저작권 규약)
- [ ] 한국언론진흥재단 뉴스저작물 이용허락 계약의 절차·사용료
- [ ] 이용규칙에서 "제목만" 사용, "요약(LLM 포함)" 에 대한 문구 — 해당 게시물에는 없음. 다른 공식 안내가 있는지 미확인
- [ ] 각 해외 API 의 상업·재배포 플랜 실제 견적 (대부분 문의 방식)

## 열린 질문 → 분석 단계로
- [ ] 브리핑 대상 시장은 어디까지인가 (국내 주식만 / 미국 주식 / 환율·금리·암호화폐)?
- [ ] 서비스가 유료인가 무료인가, 운영 주체가 개인인가 사업자인가? (약관의 "상업적 이용"·"개인용" 조항 해당 여부가 여기에 달려 있다)
- [ ] 구독자가 본인·소수 지인인가 불특정 다수인가? ("제3자 제공" 조항 해당 여부)
- [ ] 브리핑에 개별 종목 시세 수치를 그대로 싣는가, 지수·등락률 수준의 가공 지표만 싣는가?
- [ ] 뉴스는 제목+링크만 싣는가, LLM 요약을 싣는가? (네이버 약관의 AI 입력 금지, 이용규칙의 뉴스레터 조항과 맞닿는다)
- [ ] 공시(DART·EDGAR)를 뉴스의 대체·보완 재료로 볼 것인가?
- [ ] 월 예산 상한은 얼마인가?

## 참고
- [KRX Open API 이용약관](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO005.jsp) — 비상업·제3자 제공 금지·일 10,000건
- [공공데이터포털 주식시세정보](https://www.data.go.kr/data/15094808/openapi.do) — 공공누리 4유형, 익영업일 13시 이후 갱신
- [KIS 제휴 안내](https://apiportal.koreainvestment.com/provider) — 제3자 서비스 제공 대상 요건
- [네이버 개발자센터 이용약관](https://developers.naver.com/products/terms/) — 검색 API 조항 2.1~2.4
- [디지털 뉴스콘텐츠 이용규칙](https://www.kpf.or.kr/front/board/boardContentsView.do?board_id=291&contents_id=855b0c963b5c4a42ba6b26d06c7186d4) — 링크·RSS·뉴스레터 원칙
- [Twelve Data 약관](https://twelvedata.com/terms) — 재배포 애드온 조항
- [Massive 요금](https://massive.com/pricing) — 구 Polygon.io
- [DART Open API 약관](https://opendart.fss.or.kr/intro/terms.do) — 재배포 제한 문구 없음
