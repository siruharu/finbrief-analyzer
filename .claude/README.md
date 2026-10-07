# .claude — 이 프로젝트의 하네스

```
commands/          /research /analyze /plan /task /implement /test
hooks/harness.py   단계 게이트 · 편집 즉시 검증 · 종료 게이트 · 태스크 상태
settings.json      위 훅 등록 (사용자 전역 설정에 합쳐진다, 덮어쓰지 않는다)
state.json         현재 단계 (git 에 안 올라간다)
```

작업 상태 정본은 `docs/04_tasks/<주제>.tasks.json` 이다 (이건 커밋한다).

## 훅이 하는 일

| 시점 | 동작 |
|---|---|
| `PreToolUse` (Write/Edit) | 읽기 전용 단계(research/analyze/plan/task)면 `docs/`·`.claude/` 밖 편집을 **차단** |
| `PostToolUse` (Write/Edit) | 고친 파일 하나만 즉시 검증 (py=ruff, go=gofmt). 실패하면 그 자리에서 되돌려준다 |
| `Stop` | implement/test 단계에서 변경분이 있으면 `make check` / `./gradlew build` 를 돌리고, **실패하면 끝내지 못하게 한다** |
| `SessionStart` | 현재 단계와 최근 플랜/태스크/구현 노트 경로를 새 컨텍스트에 주입 |

**핵심은 Stop 훅이다.** "다 했습니다" 를 사람이 아니라 검증 명령이 판정한다.

## 태스크

산문 마크다운의 체크박스는 사람용이다. 에이전트가 "다음에 뭘 할지" 알려면
파싱이 아니라 조회가 돼야 한다.

```bash
.claude/hooks/harness.py task next          # 선행이 풀린 첫 태스크
.claude/hooks/harness.py task start 1
.claude/hooks/harness.py task done 1        # ← 선언이 아니라 판정이다
.claude/hooks/harness.py task block 2 "이유"
.claude/hooks/harness.py task list
```

**`task done` 은 그 태스크의 `verify` 명령을 실제로 돌린다.** 실패하면 완료
처리를 거부하고 `doing` 으로 남긴다. "다 했다" 를 말로 선언할 수 없다.

## 단계 전환

슬래시 커맨드가 알아서 바꾼다. 수동으로는:

```bash
.claude/hooks/harness.py stage            # 현재 단계 확인
.claude/hooks/harness.py stage implement 2026-09-15_topic
.claude/hooks/harness.py stage none       # 게이트 전부 해제
.claude/hooks/harness.py doctor           # 자가 점검
```

## 빠져나가기

훅이 방해되면:

```bash
HARNESS_SKIP=1 claude          # 훅 전부 무력화
```

`state.json` 에 `"gate": false` 를 넣으면 Stop 게이트만 끈다.
검증 명령을 직접 지정하려면 `"verify": "make test"`.

## 고장나면 열린다

훅 스크립트가 예외를 던지거나 state.json 이 깨져도 **작업을 막지 않는다**.
차단은 상태가 명시적으로 읽기 전용 단계일 때만 일어난다.
게이트가 한 번 새는 게, 버그 하나로 편집이 전부 막히는 것보다 낫다.
