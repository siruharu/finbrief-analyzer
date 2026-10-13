---
type: implementation
project: finbrief-analyzer
topic: news-summary
created: 2026-10-13
status: done
source_task: "[[2026-10-12_news-summary]]"
commits: [43e02f8]
blog_candidate: false
tags: [implementation, news, llm, summary]
---

# 🛠️ 구현: news-summary Task 8 — 메일에 실린 요약을 JSON 으로 남기기

> 단계 생략 — [[2026-10-12_news-summary]] 구현 노트의 "발견한 이슈" 1번. 외부 호출 없는 파일 쓰기 하나라 `task add` 로 Task 8 을 추가해 바로 구현했다.

## 한 일
- `summarize/record.py` — `save_digest(directory, slot, day, digest) -> Path | None`: `logs/digests/<날짜>_<슬롯>.json` 에 모델·토큰·선택 항목(줄·제목·URL·출처)을 쓴다. 디렉터리를 만들고, 같은 날·슬롯은 덮어쓴다. `OSError` 는 경고 한 줄 + `None`.
- `Settings.summary_log_dir: Path | None = Path("logs/digests")` — 빈 값이면 None(남기지 않음). `.env.example` 안내.
- `JobDeps.digest_dir`, `open_deps` 배선, `run()` 에서 digest 가 있고 디렉터리가 있으면 저장.
- 테스트 5개(record 3, jobs 2).

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| JSON 파일, 날짜·슬롯 하나당 하나 | DB 테이블 | 회고용이고 수신자와 무관하다. 폴더를 열어 읽으면 끝. 스키마 변경·마이그레이션 없음 |
| 저장 실패는 경고만 | 작업 실패 | 회고 보조 장치가 발송을 막으면 안 된다 |
| `run()` 에서 호출(어댑터 밖) | 어댑터가 저장 | 어댑터는 API 만 안다. 날짜·슬롯·디렉터리는 작업의 것 |
| 상대 경로 `logs/digests` | 절대 경로 | 런처가 작업 디렉터리를 저장소로 맞춘다. `logs/` 는 이미 git 제외 |

## 막혔던 부분 / 해결 과정
없음.

## 검증 결과
```
uv run pytest tests/summarize tests/jobs tests/test_config.py → 통과 (70)
task done 8 (ruff · mypy · 전체 pytest)                        → 통과
```
실전: 오늘 kr_open 은 09:02 에 이미 나갔고(수집 생략), us_open 의 ET 날짜는 아직 어제라 지금 돌려도 건너뛴다. **첫 파일은 오늘 22:30 us_open 실행에서 `logs/digests/2026-10-13_us_open.json` 으로 생긴다.**

## 발견한 이슈 (이번 범위 밖)
- 없음.

## 남은 것
- [ ] 2026-10-13 22:30 뒤 `logs/digests/2026-10-13_us_open.json` 확인.
