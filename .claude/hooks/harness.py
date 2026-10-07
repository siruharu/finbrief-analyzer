#!/usr/bin/env python3
"""프로젝트 하네스 — 단계 게이트와 즉시 검증.

`.claude/settings.json` 의 훅에서 호출된다. 사람이 직접 쓰는 건 `stage` 뿐.

  .claude/hooks/harness.py stage implement 2026-09-15_foo
  .claude/hooks/harness.py stage none        # 게이트 해제
  .claude/hooks/harness.py task next         # 다음에 할 일
  .claude/hooks/harness.py task done 1       # 판정을 통과해야 done 이 된다
  .claude/hooks/harness.py doctor            # 자가 점검

설계 원칙: **고장나면 열린다.** 훅 자체의 버그로 편집이 전부 막히는 것보다
게이트가 한 번 새는 쪽이 낫다. 차단은 상태가 명시적으로 읽기 전용일 때만 한다.
"""

# macOS 시스템 python3 는 아직 3.9 다. 훅은 어떤 python3 로 불릴지 모르므로
# 최신 문법(PEP 604 등)을 런타임에 평가하지 않게 한다.
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".claude" / "state.json"

# 산출물만 쓰는 단계 — 프로덕션 코드 편집을 막는다
READ_ONLY_STAGES = {"research", "analyze", "plan", "task"}
# 읽기 전용 단계에서도 쓸 수 있는 곳
WRITABLE_PREFIXES = ("docs/", ".claude/")
# 즉시 검증을 돌리는 단계 (None = 단계 미설정, 그때도 돈다)
VERIFY_STAGES = {"implement", "test", None}

ALL_STAGES = ["research", "analyze", "plan", "task", "implement", "test", "none"]


# ── 상태 ────────────────────────────────────────────────────────────
def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def save_state(d: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    d["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    STATE.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")


def stdin_json() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def block(msg: str) -> None:
    """exit 2 = 도구 호출 차단 + stderr 를 모델에게 전달."""
    print(msg, file=sys.stderr)
    sys.exit(2)


def rel_to_root(p: str) -> str | None:
    if not p:
        return None
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return None  # 프로젝트 밖 — 게이트 대상이 아니다


def run(cmd: list[str], cwd: Path = ROOT, timeout: int = 120):
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )


# ── stage: 사람/커맨드가 단계를 선언한다 ─────────────────────────────
def cmd_stage(argv: list[str]) -> int:
    if not argv:
        s = load_state()
        print(f"stage={s.get('stage') or 'none'} topic={s.get('topic') or '-'}")
        return 0
    stage = argv[0]
    if stage not in ALL_STAGES:
        print(f"모르는 단계: {stage} ({'|'.join(ALL_STAGES)})", file=sys.stderr)
        return 1
    s = load_state()
    s["stage"] = None if stage == "none" else stage
    if len(argv) > 1:
        s["topic"] = argv[1]
    save_state(s)
    print(f"stage → {stage}" + (f" ({s.get('topic')})" if s.get("topic") else ""))
    return 0


# ── PreToolUse: 읽기 전용 단계에서 코드 편집 차단 ────────────────────
def cmd_pre_edit() -> int:
    if os.environ.get("HARNESS_SKIP") == "1":
        return 0
    stage = load_state().get("stage")
    if stage not in READ_ONLY_STAGES:
        return 0

    data = stdin_json()
    path = (data.get("tool_input") or {}).get("file_path", "")
    rel = rel_to_root(path)
    if rel is None or rel.startswith(WRITABLE_PREFIXES):
        return 0

    block(
        f"차단됨: 지금은 '{stage}' 단계다. 이 단계에서는 프로덕션 코드를 고치지 않는다.\n"
        f"  막힌 경로: {rel}\n"
        f"  쓸 수 있는 곳: docs/ , .claude/\n"
        f"\n"
        f"고쳐야 할 것을 발견했다면 산출물에 적어두고 진행해라.\n"
        f"지금 구현으로 넘어가야 한다면 /implement 를 실행하거나,\n"
        f"사용자 동의를 받고 `.claude/hooks/harness.py stage implement` 로 전환해라."
    )
    return 0


# ── PostToolUse: 편집 직후 그 파일만 빠르게 검증 ─────────────────────
def _check_python(rel: str):
    if (ROOT / ".venv").exists() and shutil.which("uv"):
        r = run(["uv", "run", "ruff", "check", rel])
    elif shutil.which("ruff"):
        r = run(["ruff", "check", rel])
    else:
        return None
    # ruff: 0=통과, 1=위반, 2+=ruff 자체 오류.
    # 도구가 못 돈 것을 "코드가 틀렸다" 로 보고하면 멀쩡한 작업이 막힌다.
    return None if r.returncode >= 2 else r


def _check_go(rel: str):
    if not shutil.which("gofmt"):
        return None
    r = run(["gofmt", "-l", rel])
    if r.returncode != 0:
        # gofmt 자체가 못 돌았다 (버전 미설정된 asdf 셰임 등). 코드 문제가 아니다.
        return None
    if r.stdout.strip():
        # gofmt -l 은 포맷이 틀린 파일명을 출력하고 exit 0 한다
        r.returncode = 1
        r.stdout = f"gofmt 미적용: {r.stdout.strip()}\n  `gofmt -w {rel}` 로 정리해라."
    return r


def cmd_post_edit() -> int:
    if os.environ.get("HARNESS_SKIP") == "1":
        return 0
    if load_state().get("stage") not in VERIFY_STAGES:
        return 0

    data = stdin_json()
    path = (data.get("tool_input") or {}).get("file_path", "")
    rel = rel_to_root(path)
    if not rel:
        return 0

    try:
        if rel.endswith(".py"):
            r = _check_python(rel)
        elif rel.endswith(".go"):
            r = _check_go(rel)
        else:
            # .kt/.java 는 파일 단위 린터가 없다. Stop 게이트에서 본다.
            return 0
    except Exception:
        return 0  # 검증기 자체가 깨져도 작업은 막지 않는다

    if r is None or r.returncode == 0:
        return 0

    out = ((r.stdout or "") + (r.stderr or "")).strip()
    block(f"{rel} 검증 실패 — 다음 작업으로 넘어가기 전에 고쳐라.\n\n{out[:2000]}")
    return 0


# ── Stop: "끝났다" 를 기계가 판정한다 ────────────────────────────────
def _verify_command() -> list[str] | None:
    s = load_state()
    if s.get("verify"):
        return s["verify"].split()
    if (ROOT / "Makefile").exists():
        r = run(["make", "-n", "check"], timeout=20)
        if r.returncode == 0:
            return ["make", "check"]
    if (ROOT / "gradlew").exists():
        return ["./gradlew", "build", "-q"]
    return None


def cmd_stop() -> int:
    if os.environ.get("HARNESS_SKIP") == "1":
        return 0
    data = stdin_json()
    # 게이트가 자기 자신을 다시 부르는 무한루프 방지
    if data.get("stop_hook_active"):
        return 0

    s = load_state()
    if s.get("stage") not in {"implement", "test"}:
        return 0
    if s.get("gate") is False:
        return 0

    r = run(["git", "status", "--porcelain"], timeout=20)
    if r.returncode != 0 or not r.stdout.strip():
        return 0  # 바뀐 게 없으면 검증할 것도 없다

    cmd = _verify_command()
    if not cmd:
        return 0

    try:
        v = run(cmd, timeout=900)
    except Exception:
        return 0

    if v.returncode == 0:
        return 0

    out = ((v.stdout or "") + (v.stderr or "")).strip()
    block(
        f"검증 실패 — 아직 끝난 게 아니다: `{' '.join(cmd)}`\n\n"
        f"{out[-3000:]}\n\n"
        f"고치고 다시 돌려라. 정말 못 고치는 상황이면 사용자에게 무엇이 왜 실패하는지\n"
        f"보고하고, 통과했다고 말하지 마라."
    )
    return 0



# ── 태스크: 기계가 읽고 쓰는 작업 상태 ──────────────────────────────
# 산문 마크다운의 `- [ ]` 는 사람용이다. 에이전트가 "다음에 뭘 할지" 를
# 알려면 파싱이 아니라 조회가 돼야 한다. 정본은 이 JSON 이고,
# `docs/04_tasks/*.md` 는 배경·설계 의도를 적는 사람용 문서다.

STATUSES = ("todo", "doing", "blocked", "done")


def tasks_path() -> Path:
    topic = load_state().get("topic") or "tasks"
    return ROOT / "docs" / "04_tasks" / f"{topic}.tasks.json"


def load_tasks() -> dict:
    f = tasks_path()
    try:
        return json.loads(f.read_text())
    except Exception:
        return {"topic": load_state().get("topic"), "tasks": []}


def save_tasks(d: dict) -> None:
    f = tasks_path()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")


def find_task(d: dict, tid):
    for t in d["tasks"]:
        if str(t["id"]) == str(tid):
            return t
    return None


def deps_done(d: dict, t: dict) -> bool:
    for dep in t.get("after", []):
        x = find_task(d, dep)
        if not x or x["status"] != "done":
            return False
    return True


def fmt_task(t: dict) -> str:
    mark = {"todo": "[ ]", "doing": "[~]", "blocked": "[!]", "done": "[x]"}[t["status"]]
    after = f" (after {','.join(map(str, t['after']))})" if t.get("after") else ""
    note = f"  — {t['note']}" if t.get("note") else ""
    return f"{mark} {t['id']}. {t['title']}{after}{note}"


def cmd_task(argv: list[str]) -> int:
    sub = argv[0] if argv else "list"
    d = load_tasks()

    if sub == "list":
        if not d["tasks"]:
            print("태스크 없음 — /task 로 플랜을 전개해라")
            return 0
        print(f"topic: {d.get('topic') or '-'}  ({tasks_path().relative_to(ROOT)})")
        for t in d["tasks"]:
            print(" ", fmt_task(t))
        left = sum(1 for t in d["tasks"] if t["status"] != "done")
        print(f"  남은 태스크: {left}/{len(d['tasks'])}")
        return 0

    if sub == "add":
        # task add "제목" [--after 1,2] [--verify "make check"]
        if len(argv) < 2:
            print('사용법: task add "제목" [--after 1,2] [--verify "명령"]', file=sys.stderr)
            return 1
        title = argv[1]
        after, verify = [], None
        i = 2
        while i < len(argv) - 1:
            if argv[i] == "--after":
                after = [int(x) for x in argv[i + 1].split(",") if x.strip()]
            elif argv[i] == "--verify":
                verify = argv[i + 1]
            i += 2
        tid = max((t["id"] for t in d["tasks"]), default=0) + 1
        d["topic"] = load_state().get("topic")
        d["tasks"].append({
            "id": tid, "title": title, "status": "todo",
            "after": after, "verify": verify, "note": "", "commit": None,
        })
        save_tasks(d)
        print(f"추가: {tid}. {title}")
        return 0

    if sub == "next":
        for t in d["tasks"]:
            if t["status"] == "doing":
                print(f"진행 중: {fmt_task(t)}")
                return 0
        for t in d["tasks"]:
            if t["status"] == "todo" and deps_done(d, t):
                print(f"다음: {fmt_task(t)}")
                if t.get("verify"):
                    print(f"  완료 판정: {t['verify']}")
                return 0
        blocked = [t for t in d["tasks"] if t["status"] == "blocked"]
        if blocked:
            print("진행 가능한 태스크 없음 — 막힌 것부터 풀어라:", file=sys.stderr)
            for t in blocked:
                print(" ", fmt_task(t), file=sys.stderr)
            return 1
        print("남은 태스크 없음 ✅")
        return 0

    if sub in ("start", "block", "reopen"):
        if len(argv) < 2:
            print(f"사용법: task {sub} <id>", file=sys.stderr)
            return 1
        t = find_task(d, argv[1])
        if not t:
            print(f"없는 태스크: {argv[1]}", file=sys.stderr)
            return 1
        if sub == "start":
            if not deps_done(d, t):
                print(f"선행 태스크가 안 끝났다: after={t['after']}", file=sys.stderr)
                return 1
            t["status"] = "doing"
        elif sub == "block":
            t["status"] = "blocked"
            t["note"] = argv[2] if len(argv) > 2 else "이유 미기재"
        else:
            t["status"] = "todo"
            t["commit"] = None
        save_tasks(d)
        print(fmt_task(t))
        return 0

    if sub == "done":
        # 선언이 아니라 판정이다 — verify 를 실제로 돌려서 통과해야 done 이 된다
        if len(argv) < 2:
            print("사용법: task done <id>", file=sys.stderr)
            return 1
        t = find_task(d, argv[1])
        if not t:
            print(f"없는 태스크: {argv[1]}", file=sys.stderr)
            return 1
        cmd = (t.get("verify") or "").split() or _verify_command()
        if cmd:
            print(f"완료 판정 실행: {' '.join(cmd)}")
            try:
                r = run(cmd, timeout=900)
            except Exception as e:
                print(f"판정 명령 실행 실패: {e}", file=sys.stderr)
                return 1
            if r.returncode != 0:
                out = ((r.stdout or "") + (r.stderr or "")).strip()
                print(
                    f"완료 처리 거부 — 판정이 실패했다.\n\n{out[-3000:]}",
                    file=sys.stderr,
                )
                return 2
        t["status"] = "done"
        h = run(["git", "rev-parse", "--short", "HEAD"], timeout=20)
        t["commit"] = h.stdout.strip() if h.returncode == 0 else None
        save_tasks(d)
        print(f"완료: {fmt_task(t)}")
        left = sum(1 for x in d["tasks"] if x["status"] != "done")
        print(f"남은 태스크: {left}")
        return 0

    print(f"모르는 하위 명령: {sub} (list|add|next|start|done|block|reopen)", file=sys.stderr)
    return 1


# ── SessionStart: 새 컨텍스트에 현재 위치를 알려준다 ─────────────────
def _latest(d: str, n: int = 2) -> list[str]:
    p = ROOT / "docs" / d
    if not p.is_dir():
        return []
    fs = sorted((f for f in p.glob("*.md")), key=lambda f: f.name, reverse=True)
    return [f"docs/{d}/{f.name}" for f in fs[:n]]


def cmd_session_start() -> int:
    s = load_state()
    stage = s.get("stage")
    lines = ["# 하네스 상태"]
    topic = f" / 주제: {s['topic']}" if s.get("topic") else ""
    lines.append(f"- 단계: **{stage or '미설정'}**{topic}")
    if stage in READ_ONLY_STAGES:
        lines.append(f"- ⛔ '{stage}' 단계 — `docs/`, `.claude/` 밖의 편집은 훅이 차단한다.")
    for label, d in [("플랜", "03_plan"), ("태스크", "04_tasks"), ("구현", "05_implementation")]:
        f = _latest(d, 1)
        if f:
            lines.append(f"- 최근 {label}: `{f[0]}`")
    td = load_tasks()
    if td["tasks"]:
        left = sum(1 for t in td["tasks"] if t["status"] != "done")
        lines.append(f"- 태스크: {len(td['tasks'])}개 중 {left}개 남음 — `harness.py task next`")
        for t in td["tasks"]:
            if t["status"] in ("doing", "blocked"):
                lines.append(f"  - {fmt_task(t)}")
    lines.append("- 흐름: `docs/WORKFLOW.md`")
    print("\n".join(lines))
    return 0


# ── doctor ──────────────────────────────────────────────────────────
def cmd_doctor() -> int:
    ok = True
    print(f"ROOT   {ROOT}")
    print(f"state  {STATE} {'있음' if STATE.exists() else '없음 (단계 미설정 = 게이트 꺼짐)'}")
    print(f"stage  {load_state().get('stage') or 'none'}")
    cmd = _verify_command()
    print(f"검증   {' '.join(cmd) if cmd else '자동 탐지 실패 — state.json 의 verify 로 지정해라'}")
    for t in ("git", "ruff", "uv", "gofmt", "make"):
        print(f"  {t:6} {'✓' if shutil.which(t) else '—'}")
    settings = ROOT / ".claude" / "settings.json"
    if not settings.exists():
        print("settings.json 없음 — 훅이 등록되지 않았다")
        ok = False
    else:
        try:
            h = json.loads(settings.read_text()).get("hooks", {})
            for e in ("PreToolUse", "PostToolUse", "Stop", "SessionStart"):
                print(f"  훅 {e:14} {'✓' if e in h else '—'}")
        except Exception as e:
            print(f"settings.json 파싱 실패: {e}")
            ok = False
    return 0 if ok else 1


COMMANDS = {
    "stage": lambda a: cmd_stage(a),
    "task": lambda a: cmd_task(a),
    "pre-edit": lambda a: cmd_pre_edit(),
    "post-edit": lambda a: cmd_post_edit(),
    "stop": lambda a: cmd_stop(),
    "session-start": lambda a: cmd_session_start(),
    "doctor": lambda a: cmd_doctor(),
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"사용법: harness.py {{{'|'.join(COMMANDS)}}} [인자]", file=sys.stderr)
        sys.exit(1)
    try:
        sys.exit(COMMANDS[sys.argv[1]](sys.argv[2:]))
    except SystemExit:
        raise
    except Exception as e:
        # 훅의 예외가 작업을 막지 않게 한다
        print(f"harness.py 내부 오류(무시하고 진행): {e}", file=sys.stderr)
        sys.exit(0)
