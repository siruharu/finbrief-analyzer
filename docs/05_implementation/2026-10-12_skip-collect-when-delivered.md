---
type: implementation
project: finbrief-analyzer
topic: local-schedule
created: 2026-10-12
status: done
source_task: "[[2026-10-12_local-schedule]]"
commits: [f9d9d53]
blog_candidate: false
tags: [implementation, delivery-channels, schedule]
---

# 🛠️ 구현: delivery-channels Task 10 — 전원이 이미 받은 날은 수집 없이 끝내기

[[2026-10-08_run-briefing]] 의 발견 이슈. 같은 날 작업이 두 번 불리면(수동 재실행, 작업 스케줄러의 `StartWhenAvailable` 재시도) 아무도 받을 사람이 없는데도 Marketaux(하루 100회)·ECOS·RSS·일봉 갱신까지 전부 다시 했다.

## 한 일
- `store/delivery_log.py` — `waiting(session, brief_date, slot, channel, recipient_ids)`: 아직 선점할 수 있는 수신자(행 없음 또는 `failed`). `DeliveryLog.waiting()` 으로 감쌈.
- `jobs/run_briefing.py` — `run()` 이 수집 전에 `waiting` 을 본다. 비어 있으면 `DispatchResult(skipped=수신자 수)` 로 끝낸다. 요약 로그는 같은 형식.
- 테스트: 저장소 2개(sent·pending 은 제외, failed·미선점은 포함 / 수신자 없음), 작업 2개(두 번째 실행은 수집 0회 / 한 명이 failed 면 수집하고 그 사람에게만 발송).

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| `pending` 을 "받은 것"으로 센다 | 미선점·failed·pending 모두 기다리는 사람으로 | `claim` 과 같은 기준이어야 한다. `claim` 은 pending 을 거부하므로, 여기서 기다린다고 해 봐야 수집만 하고 보내지 못한다 |
| 수신자가 0명이면 수집하지 않는다 | 이전처럼 수집 후 발송 0 | 보낼 곳이 없는 수집은 외부 호출만 쓴다 |
| `run()` 안에서 판정 | `dispatch()` 안에서 | 아끼려는 것이 수집이고, 수집은 `dispatch` 전에 일어난다 |
| 수신자 목록을 한 번만 읽어 `dispatch` 에 넘긴다 | `dispatch` 가 다시 읽는다 | 판정과 발송이 같은 명단을 본다 |

## 막혔던 부분 / 해결 과정
없음.

## 검증 결과
```
uv run pytest tests/jobs tests/store tests/deliver → 110 passed
ruff · mypy · 전체 pytest (task done 10)         → 통과

실측: scripts\run_briefing.cmd kr_open (오늘 09:00 분 이미 발송됨, 15:03 KST)
  http requests in logs\kr_open.log: 0        ← 이전 같은 상황: ECOS 4·RSS 6·Marketaux 3·네이버 8·일봉 갱신 2분
  briefing kr_open 2026-10-12: sent=0 skipped=1 failed=0 aborted=False
  === exit 0 ===  (DB 기동 포함 수 초)
```

## 발견한 이슈 (이번 범위 밖)
- 없음.

## 남은 것
- [ ] 없음. delivery-channels 토픽의 태스크 10개가 모두 done.
