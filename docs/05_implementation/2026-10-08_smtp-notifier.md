---
type: implementation
project: finbrief-analyzer
topic: delivery-channels
created: 2026-10-08
status: done
source_task: "[[2026-10-07_delivery-channels]]"
commits: [415b738]
blog_candidate: false
tags: [implementation]
---

# 🛠️ 구현: delivery-channels Task 5 — SMTP Notifier

"한 통을 보내는 방법"만 만들었다. 누구에게 몇 번 보낼지는 Task 6 이다. 테스트는 실제 SMTP 서버에 접속하지 않는다.

## 한 일
- `Settings` 에 `smtp_host`(기본 `smtp.gmail.com`), `smtp_port`(587), `smtp_user`, `smtp_password`, `smtp_timeout_seconds`(30), `mail_from_name`, `operator_email`.
- `deliver/smtp.py`: `SmtpNotifier(settings, connect)` 의 `send`·`close`, `_build_message`, `_classify`.
- `DeliveryError` 에 `fatal` 추가.
- `.env.example` 에 `APP_SMTP_*` 예시.
- 테스트 17개 (`tests/deliver/test_smtp.py`, `FakeSmtp`).

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| `DeliveryError.fatal` 을 추가했다 | `retryable` 하나로 구분 | 인증 실패와 수신자 거절은 둘 다 "재시도 불가"지만 뜻이 다르다. 인증 실패는 남은 수신자도 전부 실패한다(Task 6 이 중단한다). 수신자 거절은 그 한 명만의 일이다. Task 2 의 모델에 없던 구분이라 여기서 넣었다 |
| 오류 메시지는 **예외 클래스 이름과 응답 코드**로만 만든다 | 서버 응답 문구를 그대로 싣는다 | 이 메시지는 발송 기록의 사유와 로그로 간다. 서버가 무엇을 되돌려 보내든 비밀값·주소가 섞이지 않는다. `raise ... from None` 으로 원인 예외도 끊었다 |
| 4xx 는 재시도 가능, 5xx 는 불가, 연결 끊김·타임아웃은 재시도 가능 | 전부 재시도 | SMTP 응답 코드의 뜻 그대로다. 5xx 를 다시 보내면 같은 답이 온다 |
| 연결은 **첫 발송 때** 열고 `close()` 까지 재사용 | 생성 시 연결 / 매번 연결 | 수신자가 0명이면 로그인하지 않는다. Gmail 에 로그인 횟수를 늘리지 않는다 |
| 재시도 가능·치명 오류 뒤에는 연결을 버린다 | 그대로 둔다 | 끊긴 연결을 다시 쓰면 다음 수신자도 실패한다. 수신자 거절(5xx)은 연결이 멀쩡하므로 그대로 쓴다 |
| 로그인 도중 실패하면 열다 만 연결도 닫는다 | 버려둔다 | 소켓이 남는다 |
| 앱 비밀번호의 공백을 걷어 낸다 | 그대로 로그인 | PoC 에서 확인했다. 구글이 4자씩 띄워 보여 줘서 그대로 붙여 넣기 쉽다 |
| 설정 누락은 **생성 시점**에 `ValueError` | 첫 발송 때 | 수집을 다 하고 나서 "보낼 수 없다"를 알게 되지 않는다 |
| `connect` 를 주입한다. 기본값만 `smtplib.SMTP` 를 연다 | `smtplib.SMTP` 를 monkeypatch | 테스트가 가짜 연결을 순서대로 건네 재연결까지 볼 수 있다 |
| 줄바꿈이 든 수신자 주소는 연결 전에 거부 | `EmailMessage` 에 맡긴다 | 헤더 주입 시도다. 어떤 오류로 드러날지를 라이브러리에 맡기지 않는다 |

## 막혔던 부분 / 해결 과정
없음.

## 검증 결과
```
uv run pytest tests/deliver/test_smtp.py  → 17 passed
uv run ruff check .                       → All checks passed!
uv run mypy                               → Success: no issues found in 57 source files
uv run pytest                             → exit 0, 커버리지 97%
```
실제 Gmail 로의 발송은 PoC 에서 같은 순서(STARTTLS → 로그인 → `send_message`)로 확인했다. 이 클래스를 통한 실제 발송은 Task 7 의 수동 확인에서 한다.

## 발견한 이슈 (이번 범위 밖)
- [ ] `operator_email` 을 설정에 넣었지만 `.env` 에는 아직 값이 없다. Task 6 의 운영자 알림은 값이 없으면 건너뛰어야 한다.

## 남은 것
- [ ] 없음.
