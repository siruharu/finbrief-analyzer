---
type: research
project: finbrief-analyzer
topic: local-schedule
created: 2026-10-12
status: done
tags: [research, delivery-channels, schedule]
next: analysis
---

# 🔍 로컬 스케줄: 이 PC 에서 두 슬롯의 브리핑 작업을 정해진 시각에 띄우는 방법

> **핵심 질문** — AWS 없이, 개발 PC 하나에서 `run_briefing --slot kr_open|us_open` 을 월~금 정해진 시각에 돌리고, 실패를 드러내는 방법은 무엇인가.

## 배경
- delivery-channels Task 8 "인프라: 비밀값, 스케줄, 실패 알람"은 terraform(EventBridge Scheduler → ECS RunTask) 전제였다. 2026-10-08 "AWS 를 쓰지 않는다" 결정으로 `blocked` 가 됐고, 메모에 "로컬 스케줄 방식은 Task 7 뒤에 다시 정한다"고 적었다 ([[2026-10-07_delivery-poc]]).
- Task 7(발송 작업)과 stock-screening Task 11 까지 끝났다. 수동 실행으로 메일 수신을 확인했다 (2026-10-08 kr_open, 2026-10-12 kr_open). 이제 "사람이 명령을 치지 않아도 아침에 메일이 온다"가 남았다.
- 발송 시각 기본값은 플랜에 있다: 국내 Asia/Seoul 09:00, 미국 America/New_York 09:30, 월~금 ([[2026-10-07_delivery-channels]] 플랜).

## 코드베이스 안에 이미 있는 것
| 위치 | 하는 일 | 재사용 가능? |
|---|---|---|
| `src/finbrief_analyzer/jobs/run_briefing.py` | `--slot` 하나를 받아 수집 → 작성 → 발송. 종료 코드 0(끝까지 감) / 1(치명 오류·크래시). `brief_date` 는 **슬롯 시간대의 날짜** (`now.astimezone(SLOT_ZONES[slot]).date()`) | ✅ 스케줄러가 부를 명령 그대로 |
| `deliver/dispatch.py` + `delivery_log` | `(brief_date, slot, recipient, channel)` 유니크. 같은 날 두 번 불려도 두 번 보내지 않는다. 아무도 못 받으면 `operator_email` 로 안내 메일(SMTP 가 살아 있을 때만) | ✅ 트리거가 겹쳐도 안전 |
| `core/config.py` | `env_file=".env"` — **현재 디렉터리**의 `.env` 를 읽는다. 비밀값은 `SecretStr`, 로그에 남지 않음 | 런처가 작업 디렉터리를 저장소로 맞춰야 한다 |
| `compose.yml` `postgres` (profile `db`) | 로컬 DB. 작업 전에 떠 있어야 한다 | `docker compose --profile db up -d --wait` |
| `C:\Users\HH_PC\AppData\Local\finbrief\run_briefing.cmd` | **저장소 밖**에 있는 런처 (2026-10-08 12:31 작성, 문서·커밋 없음). `cd` 저장소 → `docker compose --profile db up -d --wait` → `uv run python -m ...run_briefing --slot %1` → `%LOCALAPPDATA%\finbrief\logs\<slot>.log` 에 마지막 실행 출력 | 내용은 재사용 가능. 저장소 안으로 옮겨 버전 관리해야 한다 |
| 작업 스케줄러 항목 `finbrief-us-open-once` | 2026-10-08 22:20 KST 일회성 트리거로 위 런처를 `us_open` 으로 부름. `WakeToRun`·`StartWhenAvailable` 없음, 실행 제한 20분 | ❌ **실패한 실험.** 마지막 실행 2026-10-09 01:44(예정보다 3시간 24분 늦음), 결과 `267014`(0x41306, 작업이 중단됨). `logs\` 가 비어 있고 DB 에 10-08 us_open 발송 기록이 없다 → 런처가 첫 줄도 쓰지 못했거나 시작 즉시 끊겼다. 지워야 한다 |
| 구현 노트 [[2026-10-08_run-briefing]] 발견 이슈 | "전원이 이미 받은 경우에도 수집을 다시 한다" (Marketaux 하루 100회 한도) | 트리거를 겹쳐 걸 때만 문제가 된다 |

## 이 PC 의 사실 (2026-10-12 확인)
| 항목 | 값 | 함의 |
|---|---|---|
| 기기 | Lenovo **노트북**(배터리 있음), Windows 11 Home, 시간대 Korea Standard Time | 뚜껑·전원 상태에 따라 꺼져 있을 수 있다 |
| 절전 | AC 유휴 **5분**, DC 3분 뒤 대기(Modern Standby S0). 깨우기 타이머 허용(AC·DC 모두 1). 최대 절전 유휴 값은 읽히지 않음(0x80000077) | 사람이 안 쓰면 거의 항상 대기 상태다. 부팅 후 6일째지만 대기 시간이 포함된 값이다 |
| 사용자의 기존 예약 작업 `jandi-picker` | 매일 16:30, `WakeToRun` + `StartWhenAvailable`, `python.exe` 직접 실행, stdout/stderr 를 저장소 `logs/` 에 추가 | **마지막 실행 2026-10-12 03:23**(예정 16:30 → 약 11시간 늦음), 결과 1. 즉 **이 PC 에서 `WakeToRun` 은 예정 시각에 깨우는 것을 보장하지 않았고**, `StartWhenAvailable` 이 PC 가 깨어난 뒤 실행시켰다 |
| Docker Desktop | 29.8.2(linux 엔진). 로그인 시 자동 시작(HKCU Run 키). `app` 컨테이너는 `restart=no` | 로그인만 돼 있으면 `docker compose up --wait` 가 된다. 로그인 전에는 안 된다 |
| 도구 경로 | `uv` 0.12.23 `C:\Users\HH_PC\.local\bin\uv.exe`, `make` 없음 | 런처는 절대 경로를 쓴다 |

## 외부 조사

### 옵션 A — Windows 작업 스케줄러 (`Register-ScheduledTask` / `schtasks`)
- 버전: Windows 11 내장. 등록은 PowerShell `New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday..Friday -At 09:00` 또는 XML.
- 요약: 트리거 시각은 **PC 로컬 시간(KST)만** 지정할 수 있다. IANA 시간대(`America/New_York`)는 없다. 설정으로 `WakeToRun`(절전에서 깨움), `StartWhenAvailable`(놓친 시작을 가능해지면 바로 실행), `ExecutionTimeLimit`, `MultipleInstancesPolicy=IgnoreNew`, `DisallowStartIfOnBatteries` 가 있다. 결과는 "마지막 실행 결과" 코드(0 성공, 0x1 명령 실패, 0x41306 중단, 0x41301 실행 중)와 `Microsoft-Windows-TaskScheduler/Operational` 이벤트 로그에 남는다. 실행 계정 `InteractiveToken` 은 **사용자가 로그인돼 있어야** 돈다.
- 출처: Microsoft Learn — Task Scheduler schema (`settingsType`, `calendarTriggerType`), `Register-ScheduledTask`.

### 옵션 B — APScheduler 를 상주 프로세스로 (compose 서비스 또는 FastAPI 앱 안)
- 버전: APScheduler **3.11.3** (2026-06-28, PyPI). 4.x 는 아직 정식이 아니다.
- 요약: `CronTrigger(day_of_week='mon-fri', hour=9, minute=30, timezone=ZoneInfo('America/New_York'))` 로 **시간대·서머타임을 바로 표현**한다. `misfire_grace_time` 으로 놓친 실행을 뒤늦게 돌릴 수 있다. 프로세스가 살아 있을 때만 동작한다 — PC 가 대기 상태면 컨테이너도 멈추고, **PC 를 깨우지 못한다**. 의존성 1개 추가. 현재 이 서비스는 로컬 1개 프로세스라 분석 문서가 걱정한 "태스크 2개가 동시에 깨어남"은 없다.
- 출처: APScheduler 3.x 사용자 가이드 (cron trigger, misfire).

### 옵션 C — 컨테이너 안의 cron (예: `supercronic`, `ofelia`)
- 요약: B 와 같은 제약(상주 프로세스, PC 를 못 깨움)에 이미지·설정 파일이 하나 더 는다. `TZ` 환경변수로 시간대 지정은 된다.

### 시간대 사실
- us_open 09:30 America/New_York = **22:30 KST**(EDT, 3월 둘째 일요일~11월 첫째 일요일) / **23:30 KST**(EST). kr_open 09:00 KST 는 변환이 없다.
- `brief_date` 가 슬롯 시간대의 날짜이므로, us_open 을 22:30 KST 와 23:30 KST 두 번 불러도 같은 날짜로 묶여 두 번째는 "이미 받음"으로 건너뛴다(수집은 다시 한다).

## 트레이드오프 (사실만. 판단은 분석 단계)
| 항목 | A: 작업 스케줄러 | B: APScheduler 상주 | C: 컨테이너 cron |
|---|---|---|---|
| 구현 비용 | 런처 1개(이미 있음) + 등록 스크립트 1개. 코드 변경 없음 | 스케줄러 모듈·진입점·compose 서비스. 의존성 추가. 테스트 | 이미지·설정 파일 추가 |
| 시간대 | KST 고정 시각만. ET 09:30 은 22:30/23:30 KST 로 바뀐다 | IANA 시간대 그대로 | `TZ` 로 가능 |
| PC 가 대기 상태일 때 | `WakeToRun` 시도(이 PC 에선 보장 안 됨) + `StartWhenAvailable` 로 깨어나면 실행 | 깨어나면 `misfire_grace_time` 안일 때만 실행. 깨우지 못함 | 같음 |
| 로그인 전 | 안 돈다(`InteractiveToken`) | Docker Desktop 이 로그인 시 시작하므로 역시 안 돈다 | 같음 |
| 실패가 드러나는 곳 | 마지막 실행 결과 코드, 이벤트 로그, 런처 로그 파일 | 프로세스 로그만 | 컨테이너 로그만 |
| 생태계/레퍼런스 | 사용자가 `jandi-picker` 에 이미 쓴다 | 흔함 | 흔함 |
| 되돌리기 | `Unregister-ScheduledTask` 한 줄 | 서비스 제거·의존성 제거 | 서비스 제거 |

## 확인 못 한 것
- [ ] 뚜껑을 덮은 상태의 S0 대기에서 `WakeToRun` 이 깨우는지(뚜껑 동작 값은 읽히지 않았다). `jandi-picker` 의 11시간 지연이 뚜껑 때문인지 최대 절전 때문인지 모른다.
- [ ] `finbrief-us-open-once` 의 `267014` 가 20분 실행 제한 때문인지 사용자가 끊은 것인지. 로그가 없어 런처 자체가 시작되지 않았을 가능성이 크다(`cmd.exe /c "경로" 인자` 의 인용 문제일 수 있다).
- [ ] 로그인 직후 Docker Desktop 엔진이 뜨기까지의 시간. `--wait` 는 엔진이 떠 있어야 하고, 엔진이 아직 없으면 바로 실패한다.

## 열린 질문 → 분석 단계로
- [ ] 트리거를 어디에 두는가: 작업 스케줄러(A) vs 상주 프로세스(B).
- [ ] us_open 을 KST 한 시각(22:30, 겨울엔 ET 08:30)으로 고정하는가, 두 시각(22:30·23:30)을 걸고 중복 방지에 맡기는가, 작업 안에서 ET 를 판정하는가.
- [ ] PC 가 꺼져 있다가 몇 시간 뒤 켜졌을 때 그 슬롯을 보내는가(늦은 브리핑) 안 보내는가(창을 둔다).
- [ ] 실패 알람의 최소선: 결과 코드·로그 파일로 충분한가, Windows 토스트를 더하는가.
- [ ] 런처·등록 스크립트를 저장소 어디에 두는가. 저장소 밖 `AppData\Local\finbrief` 의 사본과 `finbrief-us-open-once` 를 정리하는가.

## 참고
- [Task Scheduler Schema — settingsType](https://learn.microsoft.com/windows/win32/taskschd/taskschedulerschema-settings-tasktype-element) — WakeToRun·StartWhenAvailable·ExecutionTimeLimit 정의
- [Register-ScheduledTask](https://learn.microsoft.com/powershell/module/scheduledtasks/register-scheduledtask) — PowerShell 등록
- [APScheduler 3.x User guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html) — CronTrigger 시간대, misfire_grace_time
- [[2026-10-07_delivery-poc]] — 로컬 우선 결정과 Task 8 보류 기록
- [[2026-10-07_delivery-channels]] (분석) — EventBridge vs 앱 내부 스케줄러 비교
