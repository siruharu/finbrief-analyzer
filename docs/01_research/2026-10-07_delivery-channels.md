---
type: research
project: finbrief-analyzer
topic: 발송 채널 (메일·문자·카카오톡)
created: 2026-10-07
status: draft        # draft | done
tags: [research, delivery, email, sms, kakaotalk]
next: analysis
---

# 🔍 발송 채널 (메일·문자·카카오톡)

> **핵심 질문** — 메일·SMS·카카오톡으로 브리핑을 보내는 수단으로 무엇이 있고, 각각의 비용·사전 심사·법적 요건은 무엇인가?

## 배경
finbrief-analyzer 가 만든 일일 브리핑(하루 1회, 시세·뉴스 요약 텍스트)을 한국 구독자에게 전달할 채널이 필요하다.
발송 주체는 AWS ECS on EC2(ap-northeast-2) 위의 Python 서버다.
데이터 출처는 별도 노트 [2026-10-07_data-sources.md](2026-10-07_data-sources.md).

표기: ✅ = 메인 세션에서 원문 직접 확인(2026-10-07), 표기 없음 = 서브에이전트 요약 기준.
원화 단가는 VAT 미포함.

## 코드베이스 안에 이미 있는 것
| 위치 | 하는 일 | 재사용 가능? |
|---|---|---|
| `src/finbrief_analyzer/` 전체 | 발송·스케줄링 코드 없음. smtplib·boto3·kakao·sns·ses 문자열 0건 | 해당 없음 |
| `pyproject.toml:6-19` | boto3·HTTP 클라이언트(런타임)·스케줄러 의존성 없음. `httpx` 는 dev 그룹에만 | — |
| `deploy/terraform/service/iam.tf:45-49` | 태스크 역할(`${name}-task`)은 역할만 있고 붙은 정책 없음 ("필요한 권한만 여기에 붙인다" 주석) | AWS 발송 권한을 붙일 자리 |
| `deploy/terraform/service/variables.tf:75-76`, `main.tf:83` | `secrets` 맵 → 컨테이너 `secrets.valueFrom` (SSM/Secrets Manager) | 발송 API 키 주입 경로 |
| `deploy/terraform/service/` 전체 | SES/SNS/SQS 리소스 없음. SNS 는 알람용 외부 토픽 ARN 변수뿐(`variables.tf:137`, `observe.tf:18`) | — |
| `deploy/terraform/service/main.tf:25-203` | EventBridge/Scheduler/cron 리소스 없음 | 일 1회 발송 트리거는 없음 |
| `compose.yml:8-73` | mailhog 등 메일·SMS 목 서비스 없음. mq(rabbitmq:4)·cache(redis:8) 프로파일은 있음 | — |
| `CLAUDE.md` 인프라 절 | 태스크는 항상 2개 이상 동시 실행, 스케줄 잠금은 컨테이너 밖(DB·Redis)에 둔다는 규칙 | 중복 발송과 관련된 기존 제약 |

git 이력은 템플릿 초기화 커밋 1건(`b87d142`)뿐이라 과거에 시도했다 접은 방식은 없다.

## 외부 조사

### 메일

| 옵션 | 무료 한도 | 요금 | 비고 | 출처 |
|---|---|---|---|---|
| A1 Amazon SES ✅ | 전용 무료 한도 표기 없음. "신규 AWS 고객은 최대 200 USD 의 AWS 프리 티어 크레딧" | Essentials 1,000통당 0.16 USD(월 0~1,000만 통, 고정료 없음), Pro 0.22 USD + 월 105 USD, Enterprise 0.23 USD + 월 500 USD | 2026-07-21 부터 신규 계정은 Essentials 로 시작(서브에이전트 확인) | [요금](https://aws.amazon.com/ko/ses/pricing/) |
| A2 SendGrid | 체험 60일·일 100통 | Essentials 월 19.95 USD~, Pro 월 89.95 USD~ | | [요금](https://www.twilio.com/en-us/products/email-api/pricing) |
| A3 Mailgun | 일 100통 | Basic 월 15 USD/1만 통, Foundation 월 35 USD/5만 통, Scale 월 90 USD/10만 통 | | [요금](https://www.mailgun.com/pricing/) |
| A4 Resend | 월 3,000통·일 100통·도메인 3개 | Pro 월 20 USD/5만 통 | | [요금](https://resend.com/pricing) |
| A5 스티비 | 스타터 무료: 구독자 ~500명, 발송 월 2회 | 유료 금액·API 포함 플랜 확인 못 함 | | [요금](https://stibee.com/pricing) |
| A6 NHN Cloud Email | 확인 못 함 | 확인 못 함 | | — |

**SES 세부**
- 서울 리전: 2020-07 발표 제목에 Seoul 포함 (제목만 확인, 본문 미열람). https://aws.amazon.com/about-aws/whats-new/2020/07/amazon-ses-available-ohio-singapore-tokyo-seoul-regions
- 샌드박스: 신규 계정은 리전별 샌드박스 — 검증된 주소로만, 24시간 200통, 초당 1통. 콘솔 또는 `aws sesv2 put-account-details --production-access-enabled` 로 신청, "initial response within 24 hours". https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html
- 인증: "to comply with DMARC, messages must be authenticated through either SPF or DKIM". SPF 는 custom MAIL FROM 도메인 기준. https://docs.aws.amazon.com/ses/latest/dg/send-email-authentication-dmarc.html

**수신 측 대량 발신자 요건**
- Gmail: 전 발신자 SPF 또는 DKIM. 일 5,000통 이상은 SPF+DKIM+DMARC, From 도메인 정렬, 마케팅·수신동의 메일 원클릭 수신거부(`List-Unsubscribe-Post: List-Unsubscribe=One-Click`), 스팸률 0.1% 미만 유지·0.3% 넘지 않게. https://support.google.com/a/answer/81126?hl=ko
- Yahoo: SPF+DKIM, DMARC 최소 p=none, list-unsubscribe(RFC 8058 권장), 수신거부 2일 내 반영, 스팸률 0.3% 미만. https://senders.yahooinc.com/best-practices/

### 문자 (SMS/LMS)

| 옵션 | 단가 | 가입·제약 | 출처 |
|---|---|---|---|
| B1 Solapi ✅ | SMS 18원(EUC-KR 90바이트), LMS 45원(2,000바이트), MMS 110원. "단가는 모두 VAT미포함" | 개인·사업자 계정 모두 존재. ARS 인증 + 명의확인, 계정당 발신번호 5개. 월 기본료 없음, 발송 API 5초당 100회(서브에이전트 확인) | [요금](https://solapi.com/pricing) · [발신번호](https://solapi.com/guides/senderid) |
| B2 알리고 | "대한민국 최저가 8.4원"(문자). LMS 단가 확인 못 함 | "회원가입만 하면 바로 연동". 사업자 요건 확인 못 함 | [사이트](https://smartsms.aligo.in/) · [API](https://smartsms.aligo.in/smsapi.html) |
| B3 네이버 클라우드 SENS | 확인 못 함 | 2026-09-17 Cloud Outbound Mailer 와 통합. SMS/LMS/MMS·알림톡·브랜드 메시지·이메일 제공 | [개요](https://guide.ncloud-docs.com/docs/sens-overview) |
| B4 NHN Cloud SMS | 확인 못 함 | 확인 못 함 | — |
| B5 AWS End User Messaging ✅ | 한국행 건당 단가 확인 못 함 | South Korea(KR): short code No, long code No, Sender ID No, two-way No, International sending Yes | [국가별 지원](https://docs.aws.amazon.com/sms-voice/latest/userguide/phone-numbers-sms-by-country.html) |
| B6 Twilio | 세그먼트당 0.0524 USD | 장문 연결 미지원(분할 표시), 세그먼트 140바이트(UCS2 70자), 영숫자 Sender ID 미지원, 양방향 불가, "[Web 발신]"/"[국제발신]" 자동 부착, 발신번호 앞 009/006 부착 | [요금](https://www.twilio.com/en-us/sms/pricing/kr) · [가이드](https://www.twilio.com/en-us/guidelines/kr/sms) |

**발신번호 사전등록**: 전기통신사업법 제84조의2 — 거짓표시 번호 발신 차단 등 사업자 조치 의무. 2015-10-16 시행, "인터넷으로 발송되는 모든 문자 메시지는 사전에 등록된 발신번호만"(Solapi 설명). https://www.law.go.kr/법령/전기통신사업법/제84조의2 , https://solapi.com/guides/senderid

### 카카오톡

#### 옵션 C1 — 알림톡
- 버전: 해당 없음 (카카오 비즈니스 가이드, 2026-10-07 열람)
- 요약: 채널을 추가하지 않은 이용자에게도 보낼 수 있는 정보성 메시지. 카카오가 승인한 템플릿만 발송 가능, 심사 영업일 2일 이내. "메시지의 전부 또는 일부에 광고성 내용이 포함된 경우 발송이 불가". 비즈니스 채널 전환·홈공개 ON·고객센터 정보가 선행 조건. 공식 딜러사 경유.
- 발송 예시 문구 ✅: "✅금전적 대가를 지불하고 신청한 정보만 발송 가능(뉴스레터, 축산물 거래정보 등)", "❌ 무료 뉴스레터 등 무료 구독형 메시지 불가 (브랜드 메시지 사용 권장)", "❌비 제도권금융회사에서 발송하는 주식 종목 추천 메시지 발송 불가". 금융 항목에 증권사의 지수·환율 정보 제공 예시("[OO증권] 국내지수알리미")가 있음.
- 단가 ✅: Solapi 기준 13원 (한글/영어 1,000자, 버튼 5개). 알리고 표기 6.5원(서브에이전트 확인). 카카오는 "딜러사별 단가 상이"만 명시.
- 출처: https://kakaobusiness.gitbook.io/main/ad/infotalk , https://kakaobusiness.gitbook.io/main/ad/infotalk/audit , https://kakaobusiness.gitbook.io/main/ad/infotalk/send-example , https://solapi.com/pricing

#### 옵션 C2 — 브랜드 메시지 (구 친구톡)
- 버전: 해당 없음
- 요약: 채널 친구 + 광고성 정보 수신동의 유저 대상 광고 메시지. (광고) 표시·수신거부 표시, 발송 가능 08:00~20:50. 친구톡은 ✅ "2025.12.31 서비스종료", "친구톡 발송 시 모두 브랜드 메시지 자유형으로 전환 발송"(Solapi 표기).
- 단가 ✅: Solapi 기준 텍스트 53원(1,000자), 이미지 83원, 와이드 88원, 자유형 100원, 프리미엄 103원.
- 출처: https://kakaobusiness.gitbook.io/main/ad/brandmessage , https://solapi.com/pricing

#### 옵션 C3 — 카카오톡 메시지 API (나에게 보내기 / 친구에게 보내기)
- 버전: REST API v2 (`/v2/api/talk/memo/...`)
- 요약: "같은 서비스 내 사용자간 메시지 발송만 지원", 용도는 "서로간 상호작용 목적". 나에게 보내기는 카카오 로그인 + `talk_message` 동의항목. 친구에게 보내기는 비즈 앱 전환 → 비즈니스 정보 심사 → 추가 기능 신청, 1회 최대 5명. 쿼터: 일 30,000건, 발신자당 100건, 수신자당 100건, 발신자/수신자 pair 당 20건.
- 출처: https://developers.kakao.com/docs/latest/ko/kakaotalk-message/common , https://developers.kakao.com/docs/latest/ko/kakaotalk-message/rest-api , https://developers.kakao.com/docs/latest/ko/getting-started/quota

**채널·사업자 요건**: 사업자등록번호·고유번호가 없어도 일반 채널은 개설 가능('사업자 정보가 확인되지 않은 채널' 문구 노출). 비즈니스 채널 전환 서류는 개인사업자 대표=카카오톡 전자증명서, 법인 대표=사업자등록증+본인인증. 공식 딜러사 목록에 NHN Cloud·다우기술·비즈톡·스윗트래커 등 (열람 범위에 Solapi·네이버클라우드 이름은 없었음). https://kakaobusiness.gitbook.io/main/channel/start

### 법적 요건 (정보통신망법)
- 제50조: ① 수신자의 명시적 사전 동의 ② 수신거부·동의 철회 시 전송 금지 ③ 오후 9시~다음 날 오전 8시는 별도 사전 동의(시행령 제61조②: 전자우편은 제외 매체) ④ 전송자 명칭·연락처, 수신거부 방법 명시(세부는 시행령 별표 6) ⑥ 수신거부 비용 수신자 미부담 ⑦ 동의·거부 처리 결과 통지 ⑧ 정기적 수신동의 확인. https://www.law.go.kr/법령/정보통신망이용촉진및정보보호등에관한법률/제50조 , https://www.law.go.kr/법령/정보통신망이용촉진및정보보호등에관한법률시행령/제61조
- 시행령 제62조의3: 수신동의 받은 날부터 2년마다 확인. https://www.law.go.kr/법령/정보통신망이용촉진및정보보호등에관한법률시행령/제62조의3
- 안내서 인용(카카오 심사 가이드에 실린 문구): 수신자의 요청·신청에 따른 정보는 예외이나 "다른 재화 및 서비스에 대한 홍보가 포함되거나, 수신자의 추가 요청이 없음에도 반복적으로 정보를 발송하는 경우 영리목적의 광고성 정보 전송에 해당". https://kakaobusiness.gitbook.io/main/ad/infotalk/audit
- 보조(딜러사 안내, 공식 아님): 광고성 예시에 "사업자가 발송하는 뉴스레터" 포함, "최종 판단은 메시지 내용 및 발송 목적에 따라 달라질 수 있음". https://solapi.com/guides/sms-ad-guide

## 겹치는 것 · 엇갈리는 것
- **겹침**: 문자·알림톡·브랜드 메시지는 모두 사전 등록·심사 단계가 있다(발신번호 등록, 템플릿 심사, 비즈니스 채널 전환). 메일은 도메인 인증과 SES 샌드박스 해제가 그에 해당한다.
- **겹침**: 알림톡 발송 예시와 Solapi 단가는 서브에이전트 보고와 메인 세션 원문 확인이 일치했다.
- **엇갈림**: 알림톡 단가 — Solapi 13원, 알리고 6.5원. 문자 단가 — Solapi SMS 18원, 알리고 8.4원(어떤 유형의 단가인지 페이지 문구만으로는 미확정).
- **엇갈림**: 공식 딜러사 — 카카오 가이드의 열람 범위에는 Solapi·네이버클라우드 이름이 없었으나, Solapi·SENS 는 알림톡·브랜드 메시지를 상품으로 제공한다. 재판매 구조인지는 확인 못 함.
- **엇갈림**: 구독형 뉴스레터의 광고성 해당 여부 — 카카오 가이드는 "유료로 신청한 정보"만 알림톡 가능·무료 구독형은 불가로 구분하고, 딜러사 안내는 "사업자가 발송하는 뉴스레터"를 광고성 예시로 든다. KISA 안내서 원문은 직접 보지 못했다.

## 트레이드오프 (사실만. 판단은 분석 단계)
| 항목 | 메일 (SES 기준) | 문자 (Solapi 기준) | 알림톡 | 브랜드 메시지 | 카카오톡 메시지 API |
|---|---|---|---|---|---|
| 건당 비용 | 약 0.00016 USD | SMS 18원 / LMS 45원 | 13원 | 텍스트 53원 | 과금 표기 확인 못 함 |
| 길이 제한 | 확인 못 함 | 90바이트 / 2,000바이트 | 1,000자 | 1,000자 | 확인 못 함 |
| 사전 절차 | 도메인 인증, 샌드박스 해제(24시간 내 1차 응답) | 발신번호 등록(ARS+명의확인) | 비즈니스 채널 전환 + 템플릿 심사(영업일 2일) | 비즈니스 채널 전환, 친구+광고 수신동의 | 카카오 로그인 동의, 친구 발송은 비즈 앱 심사 |
| 사업자등록 | 요건 표기 확인 못 함 | 개인 계정 존재 | 필요(비즈니스 채널) | 필요(비즈니스 채널) | 나에게 보내기는 불필요, 친구 발송은 비즈 앱 |
| 내용 제약 | 대량 발신 시 원클릭 수신거부 | 광고성이면 (광고) 표기·수신거부 | 고정 템플릿, 광고성 불가, 무료 구독형 불가 | 광고 표기, 08:00~20:50 | 같은 서비스 사용자 간, 1회 5명, pair 당 일 20건 |
| 야간 제한(21~08시) | 전자우편은 제외 매체 | 광고성이면 별도 동의 | 확인 못 함 | 20:50 까지 | 확인 못 함 |
| 구현 비용 | boto3 + IAM 정책 + DNS 레코드 | REST API + 키 | 딜러사 API + 템플릿 등록 | 딜러사 API | OAuth 토큰 관리 |
| 되돌리기 난이도 | 확인 못 함 | 확인 못 함 | 확인 못 함 | 확인 못 함 | 확인 못 함 |

## 확인 못 한 것
- [ ] NHN Cloud SMS·Email·카카오 비즈메시지 단가 (요금 페이지 본문 미렌더)
- [ ] 네이버 클라우드 SENS 단가·무료 제공량
- [ ] AWS End User Messaging / SNS 의 한국행 SMS 건당 단가
- [ ] 알리고 LMS 단가, 알리고·NHN·SENS 가입 시 사업자 요건
- [ ] 스티비 유료 요금·API 제공 플랜
- [ ] SES 서울 리전 지원 (발표 제목만 확인), 현재 리전별 기능 차이
- [ ] KISA/방통위 「불법스팸 방지를 위한 정보통신망법 안내서」 원문 — 뉴스레터의 광고성 해당 여부에 대한 공식 문구
- [ ] 시행령 별표 6 ((광고) 표기 세부) 원문, 과기정통부 발신번호 거짓표시 관련 고시 원문
- [ ] 카카오 공식 단가표, 브랜드 메시지의 친구/비친구 차등 단가
- [ ] 카카오톡 메시지 API 약관 문구 (메인 세션에서 원문 재확인 못 함 — 서브에이전트 인용 기준), "나에게 보내기"에 일간 쿼터가 동일 적용되는지
- [ ] 알림톡의 야간 발송 제한 여부
- [ ] Solapi·SENS 가 카카오 공식 딜러사인지 재판매사인지

## 열린 질문 → 분석 단계로
- [ ] 운영 주체가 사업자등록을 갖고 있는가? (비즈니스 채널·알림톡·브랜드 메시지의 선행 조건)
- [ ] 구독이 유료인가 무료인가? (알림톡 발송 예시의 "유료 정보 신청" / "무료 구독형 불가" 구분)
- [ ] 수신자가 본인·소수 지인인가 불특정 다수 구독자인가? (카카오톡 메시지 API 의 5명·pair 당 20건 제약, 수신동의 관리 범위)
- [ ] 예상 구독자 수와 월 발송 건수는? (채널별 월 비용 산정의 입력)
- [ ] 브리핑 길이는 얼마인가? (SMS 90바이트 / LMS 2,000바이트 / 알림톡 1,000자 안에 들어가는가, 본문은 링크로 넘기는가)
- [ ] 발송 시각은 언제인가? (장 마감 후 저녁이면 21시 야간 제한·브랜드 메시지 20:50 과 맞닿는다)
- [ ] 브리핑이 "광고성 정보"에 해당하는가? — 공식 안내서 원문 확인 또는 전문가 확인이 필요한 지점
- [ ] 수신동의·수신거부·2년 재확인 이력을 어디에 저장하는가? (컨테이너 밖 저장 규칙)
- [ ] 태스크가 2개 이상 동시에 도는 구조에서 일 1회 발송 트리거와 중복 발송 방지를 어디에 두는가?
- [ ] 채널을 하나로 시작하는가, 여러 채널을 동시에 지원하는가?

## 참고
- [Amazon SES 요금](https://aws.amazon.com/ko/ses/pricing/) — Essentials 1,000통당 0.16 USD
- [SES 프로덕션 액세스 요청](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html) — 샌드박스 한도와 해제 절차
- [Gmail 발신자 가이드라인](https://support.google.com/a/answer/81126?hl=ko) — 일 5,000통 이상 요건
- [Solapi 요금](https://solapi.com/pricing) — 문자·알림톡·브랜드 메시지 단가
- [AWS End User Messaging 국가별 지원](https://docs.aws.amazon.com/sms-voice/latest/userguide/phone-numbers-sms-by-country.html) — 한국은 국제 발신만
- [알림톡 발송 예시](https://kakaobusiness.gitbook.io/main/ad/infotalk/send-example) — 유료 정보·무료 구독형·금융 항목
- [알림톡 심사 가이드](https://kakaobusiness.gitbook.io/main/ad/infotalk/audit) — 정보성 메시지 기준
- [카카오톡 메시지 API](https://developers.kakao.com/docs/latest/ko/kakaotalk-message/common) — 용도·권한
- [정보통신망법 제50조](https://www.law.go.kr/법령/정보통신망이용촉진및정보보호등에관한법률/제50조) — 광고성 정보 전송 제한
