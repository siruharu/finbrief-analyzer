---
type: task
project: finbrief-analyzer
topic: local-schedule
created: 2026-10-12
source_plan: "[[2026-10-12_local-schedule]]"
branch: feat/local-schedule
issue: 없음
tags: [task, delivery-channels, schedule]
next: implementation
---

# ✅ 작업: 로컬 스케줄 (delivery-channels Task 8 재정의, Task 10 추가)

> **작업 상태의 정본은 이 문서가 아니라 `delivery-channels.tasks.json` 이다.**
> 이 주제는 새 tasks.json 을 만들지 않는다 — Task 8 은 delivery-channels 의 것이고 거기서 상태를 관리한다.
>
> ```bash
> .claude/hooks/harness.py stage task delivery-channels
> .claude/hooks/harness.py task list
> ```

## 쪼갠 기준
- **Task 8 하나로 둔다.** 런처·등록 스크립트·README 는 따로 릴리스할 수 없다 — 등록 스크립트는 런처 경로를 알고, README 는 둘을 설명한다. 셋 중 하나만 있으면 쓸모가 없다.
- **Task 10 은 떼어 둔다.** 코드 변경이고 테스트가 있다. Task 8 은 코드 변경이 없다. 섞으면 Task 8 의 완료 판정(`make check` 통과)이 Task 10 의 진행에 흔들린다.

## Task 별 설계 메모

### Task 8 — 로컬 스케줄: 런처, 작업 스케줄러 등록, 운영 절차

**손댈 곳**

| 파일 | 내용 | 작업 |
|---|---|---|
| `scripts/run_briefing.cmd` | `run_briefing.cmd <kr_open|us_open>`. `PYTHONUTF8=1`. 저장소 루트로 `cd /d`(`.env` 가 거기 있다). Docker 엔진이 준비될 때까지 `docker info` 를 최대 12회(10초 간격) 재시도 — 로그인 직후를 위해. `docker compose --profile db up -d --wait`. `uv run python -m finbrief_analyzer.jobs.run_briefing --slot %SLOT%`. 출력은 `logs\%SLOT%.log` 에 **덮어쓴다**(마지막 실행만), 요약 한 줄(`날짜 시각 slot rc`)은 `logs\history.log` 에 **추가**. 마지막 줄 `=== exit <rc> ...`. **`exit /b %RC%`** 로 작업의 종료 코드를 돌려준다 | 신규 |
| `scripts/register_tasks.ps1` | `-Unregister` 스위치. 저장소 루트는 `$PSScriptRoot\..`. 항목 2개: `finbrief-kr-open`(월~금 09:00), `finbrief-us-open`(월~금 22:30). 트리거 `New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At`. 설정 `-WakeToRun -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries`. 동작 `cmd.exe /c "<루트>\scripts\run_briefing.cmd" <slot>`, `-WorkingDirectory <루트>`. `Register-ScheduledTask -Force` 로 멱등. 있으면 `finbrief-us-open-once` 삭제. 등록 뒤 `Get-ScheduledTask` 로 두 항목과 다음 실행 시각을 출력 | 신규 |
| `.gitignore` | `logs/` | 수정 |
| `README.md` | "## 운영 — 로컬 스케줄" 절: 등록·해제 명령, 발송 시각과 그 이유(22:30 KST = 여름 ET 09:30 / 겨울 08:30), 로그 위치, 수동 실행, 결과 코드 읽는 법(`Get-ScheduledTaskInfo`), 앱 비밀번호 교체(`.env` 수정만), 전제(로그인 상태·Docker Desktop 자동 시작) | 수정 |
| `C:\Users\HH_PC\AppData\Local\finbrief\` | 저장소 밖 사본 삭제 | 삭제 |

**먼저 쓸 테스트**
- 없음. 스크립트 2개와 문서다. 대신 아래 순서로 손으로 확인하고 결과를 구현 노트에 남긴다.
  1. `scripts\register_tasks.ps1` → 두 항목이 보이고 `finbrief-us-open-once` 가 사라졌다.
  2. `Start-ScheduledTask finbrief-kr-open` → 1분 안에 `logs\kr_open.log` 가 생기고 `=== exit 0` 으로 끝난다(오늘 kr_open 은 이미 발송돼 `skipped=1`). `Get-ScheduledTaskInfo` 의 `LastTaskResult` 가 0.
  3. `Get-ScheduledTaskInfo finbrief-us-open` 의 `NextRunTime` 이 오늘 22:30.

**엣지 케이스**
- `cmd.exe /c` 인용: 경로에 공백은 없지만 `"경로" 인자` 형태를 `cmd /c ""경로" 인자"` 로 감싼다(`jandi-picker` 와 같은 꼴). 일회성 작업의 `267014` 는 여기서 났을 가능성이 크다 → 2번 수동 실행이 이것을 잡는다.
- Docker 엔진이 2분 안에 안 뜨면 rc=2 로 끝내고 로그에 남긴다. 이 경우 메일은 안 가고 결과 코드로 드러난다.
- `uv` 가 의존성을 다시 설치할 수 있다(`uv run` 이 lock 을 맞춘다). 첫 실행이 조금 길 수 있지만 30분 제한 안이다.
- 미국 슬롯을 **수동으로 지금 돌리지 않는다.** 지금(KST 오후) 돌리면 ET 날짜가 오늘이 되어 저녁 22:30 의 실제 실행이 "이미 받음"으로 건너뛴다. 수동 확인은 kr_open 으로만 한다.
- `.env` 값이 로그에 들어가지 않는지 로그를 한 번 눈으로 본다(작업이 `SecretStr` 을 쓰므로 들어가지 않아야 한다).

**완료 판정** — `tasks.json` 의 `verify` 와 같다
```bash
powershell -NoProfile -Command "if ((Get-ScheduledTask -TaskName finbrief-kr-open,finbrief-us-open -ErrorAction Stop | Measure-Object).Count -ne 2) { exit 1 }" && findstr /c:"=== exit 0" logs\kr_open.log && uv run ruff check . && uv run mypy && uv run pytest
```

### Task 10 — 이미 전원이 받은 날은 수집을 건너뛴다 (선택)

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| `src/finbrief_analyzer/jobs/run_briefing.py` | `run()` | 수집 전에 `DeliveryLog` 로 "오늘 이 슬롯에 아직 못 받은 활성 수신자"를 센다. 0 이면 수집·작성 없이 `DispatchResult(skipped=n)` 을 돌려준다 |
| `src/finbrief_analyzer/deliver/` (log 또는 dispatch) | `pending_recipients(brief_date, slot, recipients)` | 신규. 선점 로직과 같은 기준을 쓴다 |
| `tests/jobs/test_run_briefing.py` | | 위 두 테스트 |

**엣지 케이스**
- `failed` 는 다시 선점되므로 "못 받은 사람"에 포함한다. `pending`(선점만 되고 결과 없음)도 포함한다 — 지금 규칙과 같다.
- 수신자가 0명이면 수집하지 않는다(지금도 보낼 곳이 없다).

**완료 판정**
```bash
uv run pytest tests/jobs tests/deliver && uv run ruff check . && uv run mypy && uv run pytest
```

## 열어둔 질문
- 로그인 전(재부팅 뒤 자동 로그인 없음)에는 어느 방식도 돌지 않는다. 그런 아침이 잦으면 자동 로그인 또는 `S4U` 실행 계정을 본다 — Docker Desktop 이 사용자 세션에서 뜨므로 간단하지 않다.
- 겨울 ET 08:30 발송이 불편하면 `register_tasks.ps1` 의 `-At 23:30` 으로 바꾸고 다시 돌리면 된다(여름엔 10:30 ET). 둘 다 만족하려면 Task 10 뒤에 트리거를 두 개 거는 선택지가 열린다.
