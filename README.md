# finbrief-analyzer

시세·뉴스를 수집·분석해 일일 금융 브리핑을 만드는 엔진

## 시작

```bash
make install
make dev        # http://localhost:8000/health
```

## 개발

```bash
make check      # lint + typecheck + test
```

문서는 `docs/` — 작업 흐름은 [`docs/WORKFLOW.md`](docs/WORKFLOW.md).

## 설정 — 뉴스 선별·한 줄 요약 (Claude API)

`.env` 에 `APP_ANTHROPIC_API_KEY` 가 있으면 수집한 뉴스(최대 80건)를 Claude 에 한 번 보내
**7건을 골라 건별 한국어 한 줄**로 싣는다. 모델은 번호로만 고르고 제목·URL 은 코드가 원문에서 되찾는다.
키가 없거나 호출이 실패하면 지금처럼 **최신순 10건 목록**이 간다. 메일은 항상 나간다.

| 변수 | 기본값 | 뜻 |
|---|---|---|
| `APP_ANTHROPIC_API_KEY` | (없음 = 꺼짐) | Anthropic API 키 |
| `APP_SUMMARY_MODEL` | `claude-opus-5-5` | PoC 비교 결과 (`docs/01_research/2026-10-12_news-summary-poc.md`) |
| `APP_SUMMARY_EFFORT` | `low` | `low` / `medium` / `high`. medium 은 비용 1.4배, 품질 차이 없음 |
| `APP_SUMMARY_PICKS` | `7` | 싣는 건수 (1~20) |
| `APP_SUMMARY_MAX_TOKENS` | `2000` | 출력 상한 (thinking 포함, 관측 최대 1,200) |
| `APP_SUMMARY_TIMEOUT_SECONDS` | `120` | 호출 타임아웃. SDK 가 2회 재시도 |

- 비용: 호출당 약 $0.035, 하루 2회면 월 $2 안팎. 로그 한 줄 `summary: picks=7 input_tokens=… output_tokens=…` 로 확인한다.
- 실패(요율 제한·타임아웃·거부·스키마 불일치)는 경고 로그 `summary unavailable` 과 메일의
  "자동 요약을 만들지 못해 최신 기사 순으로 싣습니다." 한 줄로 드러난다.
- 끄기: 키를 비우면 다음 실행부터 목록이다. 코드 배포 없음.

## 운영 — 로컬 스케줄

브리핑은 이 PC 의 Windows 작업 스케줄러가 평일에 두 번 보낸다. AWS 는 쓰지 않는다
(근거: `docs/02_analysis/2026-10-12_local-schedule.md`).

| 항목 | 시각 (PC 로컬, KST) | 뜻 |
|---|---|---|
| `finbrief-kr-open` | 월~금 09:00 | 국내 개장 브리핑 |
| `finbrief-us-open` | 월~금 22:30 | 미국 개장 브리핑. 여름엔 ET 09:30, 겨울엔 ET 08:30 |

```powershell
.\scripts\register_tasks.ps1               # 등록·갱신 (다시 돌려도 안전)
.\scripts\register_tasks.ps1 -Unregister   # 해제 — 발송이 즉시 멈춘다
Start-ScheduledTask finbrief-kr-open       # 지금 한 번 돌려 보기
Get-ScheduledTaskInfo finbrief-kr-open     # LastTaskResult 0 이면 정상, NextRunTime 이 다음 실행
```

- **런처**는 `scripts\run_briefing.cmd <kr_open|us_open>` 이다. 저장소로 이동해 Docker 엔진을 기다리고,
  `docker compose --profile db up -d --wait` 로 DB 를 띄운 뒤 `uv run python -m finbrief_analyzer.jobs.run_briefing` 을 돌린다.
  작업의 종료 코드를 그대로 돌려주므로 작업 스케줄러의 "마지막 실행 결과"가 곧 작업 결과다.
- **로그**는 `logs\<slot>.log`(마지막 실행 전체)와 `logs\history.log`(실행마다 한 줄). git 에는 올라가지 않는다.
- **놓친 실행**: PC 가 그 시각에 잠들어 있었으면 깨어난 뒤 바로 돈다. 같은 날 두 번 불려도 발송 기록이 중복을 막는다.
- **전제**: 사용자가 로그인돼 있고 Docker Desktop 이 떠 있어야 한다(로그인 시 자동 시작). 로그인 전에는 돌지 않는다.
- **앱 비밀번호 교체**: `.env` 의 `APP_SMTP_PASSWORD` 만 바꾼다. 스케줄은 건드릴 것이 없다.
- 수동 실행은 그대로 쓸 수 있다: `uv run python -m finbrief_analyzer.jobs.run_briefing --slot kr_open`.
