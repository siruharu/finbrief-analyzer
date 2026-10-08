---
type: implementation
project: finbrief-analyzer
topic: delivery-channels
created: 2026-10-08
status: done
source_task: "[[2026-10-07_delivery-channels]]"
commits: [ac9c4f0]
blog_candidate: false
tags: [implementation]
---

# 🛠️ 구현: delivery-channels Task 2 — 브리핑 모델, Notifier 인터페이스, 렌더러

작성기(v0, 이후 LLM)와 발송 사이의 계약을 고정했다. 이 Task 는 아무것도 보내지 않는다.

## 한 일
- `deliver/models.py`: `Briefing`, `Section`, `LinkItem`, `RenderedEmail`, `Channel`, `DeliveryStatus`, `DeliveryError(retryable)`.
- `deliver/ports.py`: `Notifier.send(recipient, email)` 프로토콜.
- `deliver/render.py`: `render_email(briefing)` → 제목, text 본문, HTML 본문.
- 테스트 13개 (`tests/deliver/test_render.py`).

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| `Section` 은 **글줄(`lines`)과 링크 목록(`links`)** 만 가진다. 시세도 이미 만들어진 글줄로 받는다 | `Briefing` 이 `Quote`·`NewsItem` 을 그대로 든다 | "금리는 bp, 환율은 원과 %" 같은 표기 규칙은 작성기의 일이다. 렌더러가 `Quote` 를 알면 LLM 작성기로 바꿀 때 렌더러도 같이 바뀐다. 렌더러는 `Settings` 도 `Market` 도 읽지 않는다 |
| 필수 여부를 `Section.required` 로 둔다 | `Briefing` 이 "시세 섹션" 을 이름으로 안다 | 어느 섹션이 필수인지는 작성기가 정한다. 모델은 "필수 섹션이 비면 못 보낸다"만 판정한다 |
| 필수 섹션이 **하나도 없으면** 발송 불가 | 빈 것만 없으면 가능 | 작성기가 `required` 를 빠뜨렸을 때 내용 없는 메일이 나가는 쪽보다 안 나가는 쪽이 낫다 |
| `http(s)` 가 아닌 링크는 `LinkItem.safe_url` 이 걸러 낸다 | 렌더러에서 검사 | text·HTML 두 본문이 같은 판정을 쓴다. 카카오톡 렌더러가 생겨도 같은 속성을 쓴다 |
| 빈 선택 섹션은 본문에서 뺀다 | 제목만 싣는다 | 뉴스 0건인 날 "뉴스" 제목만 덩그러니 남지 않는다 |
| HTML 은 `html.escape` 로 직접 조립 | Jinja2 | 본문 구조가 제목·문단·목록 셋뿐이다. 의존성을 늘릴 이유가 없다. `href` 값은 `quote=True` 로 따옴표까지 이스케이프한다 |
| `Notifier.send` 는 `RenderedEmail` 을 받는다 | `Briefing` 을 받는다 | 태스크 설계 그대로다. 렌더링은 수신자 수와 무관하게 한 번만 한다. 카카오톡은 자기 렌더 결과 타입과 포트를 따로 가지면 된다 |
| `DeliveryStatus` 는 `pending`·`sent`·`failed` 셋 | `skipped` 추가 | "이미 보냄"은 기록의 상태가 아니라 선점 실패의 결과다. Task 6 의 `DispatchResult` 가 센다 |

## 막혔던 부분 / 해결 과정
없음.

## 검증 결과
```
uv run pytest tests/deliver/test_render.py   → 13 passed
uv run ruff check .                          → All checks passed!
uv run mypy                                  → Success: no issues found in 42 source files
uv run pytest                                → 전체 통과, 커버리지 99%
```
`deliver/ports.py` 의 커버리지 0% 는 프로토콜 정의뿐이라 그렇다. Task 5 에서 구현체가 생기면 채워진다.

## 발견한 이슈 (이번 범위 밖)
- [ ] 태스크 문서의 Task 8 과 플랜의 실행 형태(일회성 ECS 태스크, EventBridge)는 AWS 전제다. 2026-10-08 사용자 결정으로 AWS 를 쓰지 않으므로, 로컬에서 정해진 시각에 작업을 띄우는 방법을 Task 7 뒤에 다시 정해야 한다.
- [ ] `CLAUDE.md` 의 "인프라" 절도 ECS 전제다. 고칠지는 사용자가 정한다.

## 남은 것
- [ ] 실제 메일 클라이언트(네이버)에서 HTML 본문이 어떻게 보이는지는 Task 7 의 수동 발송 때 확인한다.
