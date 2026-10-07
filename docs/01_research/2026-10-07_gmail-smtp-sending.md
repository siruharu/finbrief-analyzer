---
type: research
project: finbrief-analyzer
topic: 개인 Gmail 계정으로 직접 발송 (SMTP)
created: 2026-10-07
status: draft        # draft | done
tags: [research, delivery, email, gmail, smtp]
next: analysis
---

# 🔍 개인 Gmail 계정으로 직접 발송 (SMTP)

> **핵심 질문** — 발신 도메인 없이, 개인 Gmail 계정으로 서버에서 브리핑 메일을 자동 발송하는 방법으로 무엇이 있고 각각의 조건·한도·제약은 무엇인가?

## 배경
[2026-10-07_delivery-channels.md](2026-10-07_delivery-channels.md) 의 분석은 "발신 도메인이 있거나 마련할 수 있다"를 전제로 Amazon SES 를 골랐다.
사용자가 발신 도메인이 없다고 답해(2026-10-07) 그 전제가 깨졌다. 도메인을 사지 않는 대안으로 개인 Gmail 직접 발송을 조사한다.
조건: 개인 @gmail.com 계정(Workspace 아님), 하루 2회, 본인과 지인 10명 이하, 발송 주체는 AWS ECS(프라이빗 서브넷 + NAT).

표기: ✅ = 메인 세션에서 원문 직접 확인(2026-10-07), 표기 없음 = 서브에이전트 요약 기준.

## 코드베이스 안에 이미 있는 것
| 위치 | 하는 일 | 재사용 가능? |
|---|---|---|
| `src/finbrief_analyzer/` 전체 | 메일 발송 코드 없음 | 해당 없음 |
| `deploy/terraform/service/variables.tf:75-76`, `main.tf:83` | `secrets` 맵 → 컨테이너 `secrets.valueFrom` (SSM/Secrets Manager) | 앱 비밀번호 주입 경로 |
| `deploy/terraform/platform/cluster.tf:75-79` | 호스트 SG egress 0.0.0.0/0 전 프로토콜 | 587 아웃바운드가 SG 에서 막히지 않음 |
| `docs/03_plan/2026-10-07_delivery-channels.md` | `Notifier` 인터페이스 뒤에 채널을 두는 계획 | 발송 수단만 교체 가능 |

## 외부 조사

### 옵션 A — SMTP + 앱 비밀번호
- 버전: Python 표준 라이브러리 `smtplib` (문서 3.14 기준). 비동기 대안 aiosmtplib 5.1.3 (2026-09-08)
- 요약
  - 서버 `smtp.gmail.com`, "Port for TLS/STARTTLS: 587", 인증 필요. 개인 계정 도움말에는 465 가 없다(465 는 Workspace 문서에만 있음).
  - ✅ 앱 비밀번호 발급 조건: "To create an app password, you need 2-Step Verification on your Google Account."
  - ✅ 발급 옵션이 안 보이는 경우: 2단계 인증이 보안 키 전용, 직장·학교 계정, 고급 보호 계정.
  - ✅ "App passwords aren't recommended and are unnecessary in most cases."
  - ✅ "we revoke your app passwords when you change your Google Account password."
  - 폐지 날짜 공지는 도움말에 없다.
  - Python 공식 예제가 `EmailMessage` + `smtplib.SMTP(...).send_message(msg)` 조합이다.
- 출처: https://support.google.com/mail/answer/7104828?hl=en , https://support.google.com/accounts/answer/185833?hl=en , https://docs.python.org/3/library/smtplib.html , https://docs.python.org/3/library/email.examples.html , https://pypi.org/project/aiosmtplib/

### 옵션 B — Gmail API (`messages.send`) + OAuth 2.0
- 버전: Gmail API v1
- 요약
  - `gmail.send` 스코프는 Sensitive 로 분류된다. "personal use (fewer than 100 users)" 앱은 검증이 필요 없지만 미검증 경고 화면이 뜬다.
  - 동의 화면이 External + "Testing" 상태면 refresh token 이 **7일 뒤 만료**된다. Production 으로 올리면 미검증 경고와 신규 사용자 100명 상한이 있다.
  - Gmail 스코프 토큰은 비밀번호 변경 시 무효가 된다.
  - 쿼터: `messages.send` 1회 100 유닛, 사용자당 분당 6,000 유닛.
- 출처: https://developers.google.com/identity/protocols/oauth2 , https://developers.google.com/workspace/gmail/api/auth/scopes , https://support.google.com/cloud/answer/13464323?hl=en , https://support.google.com/cloud/answer/15549945?hl=en , https://developers.google.com/workspace/gmail/api/reference/quota

### 옵션 C — SMTP + XOAUTH2
- 버전: 해당 없음
- 요약: 필요한 스코프가 `https://mail.google.com/` 이고 Restricted 로 분류된다(서버 저장·전송 시 보안 평가 대상). `smtplib` 의 `auth()` 로 커스텀 메커니즘을 구현할 수 있다.
- 출처: https://developers.google.com/workspace/gmail/imap/xoauth2-protocol , https://developers.google.com/workspace/gmail/api/auth/scopes

### 공통 사실
- **발송 한도** ✅: 개인 Gmail 은 "more than 500 recipients in a single email and or more than 500 emails sent in a day" 이면 제한되고, "you should be able to send emails again within 1 to 24 hours". SMTP 와 웹 발송의 구분은 이 페이지에 없다. https://support.google.com/mail/answer/22839?hl=en
- **Gmail 프로그램 정책**: "Don't use Gmail to distribute spam or unsolicited commercial mail." / "You are not allowed to automate the Gmail interface, whether to send, delete, or filter emails, in a manner that misleads or deceives users." 위반 시 접근 제한 또는 계정 비활성화 가능. https://support.google.com/mail/answer/16734397
- **AWS 아웃바운드** ✅: "By default, Amazon EC2 allows outbound traffic over port 25 only to private IPv4 addresses." 이 문서의 제한 대상은 25 뿐이고 587·465 는 언급되지 않는다. https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html
- **새 위치 로그인**: 평소와 다른 위치·기기의 로그인 시도는 차단될 수 있고 "Suspicious sign in prevented" 메일이 온다. 서드파티 로그인 차단 사유에 "You're signing in from a new location or device" 가 있고, 안내된 조치는 익숙한 기기·위치에서 재시도하거나 약 1주 뒤 재시도. https://support.google.com/accounts/answer/6063333?hl=en , https://support.google.com/accounts/answer/9279980?hl=en
- **Gmail 밖에서 @gmail.com 발신**: 발신자 가이드라인에 "Don't impersonate Gmail From: headers. Gmail will begin using a DMARC quarantine enforcement policy". Gmail 서버를 거치지 않고 @gmail.com 을 From 으로 쓰는 경우에 대한 문구다(= SES 에 개인 Gmail 주소를 발신자로 검증하는 방식에 해당). https://support.google.com/mail/answer/81126?hl=en

## 겹치는 것 · 엇갈리는 것
- **겹침**: 세 옵션 모두 Google 계정 비밀번호를 바꾸면 인증 수단(앱 비밀번호 또는 토큰)이 무효가 된다.
- **엇갈림**: 앱 비밀번호는 현재 발급·사용이 가능하지만 Google 은 "권장하지 않는다"고 적는다. 폐지 일정은 공지돼 있지 않다.
- **엇갈림**: 포트 465 — Workspace 문서에는 있고 개인 계정 도움말에는 없다.
- 한도(일 500통)와 예상 사용량(하루 2회 × 10명 이하 = 20통 이하)의 차이는 25배 이상이다.

## 트레이드오프 (사실만. 판단은 분석 단계)
| 항목 | A: SMTP + 앱 비밀번호 | B: Gmail API + OAuth | C: SMTP + XOAUTH2 | (참고) 도메인 구입 + SES |
|---|---|---|---|---|
| 구현 비용 | 표준 라이브러리만. 비밀값 1개 | Google Cloud 프로젝트·동의 화면·최초 브라우저 동의·토큰 갱신 | B 와 같고 SMTP 커스텀 인증 추가 | boto3 + DNS 레코드 + terraform |
| 운영 비용 | 없음 | 없음 | 없음 | 도메인 연 비용 + 1,000통당 0.16 USD |
| 인증 수명 | 비밀번호 변경 전까지 | Testing 상태면 7일. Production 이면 미검증 경고 | B 와 같음 | 태스크 역할 (만료 없음) |
| 스코프 분류 | 해당 없음 (계정 전체 메일 접근 권한) | Sensitive | Restricted | 해당 없음 |
| 발송 한도 | 일 500통 | 일 500통 (계정 한도) | 일 500통 | 샌드박스 24시간 200통 |
| 알려진 제약 | 새 위치 로그인 차단 가능, "권장하지 않음" | 7일 만료 또는 미검증 경고 | Restricted 스코프 | 수신자별 주소 검증(샌드박스) |
| 되돌리기 난이도 | 확인 못 함 | 확인 못 함 | 확인 못 함 | 확인 못 함 |

## 확인 못 한 것
- [ ] 클라우드(데이터센터) IP 에서 앱 비밀번호로 SMTP 로그인할 때의 차단 여부에 대한 공식 안내 — 일반적인 "새 위치·기기" 안내만 확인
- [ ] smtp.gmail.com 으로 보낸 개인 Gmail 메일이 gmail.com 의 SPF·DKIM 을 통과한다는 공식 명시 문구
- [ ] 개인 계정의 "보안 수준이 낮은 앱" 종료 날짜의 공식 출처 (블로그 서술만 확인)
- [ ] SMTP 경유 전용 한도 수치 (공식 페이지에 구분 없음)
- [ ] NAT 게이트웨이 경유 시 587 이 막히지 않는다는 명시 문구 (문서는 25 만 제한 대상으로 적음)
- [ ] 개인 계정에서 포트 465 지원 여부

## 열린 질문 → 분석 단계로
- [ ] 발신에 쓸 Gmail 계정을 평소 쓰는 개인 계정으로 할 것인가, 발송 전용 계정을 새로 만들 것인가? (앱 비밀번호는 계정 전체 메일에 접근할 수 있는 비밀값이다)
- [ ] 앱 비밀번호가 무효가 되거나 로그인이 차단됐을 때 발송 실패를 어떻게 알아챌 것인가? (실패 알림을 같은 메일 경로로 보낼 수 없다)
- [ ] 실제 ECS 호스트에서 로그인이 차단되는지는 PoC 로만 확인할 수 있다.
- [ ] 수신자가 늘어 일 500통에 가까워지면 도메인 + SES 로 넘어갈 것인가?

## 참고
- [Gmail 발송 한도](https://support.google.com/mail/answer/22839?hl=en) — 일 500통
- [앱 비밀번호](https://support.google.com/accounts/answer/185833?hl=en) — 발급 조건, 폐기 조건
- [Gmail SMTP 설정](https://support.google.com/mail/answer/7104828?hl=en) — smtp.gmail.com:587
- [OAuth 2.0 토큰 만료](https://developers.google.com/identity/protocols/oauth2) — Testing 상태 7일
- [Gmail API 스코프](https://developers.google.com/workspace/gmail/api/auth/scopes) — Sensitive / Restricted 분류
- [Gmail 프로그램 정책](https://support.google.com/mail/answer/16734397) — 스팸·자동화 관련 문구
- [EC2 포트 25 제한](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html) — 587·465 는 언급 없음
