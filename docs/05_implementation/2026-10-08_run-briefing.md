---
type: implementation
project: finbrief-analyzer
topic: delivery-channels
created: 2026-10-08
status: done
source_task: "[[2026-10-07_delivery-channels]]"
commits: [18bc7d5]
blog_candidate: false
tags: [implementation]
---

# 🛠️ 구현: delivery-channels Task 7 — 단순 작성기 v0 와 작업 엔트리포인트

한 명령으로 수집 → 작성 → 발송이 돈다. 로컬에서 실제 메일 1통이 나가는 것까지 확인했다.

```bash
uv run python -m finbrief_analyzer.jobs.run_briefing --slot kr_open   # 또는 us_open
```

## 한 일
- `compose/simple.py`: `compose_simple(snapshot, briefing_date)` — 시세 섹션(필수), 뉴스 섹션, 안내 문구.
- `jobs/run_briefing.py`: `main(argv)`, `run(slot, now, deps)`, `JobDeps`, `open_deps(settings)`, `briefing_date(slot, now)`.
- 테스트 22개 (작성기 11, 작업 11).
- 로컬 실행 준비: `.env` 에 `APP_DB_*` 5줄 추가(compose 의 로컬 값), 로컬 DB 에 수신자 1명 등록.

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| **휴장이어도 보낸다.** 안내 문구를 본문 맨 위에 싣는다 | 태스크 메모의 "대상 시장이 휴장이면 발송하지 않는다" | 태스크 문서의 "data-sources 구현 뒤 정해진 것"(2026-10-07 사용자 결정)이 우선한다고 적혀 있다. 그 테스트는 "휴장이었어도 보내고 안내가 시세보다 위에 있다"로 바꿨다 |
| 금리는 bp, 환율은 원과 %, 지수는 % | 전부 % | 같은 절의 결정. `국고채 3년 3.961% (+2.8bp)` |
| 뉴스는 최신 10건, 제목·출처·링크만 | 요약 본문도 싣는다 / 80건 전부 | 고르고 요약하는 일은 LLM 단계의 몫이고 아직 없다. 메일 한 통에서 훑을 수 있는 길이로 잘랐다 |
| 브리핑 날짜는 **곧 열리는 시장의 현지 날짜** | UTC 날짜 / 서버 날짜 | 미국 개장 슬롯은 서울 기준으로 밤 10시 반이다. 뉴욕 날짜로 적어야 "10월 8일 미국 개장 브리핑"이 맞다. 발송 기록의 키(`brief_date`)도 이 날짜다 |
| 시세가 하나도 없으면 발송 불가 → 종료 코드 1 | 뉴스만이라도 보낸다 | Task 2 의 결정(필수 섹션은 시세). 운영자 주소가 있으면 알림이 간다 |
| 일부 수신자만 실패하면 종료 코드 0 | 1 | 실행 자체는 끝까지 갔다. 실패한 사람은 다음 실행에서 다시 선점된다. 실패 수는 요약 로그에 남는다 |
| `open_deps` 가 **수집 전에** SMTP·DB 설정을 확인한다 | 쓸 때 확인 | 외부 API 를 십여 번 부른 뒤에 "보낼 수 없다"를 알게 되지 않는다. Marketaux 는 하루 100회 한도다 |
| `main(argv, open_job, now)` 로 의존성을 주입 | `monkeypatch` | 테스트가 실제 `main` 을 종료 코드까지 그대로 돌린다. 기본값만 실제 의존성을 연다 |
| 처리되지 않은 예외는 `main` 이 잡아 스택을 로그에 남기고 1 을 돌려준다 | 그대로 터지게 둔다 | 스케줄러는 종료 코드만 본다. 무엇이 터졌는지는 로그에 있어야 한다 |
| 작업이 끝나면 SMTP 연결·HTTP 클라이언트·DB 엔진을 닫는다 | 프로세스 종료에 맡긴다 | 태스크 메모의 엣지 케이스. `finally` 한 곳에 모았다 |

## 막혔던 부분 / 해결 과정
없음.

## 검증 결과
```
uv run pytest tests/jobs tests/compose  → 22 passed
uv run ruff check .                     → All checks passed!
uv run mypy                             → Success: no issues found in 66 source files
uv run pytest                           → exit 0, 커버리지 97%
```
수동 확인 (2026-10-08 10:18 KST, 로컬 postgres 18.6, 실제 Gmail SMTP):
```
1회차: briefing kr_open 2026-10-08: sent=1 skipped=0 failed=0 aborted=False   (exit 0)
2회차: briefing kr_open 2026-10-08: sent=0 skipped=1 failed=0 aborted=False   (exit 0)
delivery_log: 2026-10-08 | kr_open | email | sent
```
- 수집은 ECOS·RSS 6개·Marketaux·DART 모두 200 으로 응답했다. 로그의 API 키는 `***` 로 가려져 있다.
- 두 번째 실행은 메일을 보내지 않았다. 중복 방지가 실제 경로에서 동작한다.
- `run_briefing.py` 의 커버리지 84% 는 `open_deps` 의 실제 배선 부분이다. 위 수동 실행이 그 부분을 지났다.

## 발견한 이슈 (이번 범위 밖)
- [ ] **전원이 이미 받은 경우에도 수집을 다시 한다.** 2회차 실행이 Marketaux 를 3번 더 불렀다(하루 100회 한도). 수집 전에 "아직 못 받은 수신자가 있는가"를 먼저 볼 수 있다. 플랜에 없어 넣지 않았다.
- [ ] `httpx` 의 요청 로그가 INFO 로 전부 찍혀 요약 한 줄이 묻힌다. 로그 수준 조정은 Task 8 을 대신할 스케줄 방식을 정할 때 같이 본다.
- [ ] 수신자 등록은 여전히 SQL 직접 입력이다.
- [ ] `Dockerfile` 확인(같은 이미지에서 작업이 실행되는지)은 하지 않았다. AWS 를 쓰지 않기로 해 지금은 호스트에서 `uv run` 으로 돌린다.

## 남은 것
- [ ] 받은 메일의 실제 모양(HTML 렌더링, 한글, 링크) — 수신자 확인 필요.
- [ ] 로컬에서 정해진 시각에 이 명령을 띄우는 방법 (Task 8 을 대신할 것).
