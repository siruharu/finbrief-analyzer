---
description: 태스크 모드 — 플랜의 Task 를 실행 가능한 체크리스트와 이슈로 전개
argument-hint: <플랜 파일명> [Task 번호]
allowed-tools: Read, Glob, Grep, Write, Edit, Bash(gh issue:*), Bash(git branch:*), Bash(git status:*), Bash(.claude/hooks/harness.py:*)
---

# ✅ 태스크 모드

플랜과 구현 사이를 잇는 단계다. 여전히 **프로덕션 코드는 쓰지 않는다.**

## 목표
플랜의 Task 를 "지금 바로 손댈 수 있는" 수준까지 내린다. 구현 중 "어디부터 만지지" 로 멈추지 않게 하는 것이 목적이다.

## 절차

0. **단계 선언** — `.claude/hooks/harness.py stage task` 를 먼저 실행한다.

1. **입력 로드** — `$ARGUMENTS` → `docs/03_plan/`. 없으면 `/plan` 을 먼저 요구하고 멈춘다.

2. **전개** — 각 Task 를 다음으로 분해한다.
   - 손댈 파일과 함수/클래스 이름까지 구체적으로.
   - **먼저 쓸 테스트의 케이스 이름 목록** (given/when/then 문장으로).
   - 엣지 케이스·실패 경로. 정상 경로만 적힌 태스크는 미완성이다.
   - 완료 판정 커맨드 (`make test`, `./gradlew test` 등 실제로 돌릴 명령).

3. **브랜치/이슈**
   - 브랜치명 제안: `<type>/<이슈번호>-<slug>`.
   - 사용자가 원하면 `gh issue create` 로 이슈를 만든다. **묻지 않고 만들지 않는다.**

4. **기계가 읽는 상태로 등록** — 이게 이 단계의 핵심 산출물이다.

   ```bash
   .claude/hooks/harness.py task add "파서에 COG 필드 보존" --verify "make check"
   .claude/hooks/harness.py task add "컨트롤러에 노출" --after 1 --verify "make check"
   ```

   - `--verify` 는 **그 Task 가 끝났는지 기계가 판정할 실제 명령**이다. 산문 DoD 로 두지 않는다.
     판정 명령을 못 적겠으면 그 Task 는 아직 덜 쪼개진 것이다.
   - `--after` 로 선행 관계를 건다. 순서를 사람 기억에 맡기지 않는다.
   - 저장 위치는 `docs/04_tasks/<주제>.tasks.json` (자동).

5. **설계 메모 기록** — `docs/04_tasks/YYYY-MM-DD_<slug>.md` (양식: `docs/00_templates/task.md`)
   - **체크박스를 여기에 다시 적지 않는다.** 상태 정본은 `tasks.json` 하나다.
   - 이 문서에는 **왜 이렇게 쪼갰는지**, 손댈 파일, 먼저 쓸 테스트 이름, 엣지 케이스를 적는다.

6. **마무리** — `task list` 출력과 브랜치명을 보여주고 `/implement` 제안.

## 제약
- 프로덕션 코드 작성 **금지**.
- **판정 명령 없는 Task 를 만들지 않는다.** "테스트 통과" 같은 문장은 판정이 아니다.
- 플랜에 없는 작업을 여기서 추가하지 않는다. 필요하면 플랜으로 되돌아간다.
