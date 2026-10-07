---
type: task
project: finbrief-analyzer
topic: <주제>
created: YYYY-MM-DD
source_plan: "[[YYYY-MM-DD_slug]]"
branch: <type>/<이슈번호>-<slug>
issue: #
tags: [task]
next: implementation
---

# ✅ 작업: <주제>

> **작업 상태의 정본은 이 문서가 아니라 `<주제>.tasks.json` 이다.**
> 체크박스를 여기에 다시 적지 않는다 — 두 곳을 손으로 맞추면 반드시 어긋난다.
>
> ```bash
> .claude/hooks/harness.py task list
> .claude/hooks/harness.py task next
> ```
>
> 이 문서는 **왜 이렇게 쪼갰는지**를 적는 곳이다.

## 쪼갠 기준
Task 경계를 여기서 그은 이유. (예: "파서와 컨트롤러를 나눈 건 파서만 먼저
릴리스해도 기존 동작이 안 깨지기 때문")

## Task 별 설계 메모

### Task 1 — <제목>

**손댈 곳**

| 파일 | 함수/클래스 | 작업 |
|---|---|---|
| | | |

**먼저 쓸 테스트**
- `<대상>이 <조건>일 때 <결과>를 반환한다`
- `<대상>이 <실패 조건>이면 <예외>를 던진다`

**엣지 케이스**
- 빈 값 / 널
- 경계값
- 실패·타임아웃 경로

**완료 판정** — `tasks.json` 의 `verify` 에 넣은 명령과 같아야 한다
```bash
make check
```

### Task 2 — <제목>
(동일 구조)

## 열어둔 질문
- 
