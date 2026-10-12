---
type: implementation
project: finbrief-analyzer
topic: local-schedule
created: 2026-10-12
status: done
source_task: "[[2026-10-12_local-schedule]]"
commits: [87507a0, c60b0ce]
blog_candidate: true
tags: [implementation, delivery-channels, schedule]
---

# 🛠️ 구현: delivery-channels Task 8 — 로컬 스케줄 (작업 스케줄러 + 런처)

AWS 전제(terraform·EventBridge)였던 Task 8 을 "이 PC 의 Windows 작업 스케줄러가 부른다"로 다시 정의해 끝냈다. 코드는 바뀌지 않았고, 바뀐 것은 누가 작업을 부르는가다. 근거는 [[2026-10-12_local-schedule]] 리서치·분석.

## 한 일
- `scripts/run_briefing.cmd <slot>` — 저장소 루트로 이동(`.env` 가 거기 있다) → Docker 엔진이 뜰 때까지 최대 12×10초 대기 → `docker compose --profile db up -d --wait` → `uv run python -m finbrief_analyzer.jobs.run_briefing --slot` → `logs\<slot>.log`(마지막 실행 전체)·`logs\history.log`(실행마다 한 줄) → **작업의 종료 코드를 그대로 반환**.
- `scripts/register_tasks.ps1 [-Unregister]` — `finbrief-kr-open`(월~금 09:00), `finbrief-us-open`(월~금 22:30) 를 멱등으로 등록. `WakeToRun`, `StartWhenAvailable`, 실행 제한 30분, `IgnoreNew`, 배터리에서도 실행. 실패한 실험 `finbrief-us-open-once` 를 지운다.
- `README.md` "운영 — 로컬 스케줄" 절, `.gitignore` 에 `logs/`.
- 저장소 밖 `%LOCALAPPDATA%\finbrief\run_briefing.cmd`(2026-10-08, 문서 없음) 삭제.
- 테스트 1개 수정(`c60b0ce`): 스크리닝 기본값 테스트가 개발자의 `.env` 를 읽지 않게 `monkeypatch.chdir(tmp_path)`.

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| 런처가 **작업의 종료 코드를 반환** | 로그만 남기고 0 | 작업 스케줄러의 "마지막 실행 결과"가 곧 작업 결과가 된다. 이전 사본은 `echo` 가 마지막이라 늘 0 이었다 |
| Docker 엔진 대기 `ping -n 11 127.0.0.1` | `timeout /t 10` | `timeout` 은 표준 입력이 리디렉션된 환경에서 "입력 리디렉션은 지원되지 않습니다"로 죽는다. 작업 스케줄러가 그런 환경이다 |
| 런처 호출을 `cmd /c ""<경로>" <slot>"` | `cmd /c "<경로>" <slot>` | 바깥 따옴표가 없으면 cmd 가 안쪽 따옴표를 벗겨 인자 경계가 깨진다. `jandi-picker` 와 같은 꼴. 일회성 작업의 `267014` 는 이 인용 문제였을 가능성이 크다 |
| 수동 확인은 **kr_open 으로만** | us_open 도 돌려 본다 | 지금(KST 오후) us_open 을 돌리면 ET 날짜가 오늘이 되어 22:30 의 실제 실행이 "이미 받음"으로 건너뛴다 |
| 로그는 저장소 `logs/` | `%LOCALAPPDATA%` | 사용자의 다른 예약 작업(`jandi-picker`)과 같은 자리. 저장소를 열면 보인다. git 제외 |
| `.cmd` 는 CRLF·ASCII | LF 그대로 | LF 만 있는 배치 파일은 `goto`/라벨이 어긋나는 경우가 있다. 주석은 영어라 ASCII 로 충분하다 |
| 테스트 수정은 **그 테스트만** | `Settings()` 를 쓰는 모든 테스트에 `chdir` | 실패한 것은 하나다. 나머지는 지금 `.env` 로도 통과하지만 같은 취약점이 있다 → 발견한 이슈로 남긴다 |

## 막혔던 부분 / 해결 과정
**증상** — Task 8 완료 판정의 `uv run pytest` 에서 `test_screening_is_not_built_when_it_is_turned_off` 1개 실패. 코드 변경이 전혀 없는 태스크였다.

**가설과 검증** — 테스트가 `Settings()` 로 "기본값은 꺼짐"을 확인한다. `Settings` 는 현재 디렉터리의 `.env` 를 읽고, 그 `.env` 에는 stock-screening 뒤에 넣은 `APP_SCREEN_ENABLED=true` 가 있다. 환경변수에는 `APP_` 가 없었다(`env | grep APP_` 빈 결과). 테스트를 단독으로 돌려도 같은 실패 → 환경이 아니라 `.env`.

**원인** — 2026-10-08 에는 `.env` 에 그 줄이 없어 통과했다. "실제 메일 수신 확인"을 위해 `.env` 를 켠 순간부터 이 테스트는 이 PC 에서 항상 실패한다. 테스트가 개발자의 로컬 설정에 묶여 있었다.

**해결** — 저장소의 다른 테스트가 쓰는 방식(`monkeypatch.chdir(tmp_path)` + `delenv`)을 그대로 적용. `Settings()` 를 기본값 그대로 쓰는 다른 테스트(collect 3개, smtp 1개, backfill 1개)는 지금 `.env` 값으로 우연히 통과한다.

## 검증 결과
```
.\scripts\register_tasks.ps1
  removed finbrief-us-open-once
  registered finbrief-kr-open: Mon-Fri 09:00
  registered finbrief-us-open: Mon-Fri 22:30
  finbrief-kr-open   Ready    next run 2026-10-13 오전 9:00:00
  finbrief-us-open   Ready    next run 2026-10-12 오후 10:30:00

Start-ScheduledTask finbrief-kr-open   → 2분 41초 뒤 Ready, LastTaskResult 0
logs\kr_open.log 끝:
  briefing kr_open 2026-10-12: sent=0 skipped=1 failed=0 aborted=False   ← 오늘 아침 수동 발송분이 있어 건너뜀
  === exit 0 2026-10-12 14:14:22.05 ===
logs\history.log: 2026-10-12 14:14:22.05 kr_open rc=0
비밀값 검사: .env 의 비밀값 5개가 로그에 없음

task done 8 (완료 판정) → 통과: 작업 2개 등록 확인 · exit 0 · ruff · mypy · pytest 427 passed, 커버리지 98%
```
첫 자동 실행은 **오늘 22:30 (us_open)**, 그다음은 내일 09:00 (kr_open). 결과는 `Get-ScheduledTaskInfo` 와 `logs\history.log` 에서 본다.

## 발견한 이슈 (이번 범위 밖)
- [ ] **국내 공휴일 다음 거래일까지, 매 실행마다 국내 전 종목 이력을 다시 받는다.** 오늘 두 번의 실행에서 `reloaded=353`, `reloaded=350`(각 ~2분, FDR 호출 350회). 원인: `expected_session(KR, 월 14:00)` = 2026-10-09(한글날, 거래 없음). 저장된 마지막 날(10-08) < settled 인데 랭킹의 오늘(10-12, 진행 중) 행은 `traded_on <= settled` 에서 걸러져 `row` 가 없고, `_continues` 도 못 가니 `_load_kr(replace=True)` 로 떨어진다. 10-09 봉은 영원히 안 생기므로 10-12 장이 끝날 때까지 반복된다. 해결 후보: 랭킹 행의 `prev_close` 가 저장된 마지막 종가와 같고 `traded_on` 이 settled 뒤라면 "그 사이 거래 없음"으로 보고 건너뛴다.
- [ ] `Settings()` 를 기본값으로 쓰는 다른 테스트들도 `.env` 에 묶여 있다. 공통 fixture(`autouse` 로 `chdir(tmp_path)`)가 맞다.
- [ ] 로그인 전에는 어느 방식도 돌지 않는다. 재부팅한 아침이 잦으면 자동 로그인을 본다.
- [ ] Task 10 "이미 전원이 받은 날은 수집을 건너뛴다"는 todo 로 남아 있다. 오늘 수동 확인에서도 수집(Marketaux 3회)과 이력 갱신을 다시 했다.

## 남은 것
- [ ] 오늘 22:30 us_open 과 내일 09:00 kr_open 이 자동으로 왔는지 확인하고 여기에 적는다.
