---
type: research
project: finbrief-analyzer
topic: news-summary
created: 2026-10-12
status: done
tags: [research, news, llm, summary]
next: analysis
---

# 🔍 LLM 뉴스 선별·요약 단계

> **핵심 질문** — 수집해 둔 뉴스(국내 RSS 제목·요약, Marketaux 영문 기사, DART 공시)에서 브리핑에 실을 몇 건을 고르고 한국어로 요약하는 단계를 만들려면, 입력으로 쓸 수 있는 재료·약관, 모델·비용·구조화 출력 수단, 실패 시 대체 경로는 각각 무엇인가.

조사 방법: 서브에이전트 4개(코드베이스 / 외부 API / 입력 자료·약관 / 이력)의 요약을 교차했다. 결정을 좌우하는 수치(SDK 버전, 모델 가격)는 PyPI 와 이 세션의 Claude API 참조표로 직접 확인했다. 피드·약관 페이지는 에이전트가 2026-10-12 에 직접 받아 읽었다.

## 배경
- 2026-10-07 사용자 조건에 "뉴스 | LLM 요약까지"가 있다 ([[2026-10-07_data-sources]] 분석 :34). 그 분석의 전제: **"뉴스는 기사 본문을 옮기지 않는다. 제목·RSS 요약을 입력으로 LLM 이 자기 문장으로 흐름을 요약하고 원문 링크를 붙인다"** (:89).
- 모델 선택과 프롬프트는 세 번 연기됐다: data-sources 분석 :114, data-sources 플랜 :20-21, delivery-channels 플랜 :25 ("단순 작성기 v0 로 끝까지 연결하고 LLM 요약은 그 자리를 나중에 대체"). 코드·PoC·프롬프트는 git 이력에 전혀 없다.
- 지금 메일의 뉴스 섹션: 수집 결과 **최신순 앞 10건**을 제목·출처·링크로 나열한다. 선별도 요약도 없다 (`compose/simple.py:11,128-133`). 작성기 docstring 이 "summarising step's job, which does not exist yet" 로 자리를 비워 뒀다 (`simple.py:10`).

## 코드베이스 안에 이미 있는 것
| 위치 | 하는 일 | 재사용 가능? |
|---|---|---|
| `collect/models.py:79-91` `NewsItem` | `title, link, source, published_at, summary: str \| None`. 본문 필드 없음. 동등성은 `link` 하나 | ✅ 입력 단위 그대로 |
| `collect/service.py:28-35,162-178` | 슬롯별 lookback KR 11h / US 14h. 링크로 중복 제거 → 최신순 → **출처당 15·전체 80** 로 자른다. 상한의 키는 `item.source`(RSS 는 host, Marketaux 는 기사 출처) | ✅ LLM 입력은 이 80건 이하 |
| `collect/news_rss.py:88-99` | description 을 평문화해 `summary` 로. 제목과 같으면 None. 연합의 "(서울=연합뉴스) ○○ 기자 =" 머리말은 **제거하지 않는다** ([[2026-10-07_news-rss]] :83) | 전처리 필요 여부는 분석 몫 |
| `collect/news_marketaux.py:24,118-125` | 호출당 3건, 슬롯당 최대 3회(설정). `description` 만 쓰고 `snippet` 은 버린다(차단 문구 섞임) | ✅ |
| `collect/news_dart.py:97-102` | 제목 = "회사명 보고서명", summary 없음, 시각 없음(KST 자정) | 입력에 넣을지는 열린 질문 |
| `compose/simple.py:48,98-101` | 섹션 순서: 안내 → 시세(첫 묶음만 required) → 스크리닝 → 뉴스. **뉴스 섹션은 required 가 아니다** → 비어도 메일은 간다 | ✅ 실패 시 대체 경로의 근거 |
| `deliver/models.py:35-82` | `Section(title, lines, links, required)`, `LinkItem(title, url, source)`. 작성기↔렌더러 계약을 "LLM 작성기로 바꿀 때 렌더러가 안 바뀌게" 설계 ([[2026-10-08_deliver-render]] :15,26) | ✅ `lines`(요약 문장) + `links`(원문) 로 표현 가능 |
| `core/config.py:84,91-94,147-155` | `APP_` 접두, `.env`, 키는 `SecretStr \| None`, 빈 값 = 비활성 | ✅ `APP_ANTHROPIC_API_KEY` 같은 꼴 |
| `collect/factory.py:18-20,34-43` | `httpx.Client(timeout=30)`; 키가 있는 소스만 연결 | SDK 는 자체 클라이언트를 쓴다(아래) |
| `jobs/run_briefing.py:62-63` | `compose_simple(deps.collect(slot, now), day)` → `dispatch` | 새 단계는 collect 와 compose 사이, 또는 compose 안 |
| 테스트 관례 | 외부 HTTP 는 `httpx.MockTransport`; 주석 `# given:` `# when` `# then`; fixture `store`, `add_recipient` | SDK 호출의 가짜 객체 방식은 확인 못 함 |

## 입력 자료 실측 (2026-10-12)
| 피드 | 건수 | description | 비고 |
|---|---|---|---|
| 한국경제 economy / finance | 50 / 50 | **없음**(태그 자체 없음) | 제목 중앙값 33자 |
| 매일경제 30100041 / 50200011 | 50 / 50 | 48/50, 49/50 존재. **102자 고정 절단**("..") | 기본 UA 는 403, 브라우저 UA 로 200 |
| 연합뉴스 economy / market | 120 / 86 | 전부 존재. 1~103자, 중앙값 83자(리드 1문장 절단). 44건이 83자 | "(서울=연합뉴스) ○○○ 기자 =" 접두 |
| Marketaux (문서) | 호출당 3건, 하루 100회 | `description` = meta description(67~345자 실측, 10-07). 전문 필드 없음 | `snippet` 은 본문 조각이나 차단 문구 섞임 |
| DART | 페이지당 100행 | 요약 없음 | 공시 제목뿐 |

- 어느 출처도 HTML·전문(`content:encoded`)을 주지 않는다. **LLM 에 줄 수 있는 것은 제목 + 최대 100자 안팎의 리드**다. 2026-10-07 분석이 적어 둔 리스크 "RSS 요약이 너무 짧아 LLM 요약이 제목 나열에 그침" (:101) 은 실측으로 확인된 셈이다.
- 12시간 수집량은 339건(연합 194)이었고, 상한 뒤 80건 이하가 입력이 된다 ([[2026-10-07_news-rss]] :76,81-82).

## 약관·저작권 (원문 확인, 사실만)
- **한국경제** 이용약관 제19조: 자동화 수단으로 콘텐츠를 "수집·사용"하는 행위를 서면 허가 없이 불허(①); "인공지능(AI) 학습 데이터로 이용할 경우 사전에 회사의 동의"(②); 서비스로 얻은 정보의 가공·판매 등 상업적 사용 금지(④). RSS 전용 조건 페이지는 403 → 확인 못 함.
- **매일경제** 이용약관 제22조: "콘텐츠… 인공지능(AI) 학습데이터 등에 활용할 경우 회사와 사전에 반드시 합의"; 푸터 "무단 전재, 재배포 및 AI학습 이용 금지". RSS 페이지에는 이용 조건 없음.
- **연합뉴스** RSS 안내: "비상업적 블로그와 개인적인 용도로만 연합뉴스 RSS 피드를 사용하는 것을 허용"; 저작권규약: 계약 사용자는 "인공지능(AI)의 학습이나 인공지능 서비스에 사용하는 등 허가된 목적 이외에" 이용 불가.
- **Marketaux** ToS(2021-01-10): 라이선스는 "solely for your personal, non-commercial use"; "not access the Site through automated or non-human means". AI·캐싱·재배포·attribution 조항 없음. Free: 100 requests/day, 3 articles/request.
- 세 언론사 모두 **"학습(training)"을 적었고, "추론 입력"을 따로 다룬 문장은 없다.** 2026-10-07 리서치도 "재단 이용규칙에 요약(LLM) 문구 없음"이라 적었다 (:128,159). 두 조사가 일치한다. 네이버 검색 API 만 "AI 에 입력" 자체를 금지해 이미 제외됐다.
- 저작권법 제7조 5호 "사실의 전달에 불과한 시사보도"는 보호 대상이 아니다. KPF 는 그 범위를 "인사발령·부고·주식시세 등 오로지 사실만으로 구성된 기사"로 좁게 본다. 한국저작권보호원 지침(2020, KPF 집필) p.134: **"기사 제목과 링크를 이메일로 전송하는 것은 저작권 침해가 아닙니다. 기사 제목과 함께 언론사명, 발행일자, 기사의 첫 한두 줄 정도를 함께 보내는 것도 무방합니다"**; 요약은 "원래 표현을 단순히 축약하는 정도"면 침해 가능, "총괄적인 뜻만 살린 전혀 새로운 창작물"이면 아닐 수 있음(KPF FAQ). 모두 **영리 목적이면 다르다**고 단서를 단다. 이 프로젝트의 전제는 "본인+소수 지인·무료·비상업" ([[2026-10-07_data-sources]] 분석 :86-87).

## 외부 조사

### 옵션 A — Anthropic Claude API
- 버전: Python SDK `anthropic` **1.13.0** (2026-10-09, PyPI 직접 확인), Python ≥3.10. 1.x 는 `httpx2` 기반 — 프로젝트의 `httpx==0.28.1` 과 별개 패키지라 충돌하지 않지만, SDK 에 `httpx.Client` 를 넘길 수는 없다.
- 모델·가격(입력/출력 $/1M, 2026-10-06 참조표 = 에이전트 확인치): Haiku 5.5 `claude-haiku-5-5` 0.10/0.50 (프롬프트 100K 토큰 초과 시 0.50/2.50) · Sonnet 5.5 `claude-sonnet-5-5` 2/10 · Opus 5.5 `claude-opus-5-5` 4/20. 컨텍스트 1M, 최대 출력 128K. Haiku 5.5 는 2026-10-07 출시, 기본 effort `medium`, 어댑티브 thinking 기본 켜짐(thinking 토큰도 출력으로 과금).
- 구조화 출력: GA, 베타 헤더 없음. `output_config.format = {type: "json_schema", ...}`; Python 은 `client.messages.parse(...)` 로 Pydantic 모델 검증. 5.5 세대는 assistant prefill 과 강제 `tool_choice` 가 400 — JSON 은 구조화 출력으로만.
- 프롬프트 캐싱: 최소 **512 토큰**(미만이면 조용히 캐시 안 됨), 읽기 0.1x(5.5 세대 0.05x), 기본 TTL 5분. 하루 2회 호출은 TTL 밖이다.
- Message Batches: 50% 할인, 대부분 1시간 내, 24시간 만료.
- 요율: Start 티어 모델당 1,000 RPM / 2M ITPM. 신규 조직은 Evaluation 티어로 시작할 수 있음. 무료 크레딧·최소 충전액은 공식 문서에서 확인 못 함.
- 한국어: 공식 다국어 벤치는 4.5 세대 수치만(Sonnet 4.5 한국어 = 영어 대비 96.7%). 글자당 토큰 공식 수치 없음. 서드파티 측정은 구 토크나이저에서 한국어 약 1.06 토큰/글자, 신형 토크나이저는 "같은 텍스트가 약 30% 더 많은 토큰"(Haiku 5.5 문서).
- 출처: platform.claude.com/docs/en/models/overview, …/about-claude/pricing, …/build-with-claude/structured-outputs, …/prompt-caching, …/batch-processing, …/api/rate-limits, …/multilingual-support, pypi.org/pypi/anthropic/json.

### 옵션 B — OpenAI 소형 모델 (비교용)
- `gpt-5.4-nano` 0.20/1.25, `gpt-5.4-mini` 0.75/4.50, `gpt-5-nano` 0.05/0.40 ($/1M). 캐시 입력 10%, 배치 약 50%. Structured Outputs: `text.format = {type: "json_schema", strict: true}`. 출처: developers.openai.com/api/docs/pricing, …/guides/structured-outputs.

### 옵션 C — 로컬 (Ollama)
- 공식 라이브러리에 `exaone3.5`(2.4b/7.8b/32b), `exaone-deep`(2.4b 1.6GB / 7.8b 4.8GB / 32b 19GB), `qwen3`(0.6b~32b, 4b 2.5GB·8b 5.2GB). EXAONE 4.0 은 커뮤니티 업로드만. 하드웨어 요구는 공식 README 에 없음 → 확인 못 함. 이 PC(노트북, 사양 미확인)에서의 속도·품질은 PoC 없이는 모른다.

### 비용 추정 (가정 명시, `count_tokens` 로 검증 가능)
- 입력: 80건 × (한글 60자 → 60~84 토큰 + 영문 200자 → 50~80 토큰) ≈ 8,800~13,100 + 시스템 프롬프트·스키마 1,000~2,000 ⇒ **호출당 약 10K~15K 토큰**. 출력: 한국어 1,600자 ≈ 1,600~2,240 토큰 + 선정 JSON 300~500 ⇒ **약 2,000~2,700 토큰** (thinking 토큰 제외).
- 호출당·월(2회/일 × 30일 = 60회) 상한값 기준, thinking 제외:

| 모델 | 호출당 | 월 |
|---|---|---|
| Haiku 5.5 | 15K×0.10 + 2.7K×0.50 ≈ **$0.003** | ≈ $0.17 |
| Sonnet 5.5 | 15K×2 + 2.7K×10 ≈ **$0.057** | ≈ $3.4 |
| Opus 5.5 | 15K×4 + 2.7K×20 ≈ **$0.114** | ≈ $6.8 |
| gpt-5.4-nano | 15K×0.20 + 2.7K×1.25 ≈ $0.006 | ≈ $0.38 |

## 트레이드오프 (사실만. 판단은 분석 단계)
| 항목 | A: Claude API | B: OpenAI | C: 로컬 Ollama |
|---|---|---|---|
| 구현 비용 | SDK 1개 추가, 키 1개(`SecretStr`), 구조화 출력 내장 | 동일 수준 | 모델 설치·상주 프로세스·PC 사양 확인. 노트북이 잠들면 못 돈다(로컬 스케줄 분석과 같은 제약) |
| 운영 비용 | 월 $0.2(Haiku)~$7(Opus), 하루 2회 | 월 $0.4~ | 전기·디스크. API 비용 0 |
| 한국어 품질 근거 | 공식 벤치(4.5 세대) 있음 | 공식 한국어 수치 확인 못 함 | EXAONE 은 한국어 특화 모델. 수치 확인 못 함 |
| 구조화 출력 | GA, Pydantic 검증 | GA | 모델·런타임 의존 |
| 외부 전송 | 제목·리드가 외부 API 로 나간다 | 동일 | 나가지 않는다 |
| 되돌리기 | 뉴스 섹션이 required 가 아니므로 단계 제거 시 v0 목록으로 복귀 | 동일 | 동일 |

## 확인 못 한 것
- [ ] 세 언론사 약관의 "AI 학습" 조항이 **추론 입력(요약 생성)**에도 미치는지. 문면에는 학습만 있다. 법적 판단은 이 프로젝트 범위 밖이고, 사용자가 정할 일이다.
- [ ] 연합뉴스 "비상업적 블로그·개인 용도" 안에 "본인+소수 지인 무료 메일"이 드는지(문면상 개인 용도에 가까우나 단정 못 함).
- [ ] 제목 + 100자 리드만으로 "흐름 요약"이 실제로 되는지 — **PoC 없이는 모른다.** 2026-10-07 분석도 "PoC 에서 본다"고 적었다.
- [ ] Anthropic 신규 조직의 Evaluation 티어 한도와 최소 충전액.
- [ ] 한국어 글자당 토큰(신형 토크나이저) — `count_tokens` 로 실측하면 끝난다.
- [ ] 이 노트북 사양(RAM·GPU) — 옵션 C 의 전제.
- [ ] 테스트에서 SDK 호출을 어떻게 가짜로 대체할지(인터페이스 분리 vs SDK 의 테스트 수단).

## 열린 질문 → 분석 단계로
- [ ] **출력의 모양**: (a) 선별 N건 + 건별 한 줄 한국어 요약 + 원문 링크, (b) 흐름 요약 문단 + 근거 링크 목록, (c) 둘 다. 지침은 "제목+첫 한두 줄+링크"는 무방, "단순 축약"은 위험, "총괄적 뜻만 살린 새 문장"은 다르다고 한다.
- [ ] **입력 범위**: 80건 전부 vs 출처별 상한을 더 낮춘 뒤; DART 공시 포함 여부; 연합 머리말 제거 여부; 영문 기사의 한국어 요약 여부.
- [ ] **모델·effort**: Haiku/Sonnet/Opus 5.5 중 무엇으로 시작하고, 품질을 무엇으로 판정할 것인가(샘플 눈검사 vs 기준표).
- [ ] **실패 시**: 호출 실패·타임아웃·거부(`stop_reason=refusal`)·스키마 불일치 때 v0 목록으로 내려가는가, 섹션을 비우는가. 뉴스 섹션은 required 가 아니라 메일 자체는 간다.
- [ ] **끼어들 자리**: `collect` 와 `compose` 사이의 별도 단계(스냅샷에 요약을 붙임) vs `compose` 안의 "LLM 작성기"(플랜이 적어 둔 그림).
- [ ] **약관 결론**: 위 "확인 못 한 것" 1·2 를 어떻게 다룰지. 출처를 연합(개인 용도 허용 명시)으로 좁히는 선택지, 제목만 입력하는 선택지가 사실로서 존재한다.
- [ ] **PoC 범위**: 실제 80건 하루치로 (a)(b) 를 한 번씩 만들어 보고 길이·사실성·중복을 본다. `count_tokens` 로 비용도 실측.

## 참고
- [Models overview](https://platform.claude.com/docs/en/models/overview) — 모델 ID·컨텍스트·토큰 환산
- [Pricing](https://platform.claude.com/docs/en/about-claude/pricing) — 단가, 캐시·배치 배수
- [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) — `output_config.format`, `messages.parse`
- [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) — 최소 512 토큰, TTL
- [Rate limits](https://platform.claude.com/docs/en/api/rate-limits) — 티어
- [anthropic on PyPI](https://pypi.org/pypi/anthropic/json) — 1.13.0
- [OpenAI pricing](https://developers.openai.com/api/docs/pricing) — 비교용
- [Ollama exaone-deep](https://ollama.com/library/exaone-deep), [qwen3](https://ollama.com/library/qwen3) — 로컬 옵션
- 한국경제 이용약관 https://id.hankyung.com/user/selectAuthAgree.do · 매일경제 https://www.mk.co.kr/mypage/policy · 연합뉴스 RSS https://www.yna.co.kr/rss/index, 저작권규약 https://www.yna.co.kr/policy/copyright · Marketaux ToS https://www.marketaux.com/tos
- 한국저작권보호원 2020 자체점검 지침서 p.134 https://www.kcopa.or.kr/download.do?uuid=8641e73c-2d58-4b95-8f64-b0b21bfbfaea.pdf · KPF FAQ https://www.kpf.or.kr/front/faq/faqListPage.do?faq_type=K
- [[2026-10-07_data-sources]] (리서치·분석) — 네이버 제외, "본문을 옮기지 않는다" 전제
- [[2026-10-07_news-rss]], [[2026-10-07_collect-service]], [[2026-10-08_run-briefing]] — 실측·상한·v0 결정
